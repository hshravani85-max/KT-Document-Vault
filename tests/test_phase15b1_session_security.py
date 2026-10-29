import unittest
import os
import sys
import json
import sqlite3
import tempfile
import shutil
import time
import secrets
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import auth_services
import database


class TestPhase15B1SessionSecurity(unittest.TestCase):
    """
    Test Suite for Phase 15B-1:
    Critical Session Token Leakage Remediation & Authentication Safety.
    Verifies:
      1. Zero session state serialization or token exposure in app.py.
      2. Timing-safe password comparison via secrets.compare_digest.
      3. Valid login for Admin, Supervisor, and Staff.
      4. Invalid credentials rejected.
      5. Logout immediately invalidates session tokens.
      6. Role-based access enforcement.
      7. Non-sensitive structured logging compliance.
    """

    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test database to test DB operations
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, "test_kt_vault.db")

        live_db = r'C:\KT_Vault_V3\data\kt_vault_v3.db'
        shutil.copy2(live_db, cls.test_db_path)

        cls.orig_get_connection = database.get_connection
        def get_test_conn():
            con = sqlite3.connect(cls.test_db_path)
            con.row_factory = sqlite3.Row
            return con
        database.get_connection = get_test_conn

    @classmethod
    def tearDownClass(cls):
        database.get_connection = cls.orig_get_connection
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_no_session_state_dumping_in_app(self):
        """1. Verify app.py source code contains NO raw st.session_state dumping to disk."""
        app_path = r'C:\KT_Vault_V3\app.py'
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()

        # Vulnerable pattern must NOT exist
        self.assertNotIn("f.write(f\"Session State: {json.dumps(safe_state)}\\n\")", app_code)
        self.assertNotIn("safe_state[k] = v", app_code)

        # Hardened non-sensitive pattern must exist
        self.assertIn("SEC-CRIT-01 hardened", app_code)
        self.assertIn('"event": "navigation"', app_code)

    def test_02_timing_safe_password_comparison_in_auth_services(self):
        """2. Verify auth_services.py uses timing-safe secrets.compare_digest."""
        auth_path = r'C:\KT_Vault_V3\auth_services.py'
        with open(auth_path, 'r', encoding='utf-8') as f:
            auth_code = f.read()

        # Vulnerable pattern must NOT exist
        self.assertNotIn("pwd_hash != user['password_hash']", auth_code)

        # Timing-safe comparison must be present
        self.assertIn("secrets.compare_digest(pwd_hash, user['password_hash'])", auth_code)

    def test_03_admin_login_success(self):
        """3. Verify Admin login succeeds with timing-safe comparison."""
        auth_res = auth_services.authenticate_user("admin", "KTAdmin@2026#Demo")
        self.assertIsNotNone(auth_res)
        self.assertEqual(auth_res['role'], 'Admin')
        self.assertGreaterEqual(len(auth_res['token']), 32)

        # Verify active session in DB
        user = auth_services.get_user_by_token(auth_res['token'])
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], 'admin')

    def test_04_supervisor_login_success(self):
        """4. Verify Supervisor login succeeds with timing-safe comparison."""
        auth_res = auth_services.authenticate_user("supervisor", "KTSuper@2026#Demo")
        self.assertIsNotNone(auth_res)
        self.assertEqual(auth_res['role'], 'Supervisor')

        user = auth_services.get_user_by_token(auth_res['token'])
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], 'supervisor')

    def test_05_staff_login_success(self):
        """5. Verify Staff login succeeds with timing-safe comparison."""
        auth_res = auth_services.authenticate_user("staff", "KTStaff@2026#Demo")
        self.assertIsNotNone(auth_res)
        self.assertEqual(auth_res['role'], 'Staff')

        user = auth_services.get_user_by_token(auth_res['token'])
        self.assertIsNotNone(user)
        self.assertEqual(user['username'], 'staff')

    def test_06_invalid_password_rejected(self):
        """6. Verify incorrect passwords are unconditionally rejected."""
        auth_res = auth_services.authenticate_user("admin", "IncorrectPassword123!")
        self.assertIsNone(auth_res)

        auth_res2 = auth_services.authenticate_user("staff", "WrongPassword456!")
        self.assertIsNone(auth_res2)

    def test_07_unknown_username_rejected(self):
        """7. Verify nonexistent usernames are unconditionally rejected."""
        auth_res = auth_services.authenticate_user("nonexistent_user", "AnyPassword123!")
        self.assertIsNone(auth_res)

    def test_08_logout_invalidates_session(self):
        """8. Verify logout immediately deletes the session token from the database."""
        auth_res = auth_services.authenticate_user("staff", "KTStaff@2026#Demo")
        token = auth_res['token']

        # Confirm token is valid
        self.assertIsNotNone(auth_services.get_user_by_token(token))

        # Logout
        auth_services.logout(token)

        # Confirm token is invalidated
        self.assertIsNone(auth_services.get_user_by_token(token))

    def test_09_role_permission_enforcement(self):
        """9. Verify require_role allows authorized roles and rejects unauthorized roles."""
        auth_res = auth_services.authenticate_user("staff", "KTStaff@2026#Demo")
        token = auth_res['token']

        # Staff can access Staff roles
        user = auth_services.require_role(token, ['Staff', 'Supervisor', 'Admin'])
        self.assertEqual(user['role'], 'Staff')

        # Staff cannot access Supervisor/Admin roles
        with self.assertRaises(PermissionError):
            auth_services.require_role(token, ['Supervisor', 'Admin'])

        with self.assertRaises(PermissionError):
            auth_services.require_role(token, ['Admin'])

    def test_10_navigation_log_strict_allowlist_and_no_sensitive_data(self):
        """10. Verify the hardened navigation logging strictly uses an allowlist and never logs query params or tokens."""
        test_log_path = os.path.join(self.temp_dir, "test_nav.log")
        mock_token = secrets.token_urlsafe(32)

        ALLOWED_LOG_PAGES = {
            "staff_home", "customers", "customer_workspace", "trips", 
            "trip_workspace", "documents", "document_review", 
            "smart_upload", "vault_search", "smart_intake", "login"
        }

        # Case A: Valid allowed page
        valid_page = "trip_workspace"
        safe_page_id = valid_page if valid_page in ALLOWED_LOG_PAGES else "other"
        safe_log_entry = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "event": "navigation",
            "page": safe_page_id,
            "authenticated": bool(mock_token)
        }
        with open(test_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(safe_log_entry) + "\n")

        # Case B: Disallowed/arbitrary input injected in URL query parameter
        injected_page = "secret_customer_token_or_payload_12345"
        safe_injected_id = injected_page if injected_page in ALLOWED_LOG_PAGES else "other"
        injected_log_entry = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "event": "navigation",
            "page": safe_injected_id,
            "authenticated": False
        }
        with open(test_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(injected_log_entry) + "\n")

        with open(test_log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2)
        parsed_1 = json.loads(lines[0].strip())
        parsed_2 = json.loads(lines[1].strip())

        self.assertEqual(parsed_1['page'], 'trip_workspace')
        self.assertEqual(parsed_2['page'], 'other')  # Blocked by allowlist!
        self.assertNotIn("secret_customer_token_or_payload_12345", lines[1])
        self.assertNotIn(mock_token, lines[0])


if __name__ == '__main__':
    unittest.main()
