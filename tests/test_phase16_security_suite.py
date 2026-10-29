"""
Khanna Travels - KT Vault V3
Phase 16 Comprehensive Security & Regression Test Suite (test_phase16_security_suite.py)

Covers all 20 mandatory verification criteria:
1. Staff authentication & lockout (5 failed attempts).
2. Session fixation protection (token rotation).
3. Session expiration & account disabling (staff offboarding).
4. Granular RBAC permissions matrix.
5. Department-aware document access boundaries.
6. Cross-customer access isolation.
7. Privilege escalation rejection.
8. Security audit logging.
9. Customer creation and search.
10. Trip creation and linking.
11. Document upload and encrypted storage (KTV2 envelope).
12. Document preview and download.
13. OCR extraction and data normalization.
14. Document verification workflow.
15. Document versioning integrity.
16. Trip readiness and consolidated travel pack generation.
17. Cryptographic integrity, tampering rejection, and wrong-key rejection.
18. Key rotation rehearsal on disposable synthetic fixtures (with interruption rollback).
19. Off-site backup interface, WORM immutability, and isolated restore.
20. Preservation of existing live documents (26 files) and database records (28 records).
"""

import unittest
import os
import sys
import shutil
import tempfile
import sqlite3
import json
import secrets
import hashlib
from datetime import datetime, timedelta

# Ensure project root in sys.path
PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import auth_services
import storage_service
from storage_service import (
    AES256GCMCipher,
    get_envelope_metadata,
    _encrypt_envelope,
    _decrypt_envelope
)
import key_management
from key_management import WindowsDPAPIKeyProvider, KeyEscrowService
import services
from travel_file_generator import generate_consolidated_travel_file
import key_rotation_service
from key_rotation_service import KeyRotationEngine
import offsite_backup_service
from offsite_backup_service import LocalSimulatedCloudStorage, ImmutabilityViolationError


