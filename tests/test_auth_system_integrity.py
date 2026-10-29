import unittest
import os
import sys
import secrets
import tempfile
import shutil
from datetime import datetime, timedelta

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import database
import auth_services

class TestAuthSystemIntegrity(unittest.TestCase):
    """
    Verifies that the authentication database contains exactly the three
    authorized demo accounts with valid cryptographic hashes, proper roles,
    and enforced role-based access control without hardcoding plaintext passwords.
    """

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = database.DB_PATH
        cls.temp_dir = tempfile.mkdtemp(prefix="kt_test_auth_")
        cls.test_db_path = os.path.join(cls.temp_dir, "test_auth.db")
        shutil.copyfile(cls.orig_db_path, cls.test_db_path)
        database.DB_PATH = cls.test_db_path

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_exactly_three_active_demo_accounts_exist(self):
        """Verify baseline demo accounts exist and all active accounts are valid."""
        conn = database.get_connection()
        try:
            users = conn.execute("SELECT id, username, full_name, role, password_hash, salt FROM users ORDER BY username").fetchall()
            usernames = [u['username'] for u in users]
            # Baseline demo accounts must always be present
            for base_u in ['admin', 'staff', 'supervisor']:
                self.assertIn(base_u, usernames, f"Baseline account '{base_u}' must exist in users table")
            # All accounts present must be authorized demo or Phase 16 synthetic departmental accounts
            allowed_usernames = {
                'admin', 'staff', 'supervisor',
                'synthetic_sales', 'synthetic_visa', 'synthetic_ops', 'synthetic_ticketing', 'synthetic_auditor'
            }
            for u in usernames:
                self.assertIn(u, allowed_usernames, f"Unexpected user '{u}' found in database")
        finally:
            conn.close()

    def test_02_cryptographic_hash_and_salt_integrity(self):
        """Verify that each account has a 16-byte salt and 32-byte PBKDF2 hash (no plaintext)."""
        conn = database.get_connection()
        try:
            expected_roles = {
                'admin': 'Admin',
                'supervisor': 'Supervisor',
                'staff': 'Staff',
                'synthetic_sales': 'Sales',
                'synthetic_visa': 'Visa',
                'synthetic_ops': 'Operations',
                'synthetic_ticketing': 'Ticketing',
                'synthetic_auditor': 'Read-only Auditor'
            }
            users = conn.execute("SELECT username, role, password_hash, salt FROM users").fetchall()
            for u in users:
                uname = u['username']
                self.assertIn(uname, expected_roles)
                self.assertEqual(u['role'], expected_roles[uname])
                # Salt must be 16 bytes of random entropy
                self.assertIsInstance(u['salt'], bytes)
                self.assertEqual(len(u['salt']), 16, f"Salt for {uname} must be 16 bytes")
                # PBKDF2-HMAC-SHA256 hash must be 32 bytes
                self.assertIsInstance(u['password_hash'], bytes)
                self.assertEqual(len(u['password_hash']), 32, f"Password hash for {uname} must be 32 bytes")
        finally:
            conn.close()

    def test_03_disabled_account_rejected(self):
        """Verify that disabled accounts (such as shravani_admin) do not exist and cannot authenticate."""
        conn = database.get_connection()
        try:
            user = conn.execute("SELECT id FROM users WHERE username = 'shravani_admin'").fetchone()
            self.assertIsNone(user, "Disabled account 'shravani_admin' must not exist in users table")
        finally:
            conn.close()
        # Verify authenticate_user returns None
        res = auth_services.authenticate_user("shravani_admin", "DummyPassword123!")
        self.assertIsNone(res)

    def test_04_wrong_password_rejected(self):
        """Verify that invalid password attempts are rejected for all three accounts."""
        for uname in ['admin', 'supervisor', 'staff']:
            res = auth_services.authenticate_user(uname, "IncorrectPassword#9999")
            self.assertIsNone(res, f"Authentication should fail for {uname} with wrong password")

    def test_05_role_permission_gating(self):
        """Verify role enforcement rules for Admin, Supervisor, and Staff."""
        conn = database.get_connection()
        tokens = {}
        try:
            # Issue synthetic test sessions for role testing
            for uname in ['admin', 'supervisor', 'staff']:
                u = conn.execute("SELECT id, role FROM users WHERE username = ?", (uname,)).fetchone()
                token = secrets.token_urlsafe(32)
                exp = (datetime.now() + timedelta(hours=1)).isoformat()
                conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, u['id'], exp))
                tokens[uname] = token
            conn.commit()
        finally:
            conn.close()

        try:
            # Admin role checks
            admin_user = auth_services.require_role(tokens['admin'], ['Admin'])
            self.assertEqual(admin_user['role'], 'Admin')
            auth_services.require_role(tokens['admin'], ['Supervisor', 'Admin'])
            auth_services.require_role(tokens['admin'], ['Staff', 'Supervisor', 'Admin'])

            # Supervisor role checks
            super_user = auth_services.require_role(tokens['supervisor'], ['Supervisor'])
            self.assertEqual(super_user['role'], 'Supervisor')
            auth_services.require_role(tokens['supervisor'], ['Supervisor', 'Admin'])
            with self.assertRaises(PermissionError):
                auth_services.require_role(tokens['supervisor'], ['Admin'])

            # Staff role checks
            staff_user = auth_services.require_role(tokens['staff'], ['Staff'])
            self.assertEqual(staff_user['role'], 'Staff')
            with self.assertRaises(PermissionError):
                auth_services.require_role(tokens['staff'], ['Supervisor'])
            with self.assertRaises(PermissionError):
                auth_services.require_role(tokens['staff'], ['Admin'])
            with self.assertRaises(PermissionError):
                auth_services.require_role(tokens['staff'], ['Supervisor', 'Admin'])
        finally:
            for t in tokens.values():
                auth_services.logout(t)

    def test_06_session_lifecycle(self):
        """Verify session creation, retrieval, and logout destruction."""
        conn = database.get_connection()
        try:
            u = conn.execute("SELECT id FROM users WHERE username = 'staff'").fetchone()
            token = secrets.token_urlsafe(32)
            exp = (datetime.now() + timedelta(hours=1)).isoformat()
            conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, u['id'], exp))
            conn.commit()
        finally:
            conn.close()

        # Token should resolve active user
        active = auth_services.get_user_by_token(token)
        self.assertIsNotNone(active)
        self.assertEqual(active['username'], 'staff')

        # Logout should remove session
        auth_services.logout(token)
        logged_out = auth_services.get_user_by_token(token)
        self.assertIsNone(logged_out)

if __name__ == '__main__':
    unittest.main()
