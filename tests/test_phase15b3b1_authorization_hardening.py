import unittest
import os
import sys
import tempfile
import shutil
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import database
import auth_services
import storage_service
from storage_service import (
    StaticKeyProvider,
    write_encrypted_file,
    read_decrypted_document,
    is_encrypted_file
)
import services
import travel_file_generator


class TestPhase15B3B1AuthorizationHardening(unittest.TestCase):
    """
    Focused Security Test Suite for Phase 15B-3B.1:
    Mandatory Authenticated Document-Access Boundary.
    
    Verifies:
    1. Enforcement of authenticated session tokens on all document reads.
    2. Rejection of missing, empty, forged, and expired tokens.
    3. Strict RBAC role enforcement (Staff, Supervisor, Admin, Unauthorized).
    4. Fail-closed tamper detection (zero plaintext on integrity tag or ciphertext failure).
    5. Shared physical document reads with canonical AAD.
    6. Cross-customer document isolation and preview/download flows.
    7. Storage service integration in services.py, document review, and travel pack generator.
    8. Complete isolation: zero mutations to live database or live documents.
    """

    @classmethod
    def setUpClass(cls):
        # 1. Capture live database checksum and row counts for verification
        cls.live_db_path = database.DB_PATH
        cls.live_db_hash = cls._hash_file(cls.live_db_path)
        cls.live_docs_dir = os.path.realpath(os.path.join(project_root, "documents"))
        cls.live_docs_count = len(os.listdir(cls.live_docs_dir)) if os.path.exists(cls.live_docs_dir) else 0

        conn_live = sqlite3.connect(cls.live_db_path)
        cls.live_activity_count = conn_live.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
        cls.live_sessions_count = conn_live.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn_live.close()

        # 2. Create isolated test sandbox
        cls.temp_dir = tempfile.mkdtemp(prefix="kt_test_phase15b3b1_")
        cls.test_db_dir = os.path.join(cls.temp_dir, "data")
        os.makedirs(cls.test_db_dir, exist_ok=True)
        cls.test_db_path = os.path.join(cls.test_db_dir, "kt_vault_v3.db")
        shutil.copyfile(cls.live_db_path, cls.test_db_path)

        cls.test_docs_dir = os.path.join(cls.temp_dir, "documents")
        os.makedirs(cls.test_docs_dir, exist_ok=True)

        # Redirect database to test database
        database.DB_PATH = cls.test_db_path

        # Setup test encryption key
        cls.test_key = secrets.token_bytes(32)
        cls.key_provider = StaticKeyProvider(cls.test_key)
        storage_service.set_key_provider(cls.key_provider)

        # 3. Create test users & sessions in isolated test database
        conn = sqlite3.connect(cls.test_db_path)
        conn.row_factory = sqlite3.Row

        # Create active sessions
        cls.staff_token = "test_staff_token_" + secrets.token_hex(16)
        cls.supervisor_token = "test_supervisor_token_" + secrets.token_hex(16)
        cls.admin_token = "test_admin_token_" + secrets.token_hex(16)
        cls.expired_token = "test_expired_token_" + secrets.token_hex(16)
        cls.unauth_token = "test_unauth_token_" + secrets.token_hex(16)

        user_staff = conn.execute("SELECT id FROM users WHERE role = 'Staff'").fetchone()
        user_sup = conn.execute("SELECT id FROM users WHERE role = 'Supervisor'").fetchone()
        user_admin = conn.execute("SELECT id FROM users WHERE role = 'Admin'").fetchone()

        valid_future = (datetime.now() + timedelta(hours=8)).isoformat()
        expired_past = (datetime.now() - timedelta(hours=2)).isoformat()

        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.staff_token, user_staff['id'], valid_future))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.supervisor_token, user_sup['id'], valid_future))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.admin_token, user_admin['id'], valid_future))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.expired_token, user_staff['id'], expired_past))

        # Insert custom user with unauthorized role 'Guest'
        guest_salt = secrets.token_bytes(16)
        guest_hash = hashlib.pbkdf2_hmac('sha256', b"guestpass", guest_salt, 100000)
        conn.execute(
            "INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
            ("USR-GUEST", "guest_user", guest_hash, guest_salt, "Guest User", "Guest")
        )
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.unauth_token, "USR-GUEST", valid_future))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        # Restore database configuration
        database.DB_PATH = cls.live_db_path
        storage_service.reset_key_provider()

        # Remove sandbox directory
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

        # Confirm live database was not touched
        current_live_hash = cls._hash_file(cls.live_db_path)
        assert cls.live_db_hash == current_live_hash, "CRITICAL ERROR: Live database was modified during test run!"

        conn_live = sqlite3.connect(cls.live_db_path)
        cur_act = conn_live.execute("SELECT COUNT(*) FROM activity").fetchone()[0]
        cur_sess = conn_live.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        conn_live.close()

        assert cur_act == cls.live_activity_count, f"Activity count changed: {cur_act} != {cls.live_activity_count}"
        assert cur_sess == cls.live_sessions_count, f"Sessions count changed: {cur_sess} != {cls.live_sessions_count}"

    @staticmethod
    def _hash_file(filepath):
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    # -----------------------------------------------------------------
    # 1. Missing and Empty Session Tokens
    # -----------------------------------------------------------------
    def test_01_missing_session_token_rejected(self):
        """Document read without session token must fail closed with PermissionError."""
        res = write_encrypted_file("doc1.pdf", b"Secret Passport Data", base_dir=self.test_docs_dir)
        with self.assertRaises(PermissionError) as ctx:
            read_decrypted_document(res["file_path"], base_dir=self.test_docs_dir)
        self.assertIn("session token is required", str(ctx.exception))

    def test_02_empty_and_whitespace_session_token_rejected(self):
        """Document read with empty or whitespace token must fail closed with PermissionError."""
        res = write_encrypted_file("doc2.pdf", b"Confidential Visa", base_dir=self.test_docs_dir)
        for empty_val in ["", "   ", "\t\n", None]:
            with self.assertRaises(PermissionError):
                read_decrypted_document(res["file_path"], session_token=empty_val, base_dir=self.test_docs_dir)

    # -----------------------------------------------------------------
    # 2. Invalid and Expired Sessions
    # -----------------------------------------------------------------
    def test_03_invalid_forged_session_token_rejected(self):
        """Document read with forged or non-existent token must be rejected."""
        res = write_encrypted_file("doc3.pdf", b"Private Insurance", base_dir=self.test_docs_dir)
        with self.assertRaises(PermissionError) as ctx:
            read_decrypted_document(
                res["file_path"],
                session_token="forged_token_0000000000000000",
                base_dir=self.test_docs_dir
            )
        self.assertIn("Invalid or expired session", str(ctx.exception))

    def test_04_expired_session_token_rejected_and_purged(self):
        """Expired session token must be rejected and purged from database."""
        res = write_encrypted_file("doc4.pdf", b"Flight Confirmation", base_dir=self.test_docs_dir)
        with self.assertRaises(PermissionError) as ctx:
            read_decrypted_document(
                res["file_path"],
                session_token=self.expired_token,
                base_dir=self.test_docs_dir
            )
        self.assertIn("Invalid or expired session", str(ctx.exception))

        # Confirm session was deleted from test sessions table
        conn = database.get_connection()
        sess = conn.execute("SELECT * FROM sessions WHERE token = ?", (self.expired_token,)).fetchone()
        conn.close()
        self.assertIsNone(sess, "Expired session should have been purged upon validation.")

    # -----------------------------------------------------------------
    # 3. Unauthorized Document Access (Role Enforcement)
    # -----------------------------------------------------------------
    def test_05_unauthorized_role_rejected(self):
        """Session with unauthorized role ('Guest') must be rejected."""
        res = write_encrypted_file("doc5.pdf", b"Restricted Voucher", base_dir=self.test_docs_dir)
        with self.assertRaises(PermissionError) as ctx:
            read_decrypted_document(
                res["file_path"],
                session_token=self.unauth_token,
                allowed_roles=["Staff", "Supervisor", "Admin"],
                base_dir=self.test_docs_dir
            )
        self.assertIn("Unauthorized: Requires one of", str(ctx.exception))

    # -----------------------------------------------------------------
    # 4. Valid Authenticated Access
    # -----------------------------------------------------------------
    def test_06_valid_authenticated_staff_read(self):
        """Authorized Staff session must successfully decrypt and read document."""
        payload = b"%PDF-1.4\nSynthetic Flight Ticket Details"
        res = write_encrypted_file("staff_doc.pdf", payload, base_dir=self.test_docs_dir)
        data = read_decrypted_document(res["file_path"], session_token=self.staff_token, base_dir=self.test_docs_dir)
        self.assertEqual(data, payload)

    def test_07_valid_authenticated_supervisor_read(self):
        """Authorized Supervisor session must successfully decrypt and read document."""
        payload = b"%PDF-1.4\nSupervisor Approved Itinerary"
        res = write_encrypted_file("supervisor_doc.pdf", payload, base_dir=self.test_docs_dir)
        data = read_decrypted_document(res["file_path"], session_token=self.supervisor_token, base_dir=self.test_docs_dir)
        self.assertEqual(data, payload)

    def test_08_valid_authenticated_admin_read(self):
        """Authorized Admin session must successfully decrypt and read document."""
        payload = b"%PDF-1.4\nAdmin Master Document"
        res = write_encrypted_file("admin_doc.pdf", payload, base_dir=self.test_docs_dir)
        data = read_decrypted_document(res["file_path"], session_token=self.admin_token, base_dir=self.test_docs_dir)
        self.assertEqual(data, payload)

    # -----------------------------------------------------------------
    # 5. Tampered Ciphertext & Authentication-Tag Failures (Fail-Closed)
    # -----------------------------------------------------------------
    def test_09_tampered_ciphertext_fails_closed(self):
        """Modifying 1 byte of ciphertext must fail integrity check with zero plaintext return."""
        payload = b"CRITICAL_PASSPORT_PAYLOAD_12345678"
        res = write_encrypted_file("tamper_ct.pdf", payload, base_dir=self.test_docs_dir)
        target_path = res["file_path"]

        with open(target_path, "rb") as f:
            enc_data = bytearray(f.read())

        # Flip byte at offset 40 (inside ciphertext)
        enc_data[40] ^= 0xFF
        with open(target_path, "wb") as f:
            f.write(enc_data)

        with self.assertRaises(ValueError) as ctx:
            read_decrypted_document(target_path, session_token=self.staff_token, base_dir=self.test_docs_dir)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    def test_10_tampered_auth_tag_fails_closed(self):
        """Modifying 1 byte of the 16-byte authentication tag must fail verification."""
        payload = b"HOTEL_VOUCHER_SENSITIVE_RESERVATION"
        res = write_encrypted_file("tamper_tag.pdf", payload, base_dir=self.test_docs_dir)
        target_path = res["file_path"]

        with open(target_path, "rb") as f:
            enc_data = bytearray(f.read())

        # Flip byte at offset 20 (inside tag, offset 18..33)
        enc_data[20] ^= 0x01
        with open(target_path, "wb") as f:
            f.write(enc_data)

        with self.assertRaises(ValueError) as ctx:
            read_decrypted_document(target_path, session_token=self.supervisor_token, base_dir=self.test_docs_dir)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    # -----------------------------------------------------------------
    # 6. Shared Physical Files
    # -----------------------------------------------------------------
    def test_11_shared_physical_files_authorized_read(self):
        """Shared physical document can be decrypted by multiple records using canonical storage ID."""
        shared_filename = "shared_intake_a9254ef9.pdf"
        content = b"Shared Flight Ticket for Amit and Neha"
        res = write_encrypted_file(
            shared_filename,
            content,
            file_storage_id=shared_filename,
            base_dir=self.test_docs_dir
        )

        # Both records can read using valid sessions and matching canonical storage ID
        doc1 = read_decrypted_document(
            res["file_path"],
            session_token=self.staff_token,
            file_storage_id=shared_filename,
            base_dir=self.test_docs_dir
        )
        self.assertEqual(doc1, content)

        doc2 = read_decrypted_document(
            res["file_path"],
            session_token=self.supervisor_token,
            file_storage_id=shared_filename,
            base_dir=self.test_docs_dir
        )
        self.assertEqual(doc2, content)

    # -----------------------------------------------------------------
    # 7. Document Preview and Download Authorization Boundary
    # -----------------------------------------------------------------
    def test_12_preview_download_requires_authentication(self):
        """get_document_for_download_or_preview rejects unauthenticated callers."""
        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview("DOC-0001", "KT-C-0001", session_token=None)

        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview("DOC-0001", "KT-C-0001", session_token="")

        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview("DOC-0001", "KT-C-0001", session_token="forged_token")

    def test_13_preview_download_cross_customer_rejection(self):
        """get_document_for_download_or_preview strictly rejects cross-customer access."""
        # Find an existing document for KT-C-0001
        conn = database.get_connection()
        doc = conn.execute('''
            SELECT d.id FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            JOIN trips t ON r.trip_id = t.id
            WHERE t.customer_id = 'KT-C-0001' LIMIT 1
        ''').fetchone()
        conn.close()

        if doc:
            doc_id = doc['id']
            # Attempt to access doc_id using customer KT-C-0002
            with self.assertRaises(PermissionError) as ctx:
                services.get_document_for_download_or_preview(
                    doc_id,
                    customer_id='KT-C-0002',
                    session_token=self.staff_token
                )
            self.assertIn("Security violation", str(ctx.exception))

    def test_14_preview_download_success_flow(self):
        """Authorized download returns verified bytes, MIME type, and safe filename."""
        conn = database.get_connection()
        doc = conn.execute('''
            SELECT d.id, d.file_path, t.customer_id FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            JOIN trips t ON r.trip_id = t.id
            WHERE d.status = 'Verified' LIMIT 1
        ''').fetchone()

        if doc:
            filename = os.path.basename(doc['file_path'])
            doc_file = os.path.join(self.test_docs_dir, filename)
            with open(doc_file, 'wb') as f:
                f.write(b"%PDF-1.4\nTest Verified Document Content")

            conn.execute("UPDATE documents SET file_path = ? WHERE id = ?", (f"documents/{filename}", doc['id']))
            conn.commit()
            conn.close()

            result = services.get_document_for_download_or_preview(
                doc['id'],
                customer_id=doc['customer_id'],
                session_token=self.staff_token,
                action='download'
            )
            self.assertIn("file_bytes", result)
            self.assertIn("mime_type", result)
            self.assertIn("file_name", result)
            self.assertGreater(len(result["file_bytes"]), 0)
        else:
            conn.close()

    # -----------------------------------------------------------------
    # 8. save_document Authentication & Storage Integration
    # -----------------------------------------------------------------
    def test_15_save_document_requires_valid_session(self):
        """save_document rejects missing/invalid session tokens."""
        dummy_file = os.path.join(self.test_docs_dir, "test_save.pdf")
        with open(dummy_file, "wb") as f:
            f.write(b"%PDF-1.4\nTest Document Content")

        with self.assertRaises(PermissionError):
            services.save_document("REQ-T-01", dummy_file, {"Note": "Test"}, session_token=None)

        with self.assertRaises(PermissionError):
            services.save_document("REQ-T-01", dummy_file, {"Note": "Test"}, session_token="forged_token")

    # -----------------------------------------------------------------
    # 9. recover_verified_document_data Authorization
    # -----------------------------------------------------------------
    def test_16_recover_verified_document_data_role_enforcement(self):
        """recover_verified_document_data requires Supervisor or Admin; Staff is rejected."""
        conn = database.get_connection()
        doc = conn.execute("SELECT id, file_path FROM documents WHERE status = 'Verified' LIMIT 1").fetchone()
        conn.close()

        if doc:
            doc_id = doc['id']
            # Staff attempt must be rejected with PermissionError
            with self.assertRaises(PermissionError) as ctx:
                services.recover_verified_document_data(
                    doc_id=doc_id,
                    recovered_data={"Full Name": "Test Rec"},
                    reason="Supervised test recovery",
                    session_token=self.staff_token
                )
            self.assertIn("Unauthorized: Requires one of ['Supervisor', 'Admin']", str(ctx.exception))

    # -----------------------------------------------------------------
    # 10. Travel File Generation Authorization
    # -----------------------------------------------------------------
    def test_17_generate_consolidated_travel_file_role_enforcement(self):
        """generate_consolidated_travel_file allows office staff, supervisors, and admins; unauthorized roles and unauthenticated requests are rejected."""
        with self.assertRaises(PermissionError):
            travel_file_generator.generate_consolidated_travel_file("KT-T-0001", session_token=None)

        with self.assertRaises(PermissionError):
            travel_file_generator.generate_consolidated_travel_file("KT-T-0001", session_token=self.unauth_token)

        # In Phase 16, office staff (Sales/Staff, Supervisor, Admin) are authorized per business rule 5
        res = travel_file_generator.generate_consolidated_travel_file("KT-T-0001", session_token=self.staff_token)
        self.assertTrue(os.path.isfile(res))

    # -----------------------------------------------------------------
    # 11. Transitional Plaintext Reading Requires Authentication
    # -----------------------------------------------------------------
    def test_18_transitional_plaintext_requires_authentication(self):
        """Unencrypted legacy file on disk cannot be read without valid authenticated session."""
        plain_file = os.path.join(self.test_docs_dir, "legacy_unencrypted.pdf")
        plain_content = b"%PDF-1.4\nLegacy unencrypted document content"
        with open(plain_file, "wb") as f:
            f.write(plain_content)

        self.assertFalse(is_encrypted_file(plain_file, base_dir=self.test_docs_dir))

        # Unauthenticated read MUST be rejected
        with self.assertRaises(PermissionError):
            read_decrypted_document(plain_file, base_dir=self.test_docs_dir)

        # Forged token MUST be rejected
        with self.assertRaises(PermissionError):
            read_decrypted_document(plain_file, session_token="forged_token", base_dir=self.test_docs_dir)

        # Authenticated Staff session CAN read transitional plaintext
        read_bytes = read_decrypted_document(plain_file, session_token=self.staff_token, base_dir=self.test_docs_dir)
        self.assertEqual(read_bytes, plain_content)

    # -----------------------------------------------------------------
    # 12. Path Traversal Rejection
    # -----------------------------------------------------------------
    def test_19_path_traversal_rejected_regardless_of_authentication(self):
        """Path traversal sequence must be rejected even with valid Admin session."""
        traversal_path = os.path.join(self.test_docs_dir, "..", "data", "kt_vault_v3.db")
        with self.assertRaises(PermissionError) as ctx:
            read_decrypted_document(traversal_path, session_token=self.admin_token, base_dir=self.test_docs_dir)
        self.assertIn("Access denied", str(ctx.exception))

    # -----------------------------------------------------------------
    # 13. System Context Offline Support
    # -----------------------------------------------------------------
    def test_20_system_context_offline_support(self):
        """system_context=True allows internal offline maintenance tools without user session."""
        payload = b"%PDF-1.4\nOffline maintenance data"
        res = write_encrypted_file("system_doc.pdf", payload, base_dir=self.test_docs_dir)
        data = read_decrypted_document(res["file_path"], system_context=True, base_dir=self.test_docs_dir)
        self.assertEqual(data, payload)


if __name__ == '__main__':
    unittest.main()