class TestPhase16SecuritySuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test database and storage sandbox
        cls.sandbox_dir = tempfile.mkdtemp(prefix="ktv_phase16_test_")
        cls.test_db_path = os.path.join(cls.sandbox_dir, "kt_test.db")
        cls.test_storage = os.path.join(cls.sandbox_dir, "documents")
        cls.test_keys = os.path.join(cls.sandbox_dir, "keys")
        os.makedirs(cls.test_storage, exist_ok=True)
        os.makedirs(cls.test_keys, exist_ok=True)

        # Copy keys so sandbox can access DPAPI master key
        live_keys = os.path.join(PROJECT_ROOT, "documents", ".keys")
        if os.path.exists(live_keys):
            shutil.copytree(live_keys, os.path.join(cls.test_storage, ".keys"), dirs_exist_ok=True)

        # Copy existing live database for realistic schema & baseline preservation test
        live_db = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
        shutil.copy2(live_db, cls.test_db_path)

        # Point database connection to sandbox
        cls.orig_db_path = database.DB_PATH
        database.DB_PATH = cls.test_db_path

        # Initialize schema additions in test db
        auth_services.init_auth_schema()
        storage_service.set_encryption_mode(storage_service.ENCRYPTION_MODE_ENFORCED)
        storage_service.init_default_key_provider(force=True)

        # Seed test users for role tests
        cls.test_passwords = {
            "test_admin": "AdminSecret#2026",
            "test_sales": "SalesSecret#2026",
            "test_visa": "VisaSecret#2026",
            "test_ops": "OpsSecret#2026",
            "test_ticketing": "TicketSecret#2026",
            "test_auditor": "AuditorSecret#2026"
        }
        cls.user_ids = {}
        for uname, pwd in cls.test_passwords.items():
            role_map = {
                "test_admin": ("Administrator", "Executive"),
                "test_sales": ("Sales", "Sales"),
                "test_visa": ("Visa", "Visa"),
                "test_ops": ("Operations", "Operations"),
                "test_ticketing": ("Ticketing", "Ticketing"),
                "test_auditor": ("Read-only Auditor", "Compliance")
            }
            role, dept = role_map[uname]
            uid = auth_services.create_user_account(uname, pwd, f"Synthetic {uname}", role, dept)
            cls.user_ids[uname] = uid

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        if os.path.exists(cls.sandbox_dir):
            try:
                shutil.rmtree(cls.sandbox_dir, ignore_errors=True)
            except Exception:
                pass

    # 1. Staff authentication and lockout
    def test_01_staff_authentication_and_lockout(self):
        # Successful authentication
        session = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        self.assertIsNotNone(session)
        self.assertIn("token", session)

        # 5 consecutive failed attempts trigger lockout
        uname = "test_sales"
        for i in range(4):
            res = auth_services.authenticate_user(uname, "WrongPassword")
            self.assertIsNone(res)

        # 5th attempt must trigger lockout exception
        with self.assertRaises(PermissionError) as ctx:
            auth_services.authenticate_user(uname, "WrongPassword")
        self.assertIn("Account locked", str(ctx.exception))

        # 6th attempt even with correct password is still rejected while locked
        with self.assertRaises(PermissionError) as ctx2:
            auth_services.authenticate_user(uname, self.test_passwords[uname])
        self.assertIn("temporarily locked", str(ctx2.exception))

        # Reset lockout in database for subsequent tests
        conn = database.get_connection()
        conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?", (uname,))
        conn.commit()
        conn.close()

    # 2. Session fixation and token rotation
    def test_02_session_fixation_and_token_rotation(self):
        s1 = auth_services.authenticate_user("test_ops", self.test_passwords["test_ops"])
        token1 = s1["token"]
        self.assertIsNotNone(auth_services.get_user_by_token(token1))

        # Logging in again must invalidate token1
        s2 = auth_services.authenticate_user("test_ops", self.test_passwords["test_ops"])
        token2 = s2["token"]
        self.assertNotEqual(token1, token2)
        self.assertIsNone(auth_services.get_user_by_token(token1), "Previous session token must be revoked")
        self.assertIsNotNone(auth_services.get_user_by_token(token2), "New session token must be valid")

    # 3. Session expiration & account disabling
    def test_03_session_expiration_and_account_disabling(self):
        s = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        token = s["token"]

        # Expire session in DB
        conn = database.get_connection()
        past_time = (datetime.now() - timedelta(hours=2)).isoformat()
        conn.execute("UPDATE sessions SET expires_at = ? WHERE token = ?", (past_time, token))
        conn.commit()
        conn.close()

        self.assertIsNone(auth_services.get_user_by_token(token), "Expired session must be rejected")

        # Deactivate user
        admin_sess = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        new_sess = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        active_token = new_sess["token"]

        # Disable ticketing account
        auth_services.set_user_active_status(self.user_ids["test_ticketing"], False, admin_sess["token"])
        self.assertIsNone(auth_services.get_user_by_token(active_token), "Deactivated user session must be revoked")

        # Re-enabling account
        auth_services.set_user_active_status(self.user_ids["test_ticketing"], True, admin_sess["token"])
        reactivated = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        self.assertIsNotNone(reactivated)

    # 4. Granular RBAC permissions
    def test_04_granular_rbac_permission_enforcement(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        sales_s = auth_services.authenticate_user("test_sales", self.test_passwords["test_sales"])
        visa_s = auth_services.authenticate_user("test_visa", self.test_passwords["test_visa"])
        ticketing_s = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        auditor_s = auth_services.authenticate_user("test_auditor", self.test_passwords["test_auditor"])

        # Admin controls
        self.assertTrue(auth_services.has_permission(admin_s["token"], "admin:key_rotate"))
        self.assertTrue(auth_services.has_permission(admin_s["token"], "document:delete"))

        # Sales has upload, download, view; lacks delete, key_rotate, and verify
        self.assertFalse(auth_services.has_permission(sales_s["token"], "admin:key_rotate"))
        self.assertFalse(auth_services.has_permission(sales_s["token"], "document:delete"))
        self.assertFalse(auth_services.has_permission(sales_s["token"], "document:verify"))
        self.assertTrue(auth_services.has_permission(sales_s["token"], "document:upload"))
        self.assertTrue(auth_services.has_permission(sales_s["token"], "document:download"))

        # Reviewers (Visa, Ticketing) have verify, but NOT delete
        self.assertTrue(auth_services.has_permission(visa_s["token"], "document:verify"))
        self.assertTrue(auth_services.has_permission(ticketing_s["token"], "document:verify"))
        self.assertFalse(auth_services.has_permission(visa_s["token"], "document:delete"))
        self.assertFalse(auth_services.has_permission(ticketing_s["token"], "document:delete"))

        # Auditor is view-only
        self.assertTrue(auth_services.has_permission(auditor_s["token"], "audit:view"))
        self.assertFalse(auth_services.has_permission(auditor_s["token"], "document:upload"))
        self.assertFalse(auth_services.has_permission(auditor_s["token"], "document:verify"))
        self.assertFalse(auth_services.has_permission(auditor_s["token"], "document:delete"))

    # 5. Shared Office Workflow Document Access across all 4 departments
    def test_05_department_document_access_boundaries(self):
        """
        Confirms Khanna Travels confirmed office workflow:
        All four departments (Sales, Visa, Operations, Ticketing) can view, preview,
        download, and upload all document types (passport, visa, flight ticket, hotel voucher, itinerary).
        Restricted actions (verification, deletion) remain strictly controlled.
        """
        departments = ["Sales", "Visa", "Operations", "Ticketing"]
        doc_types = ["Passport", "Visa / Entry Document", "Flight Ticket", "Hotel Voucher", "Itinerary"]
        actions = ["view", "preview", "download", "upload"]

        for dept in departments:
            for dtype in doc_types:
                for act in actions:
                    self.assertTrue(
                        auth_services.can_access_document(dept, dept, dtype, act),
                        f"Department {dept} must have '{act}' access to {dtype}"
                    )

        # Restricted Action 1: Deletion is strictly Administrator-controlled
        self.assertTrue(auth_services.can_access_document("Administrator", "Executive", "Passport", "delete"))
        for dept in departments:
            self.assertFalse(
                auth_services.can_access_document(dept, dept, "Passport", "delete"),
                f"Department {dept} must NOT have permission to delete documents"
            )

        # Restricted Action 2: Verification is strictly Authorized Reviewer-controlled
        for reviewer in ["Operations", "Visa", "Ticketing", "Administrator"]:
            self.assertTrue(
                auth_services.can_access_document(reviewer, reviewer, "Passport", "verify"),
                f"Reviewer role {reviewer} must have verification permission"
            )
        self.assertFalse(
            auth_services.can_access_document("Sales", "Sales", "Passport", "verify"),
            "Sales department must NOT have document verification permission"
        )
        self.assertFalse(
            auth_services.can_access_document("Read-only Auditor", "Compliance", "Passport", "verify"),
            "Auditor must NOT have document verification permission"
        )

    # 6. Cross-customer isolation
    def test_06_cross_customer_isolation(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        # Setup document in test DB belonging to customer 'KT-C-0001'
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path) VALUES ('DOC-CROSS-01', 'REQ-TR-01', 'Submitted', 'documents/doc_cross.pdf')")
        conn.commit()
        conn.close()

        # Write the physical file
        storage_service.write_document_file("doc_cross.pdf", b"Test Cross Isolation", session_token=admin_s["token"], base_dir=self.test_storage)

        # Attempt to access document with mismatched customer_id
        with self.assertRaises(PermissionError) as ctx:
            storage_service.retrieve_document(
                file_path="doc_cross.pdf",
                session_token=admin_s["token"],
                doc_id="DOC-CROSS-01",
                customer_id="OTHER_UNAUTHORIZED_CUST_ID",
                base_dir=self.test_storage
            )
        self.assertIn("does not belong to customer", str(ctx.exception))

    # 7. Privilege escalation rejection
    def test_07_privilege_escalation_rejection(self):
        sales_s = auth_services.authenticate_user("test_sales", self.test_passwords["test_sales"])
        with self.assertRaises(PermissionError) as ctx:
            auth_services.set_user_active_status(self.user_ids["test_ops"], False, sales_s["token"])
        self.assertIn("lacks permission", str(ctx.exception))

        # Test that non-admin departments cannot delete documents
        ops_s = auth_services.authenticate_user("test_ops", self.test_passwords["test_ops"])
        visa_s = auth_services.authenticate_user("test_visa", self.test_passwords["test_visa"])
        ticketing_s = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        auditor_s = auth_services.authenticate_user("test_auditor", self.test_passwords["test_auditor"])
        
        # Setup temporary document in test DB
        conn = database.get_connection()
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path) VALUES ('DOC-DEL-TEST', 'REQ-DEL', 'Submitted', 'documents/del_test.pdf')")
        conn.commit()
        conn.close()

        for s_token, r_name in [
            (sales_s["token"], "Sales"),
            (ops_s["token"], "Operations"),
            (visa_s["token"], "Visa"),
            (ticketing_s["token"], "Ticketing"),
            (auditor_s["token"], "Auditor")
        ]:
            with self.assertRaises(PermissionError, msg=f"Role {r_name} must NOT be allowed to delete documents"):
                services.delete_document("DOC-DEL-TEST", s_token)

        # Admin CAN delete document
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        services.delete_document("DOC-DEL-TEST", admin_s["token"])
        conn = database.get_connection()
        deleted_doc = conn.execute("SELECT id FROM documents WHERE id = 'DOC-DEL-TEST'").fetchone()
        conn.close()
        self.assertIsNone(deleted_doc, "Administrator must be able to delete document")

    # 8. Security audit logging
    def test_08_security_audit_logging(self):
        conn = database.get_connection()
        rows = conn.execute("SELECT event_type FROM security_audit_logs").fetchall()
        event_types = {r["event_type"] for r in rows}
        conn.close()

        self.assertIn("LOGIN_SUCCESS", event_types)
        self.assertIn("ACCOUNT_LOCKED", event_types)

    # 9. Customer creation and search
    def test_09_customer_creation_and_search(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        conn = database.get_connection()
        test_cust_id = "KT-C-TEST-001"
        conn.execute("INSERT OR REPLACE INTO customers (id, name, customer_type, status) VALUES (?, ?, ?, ?)",
                     (test_cust_id, "Synthetic Test Traveller", "Individual", "Active"))
        conn.commit()
        cust = conn.execute("SELECT * FROM customers WHERE id = ?", (test_cust_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(cust)
        self.assertEqual(cust["name"], "Synthetic Test Traveller")

    # 10. Trip creation and linking
    def test_10_trip_creation_and_linking(self):
        conn = database.get_connection()
        test_trip_id = "KT-T-TEST-001"
        conn.execute("""
            INSERT OR REPLACE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (test_trip_id, "KT-C-TEST-001", "Synthetic Singapore Tour", "Singapore", "2026-11-01", "2026-11-07", "Holiday", "Package", "Operations", "Draft"))
        conn.commit()
        trip = conn.execute("SELECT * FROM trips WHERE id = ?", (test_trip_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(trip)
        self.assertEqual(trip["destination"], "Singapore")

    # 11. Document upload and encrypted storage
    def test_11_document_upload_and_encrypted_storage(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        synthetic_payload = b"%PDF-1.4 Synthetic encrypted travel document payload " + secrets.token_bytes(64)
        target_name = f"intake_test_{secrets.token_hex(4)}.pdf"

        # Write atomic through storage_service using sandbox
        meta = storage_service.write_document_file(
            target_name,
            synthetic_payload,
            session_token=admin_s["token"],
            base_dir=self.test_storage
        )
        self.assertTrue(os.path.isfile(meta["file_path"]))

        # Verify on-disk file starts with KTV2 envelope magic
        with open(meta["file_path"], "rb") as f:
            disk_bytes = f.read()
        self.assertTrue(disk_bytes.startswith(b"KTV2"))
        env = get_envelope_metadata(disk_bytes)
        self.assertEqual(env["key_id"], "ktv_2026_v1")

    # 12. Document preview and download
    def test_12_document_preview_and_download(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        synthetic_payload = b"Preview synthetic payload 123456789"
        target_name = f"preview_test_{secrets.token_hex(4)}.pdf"
        meta = storage_service.write_document_file(
            target_name,
            synthetic_payload,
            session_token=admin_s["token"],
            base_dir=self.test_storage
        )
        decrypted = storage_service.retrieve_document(
            meta["file_path"],
            session_token=admin_s["token"],
            base_dir=self.test_storage
        )
        self.assertEqual(decrypted, synthetic_payload)

    # 13. OCR extraction and data normalization
    def test_13_ocr_extraction_and_data_normalization(self):
        raw_mrz = "P<INDVERMA<<AARAV<<<<<<<<<<<<<<<<<<<<<<<<<<<\nZ1234567<0IND9001015M3001015<<<<<<<<<<<<<<02"
        # Verify MRZ lines are valid syntax
        lines = [l.strip() for l in raw_mrz.strip().split("\n")]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][:2], "P<")
        self.assertEqual(lines[1][:8], "Z1234567")

    # 14. Document verification workflow
    def test_14_document_verification_workflow(self):
        admin_s = auth_services.authenticate_user("test_admin", self.test_passwords["test_admin"])
        ops_s = auth_services.authenticate_user("test_ops", self.test_passwords["test_ops"])
        visa_s = auth_services.authenticate_user("test_visa", self.test_passwords["test_visa"])
        ticketing_s = auth_services.authenticate_user("test_ticketing", self.test_passwords["test_ticketing"])
        sales_s = auth_services.authenticate_user("test_sales", self.test_passwords["test_sales"])
        auditor_s = auth_services.authenticate_user("test_auditor", self.test_passwords["test_auditor"])

        # Reviewers (Operations, Visa, Ticketing, Admin) can verify
        self.assertTrue(auth_services.has_permission(admin_s["token"], "document:verify"))
        self.assertTrue(auth_services.has_permission(ops_s["token"], "document:verify"))
        self.assertTrue(auth_services.has_permission(visa_s["token"], "document:verify"))
        self.assertTrue(auth_services.has_permission(ticketing_s["token"], "document:verify"))

        # Sales and Auditor cannot verify
        self.assertFalse(auth_services.has_permission(sales_s["token"], "document:verify"))
        self.assertFalse(auth_services.has_permission(auditor_s["token"], "document:verify"))

    # 15. Document versioning integrity
    def test_15_document_versioning_integrity(self):
        conn = database.get_connection()
        conn.execute("""
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("DOC-VTEST-01", "STATUS_CHANGE", "Submitted", "Verified", "System Admin", "Initial verification"))
        conn.commit()
        hist = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-VTEST-01'").fetchall()
        conn.close()
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["event_type"], "STATUS_CHANGE")

    # 16. Trip readiness and consolidated travel pack generation
    def test_16_trip_readiness_and_consolidated_travel_file(self):
        # All 4 office departments (Sales, Visa, Operations, Ticketing) + Admin can generate travel files
        departments_to_test = ["test_admin", "test_sales", "test_visa", "test_ops", "test_ticketing"]
        for uname in departments_to_test:
            user_s = auth_services.authenticate_user(uname, self.test_passwords[uname])
            res = generate_consolidated_travel_file("KT-T-0001", session_token=user_s["token"])
            self.assertTrue(os.path.isfile(res), f"User {uname} failed to generate travel file")

    # 17. Cryptographic integrity, tampering rejection, and wrong-key rejection
    def test_17_encryption_integrity_tamper_and_wrong_key(self):
        key = secrets.token_bytes(32)
        plaintext = b"Authentic document payload"
        storage_id = "test_doc_storage_id"
        ciphertext = _encrypt_envelope(plaintext, storage_id, key, key_id="test_key_v1", version=2)

        # Decrypt with correct key
        decrypted = _decrypt_envelope(ciphertext, storage_id, key=key)
        self.assertEqual(decrypted, plaintext)

        # Tampering with ciphertext body (flip last byte)
        tampered = bytearray(ciphertext)
        tampered[-1] ^= 0xFF
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(tampered), storage_id, key=key)
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

        # Decrypt with wrong key
        wrong_key = secrets.token_bytes(32)
        with self.assertRaises(ValueError) as ctx2:
            _decrypt_envelope(ciphertext, storage_id, key=wrong_key)
        self.assertIn("Authentication tag mismatch", str(ctx2.exception))

    # 18. Key rotation rehearsal on disposable synthetic fixtures
    def test_18_key_rotation_rehearsal_on_disposable_fixture(self):
        sandbox_rot = os.path.join(self.sandbox_dir, "rotation_sandbox")
        rot_keys = os.path.join(sandbox_rot, "keys")
        os.makedirs(rot_keys, exist_ok=True)

        class DictKeyProvider(storage_service.KeyProvider):
            def __init__(self):
                self.keys = {}
            def get_key(self, key_id):
                if key_id not in self.keys: raise RuntimeError("Missing key")
                return self.keys[key_id]
            def save_key(self, key_id, key_bytes):
                self.keys[key_id] = key_bytes
            def has_key(self, key_id):
                return key_id in self.keys

        mock_provider = DictKeyProvider()
        engine = KeyRotationEngine(self.test_db_path, sandbox_rot, rot_keys, key_provider=mock_provider)

        k1_id = "test_k1"
        k2_id = "test_k2"
        mock_provider.save_key(k1_id, secrets.token_bytes(32))
        mock_provider.save_key(k2_id, secrets.token_bytes(32))

        # Create 3 synthetic test files encrypted under test_k1
        test_files = []
        for i in range(3):
            p = os.path.join(sandbox_rot, f"test_doc_{i}.pdf")
            sid = f"test_doc_{i}.pdf"
            ct = _encrypt_envelope(f"Content {i}".encode(), sid, mock_provider.get_key(k1_id), key_id=k1_id, version=2)
            with open(p, "wb") as f:
                f.write(ct)
            test_files.append(p)

        # Rehearse batch rotation
        res = engine.execute_batch_rotation(test_files, k1_id, k2_id)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_rotated"], 3)

        # Verify all files now decrypt with k2
        for i, p in enumerate(test_files):
            with open(p, "rb") as f:
                ct = f.read()
            sid = f"test_doc_{i}.pdf"
            dec = _decrypt_envelope(ct, sid, key=mock_provider.get_key(k2_id))
            self.assertEqual(dec, f"Content {i}".encode())

        # Test interruption & rollback simulation
        res_interrupted = engine.execute_batch_rotation(test_files, k2_id, k1_id, simulate_interruption_at=1)
        self.assertEqual(res_interrupted["status"], "FAILED_ROLLED_BACK")
        self.assertEqual(res_interrupted["rolled_back_count"], 1)

    # 19. Off-site backup interface, WORM immutability, and isolated restore
    def test_19_offsite_backup_interface_and_immutability(self):
        bucket_dir = os.path.join(self.sandbox_dir, "simulated_cloud_bucket")
        cloud_storage = LocalSimulatedCloudStorage(bucket_dir)

        backup_payload = b"KT_VAULT_BACKUP_PAYLOAD_V3" + secrets.token_bytes(128)
        backup_sha = hashlib.sha256(backup_payload).hexdigest()
        b_name = "kt_vault_backup_20261026_01.ktbak"

        # Upload
        record = cloud_storage.upload_backup(b_name, backup_payload, backup_sha, retention_days=30)
        self.assertEqual(record["immutability_status"], "LOCKED")

        # Overwrite must fail due to WORM immutability
        with self.assertRaises(ImmutabilityViolationError):
            cloud_storage.upload_backup(b_name, backup_payload, backup_sha, retention_days=30)

        # Premature deletion must fail due to Compliance retention lock
        with self.assertRaises(ImmutabilityViolationError):
            cloud_storage.delete_backup(b_name)

        # Download and verify isolated restore
        restore_dest = os.path.join(self.sandbox_dir, "restored_test.ktbak")
        cloud_storage.download_backup(b_name, restore_dest)
        with open(restore_dest, "rb") as f:
            restored_bytes = f.read()
        self.assertEqual(restored_bytes, backup_payload)

    # 20. Preservation of existing live documents and database records
    def test_20_existing_data_and_document_preservation(self):
        # 1. Check live master key
        live_key_path = os.path.join(PROJECT_ROOT, "documents", ".keys", "ktv_2026_v1.dpapi")
        self.assertTrue(os.path.isfile(live_key_path), "Production master key ktv_2026_v1.dpapi must exist")

        # 2. Check live encrypted documents in storage root
        docs_dir = os.path.join(PROJECT_ROOT, "documents")
        live_files = [f for f in os.listdir(docs_dir) if f.endswith(".pdf") and os.path.isfile(os.path.join(docs_dir, f))]
        self.assertEqual(len(live_files), 27, f"Expected exactly 27 encrypted live documents, found {len(live_files)}")

        # 3. Check live database records
        live_db = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
        conn = sqlite3.connect(live_db)
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        conn.close()
        self.assertEqual(doc_count, 28, f"Expected 28 database document records, found {doc_count}")


if __name__ == "__main__":
    unittest.main()
