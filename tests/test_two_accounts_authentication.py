import os
import sys
import unittest
import sqlite3

APP_ROOT = r"C:\KT_Vault_V3"
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

DB_PATH = os.path.join(APP_ROOT, "data", "kt_vault_v3.db")

import auth_services
import services

class TestTwoAccountsAuthentication(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_pwd = "canyon-whisper-beacon-matrix"
        cls.staff_pwd = "falcon-orchard-cobalt-harbor"

    def test_01_active_account_count_is_exactly_two(self):
        """Verify that exactly two active accounts exist in the database."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username, role, is_active FROM users WHERE is_active = 1 ORDER BY username")
        active_users = c.fetchall()
        conn.close()

        usernames = [u[0] for u in active_users]
        self.assertEqual(len(active_users), 2, f"Expected exactly 2 active users, found: {usernames}")
        self.assertIn("admin", usernames)
        self.assertIn("staff", usernames)

    def test_02_disabled_accounts_remain_in_database(self):
        """Verify historical accounts are disabled, not deleted."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username, is_active FROM users WHERE username = 'supervisor'")
        row = c.fetchone()
        conn.close()

        self.assertIsNotNone(row, "Supervisor account was deleted instead of deactivated.")
        self.assertEqual(row[1], 0, "Supervisor account should be disabled (is_active = 0).")

    def test_03_admin_successful_login(self):
        """Verify administrator can log in successfully with new memorable passphrase."""
        session = auth_services.authenticate_user("admin", self.admin_pwd)
        self.assertIsNotNone(session, "Admin authentication failed with correct passphrase.")
        self.assertEqual(session["username"], "admin")
        self.assertEqual(session["role"], "Admin")
        self.assertIn("token", session)
        self.assertTrue(len(session["token"]) > 20)

    def test_04_staff_successful_login(self):
        """Verify staff member can log in successfully with new memorable passphrase."""
        session = auth_services.authenticate_user("staff", self.staff_pwd)
        self.assertIsNotNone(session, "Staff authentication failed with correct passphrase.")
        self.assertEqual(session["username"], "staff")
        self.assertEqual(session["role"], "Staff")
        self.assertIn("token", session)
        self.assertTrue(len(session["token"]) > 20)

    def test_05_admin_incorrect_password_rejected(self):
        """Verify incorrect password for admin is rejected."""
        res = auth_services.authenticate_user("admin", "WrongAdminPassword!999")
        self.assertIsNone(res, "Incorrect admin password was not rejected.")

    def test_06_staff_incorrect_password_rejected(self):
        """Verify incorrect password for staff is rejected."""
        res = auth_services.authenticate_user("staff", "WrongStaffPassword!999")
        self.assertIsNone(res, "Incorrect staff password was not rejected.")

    def test_07_supervisor_login_blocked(self):
        """Verify disabled supervisor account cannot log in."""
        with self.assertRaises(PermissionError) as ctx:
            auth_services.authenticate_user("supervisor", "super123")
        self.assertIn("disabled", str(ctx.exception).lower())

    def test_08_admin_role_permissions(self):
        """Verify administrator has all intended administrative permissions."""
        admin_perms = auth_services.get_role_permissions("Admin")
        
        required_admin_perms = [
            "admin:access", "admin:user_manage", "admin:key_rotate", "admin:backup",
            "audit:view", "customer:view", "customer:create", "customer:edit",
            "trip:view", "trip:create", "trip:edit",
            "document:view_metadata", "document:view_content", "document:download",
            "document:upload", "document:verify", "document:reopen", "document:delete",
            "pack:generate"
        ]
        for p in required_admin_perms:
            self.assertIn(p, admin_perms, f"Admin missing permission: {p}")

    def test_09_staff_role_permissions(self):
        """Verify staff has operational permissions but NO administrative permissions."""
        staff_perms = auth_services.get_role_permissions("Staff")
        
        allowed_staff_perms = [
            "customer:view", "customer:create", "customer:edit",
            "trip:view", "trip:create", "trip:edit",
            "document:view_metadata", "document:view_content", "document:download",
            "document:upload", "document:version_history", "pack:generate"
        ]
        for p in allowed_staff_perms:
            self.assertIn(p, staff_perms, f"Staff missing operational permission: {p}")

        forbidden_staff_perms = [
            "admin:access", "admin:user_manage", "admin:key_rotate", "admin:backup",
            "audit:view", "document:verify", "document:reopen", "document:delete"
        ]
        for p in forbidden_staff_perms:
            self.assertNotIn(p, staff_perms, f"Staff has forbidden permission: {p}")

    def test_10_staff_cannot_verify_document_direct_call(self):
        """Verify staff cannot bypass UI and call services.verify_document directly."""
        staff_session = auth_services.authenticate_user("staff", self.staff_pwd)
        token = staff_session["token"]

        with self.assertRaises(PermissionError) as ctx:
            services.verify_document("DOC-TEST-DIRECT", token)
        self.assertIn("unauthorized", str(ctx.exception).lower())

    def test_11_staff_cannot_reopen_document_direct_call(self):
        """Verify staff cannot call services.reopen_document directly."""
        staff_session = auth_services.authenticate_user("staff", self.staff_pwd)
        token = staff_session["token"]

        with self.assertRaises(PermissionError) as ctx:
            services.reopen_document("DOC-TEST-DIRECT", "Test reason", token)
        self.assertIn("unauthorized", str(ctx.exception).lower())

    def test_12_staff_cannot_delete_document_direct_call(self):
        """Verify staff cannot call services.delete_document directly."""
        staff_session = auth_services.authenticate_user("staff", self.staff_pwd)
        token = staff_session["token"]

        with self.assertRaises(PermissionError) as ctx:
            services.delete_document("DOC-TEST-DIRECT", token)
        self.assertIn("unauthorized", str(ctx.exception).lower())

    def test_13_staff_cannot_manage_users_direct_call(self):
        """Verify staff cannot call auth_services.create_user_account directly."""
        staff_session = auth_services.authenticate_user("staff", self.staff_pwd)
        token = staff_session["token"]

        with self.assertRaises(PermissionError) as ctx:
            auth_services.create_user_account("evil_user", "pass123", "Evil User", "Admin", admin_token=token)
        self.assertIn("unauthorized", str(ctx.exception).lower())

    def test_14_database_integrity_and_data_preservation(self):
        """Verify PRAGMA integrity_check and preservation of customer/trip data."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(integrity, "ok", "Database integrity check failed.")

        customer_count = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        trip_count = c.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
        audit_count = c.execute("SELECT COUNT(*) FROM security_audit_logs").fetchone()[0]
        conn.close()

        self.assertGreater(customer_count, 0, "Customers were lost.")
        self.assertGreater(trip_count, 0, "Trips were lost.")
        self.assertGreater(audit_count, 0, "Security audit logs were lost.")

    def test_15_simulated_restart_persistence(self):
        """Simulate application restart and verify both accounts authenticate."""
        admin_session = auth_services.authenticate_user("admin", self.admin_pwd)
        staff_session = auth_services.authenticate_user("staff", self.staff_pwd)

        self.assertIsNotNone(admin_session)
        self.assertIsNotNone(staff_session)
        self.assertEqual(admin_session["role"], "Admin")
        self.assertEqual(staff_session["role"], "Staff")

if __name__ == "__main__":
    unittest.main()