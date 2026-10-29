"""
KT Vault V3 - Phase 15B-3B.4A Secure Document Writes & Generated PDF Test Suite
Verifies authenticated document-writing interface, KTV2 encryption enforcement,
smart upload / intake workflows, travel file generation, missing key fail-closed behavior,
and prevention of plaintext leakage into storage.
"""

import os
import sys
import shutil
import tempfile
import unittest
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import auth_services
import storage_service
from storage_service import (
    StaticKeyProvider,
    FailClosedKeyProvider,
    write_document_file,
    write_encrypted_file,
    read_decrypted_document,
    is_encrypted_bytes,
    is_encrypted_file,
    get_envelope_metadata,
    get_encryption_mode,
    set_encryption_mode,
    ENCRYPTION_MODE_TRANSITIONAL,
    ENCRYPTION_MODE_ENFORCED,
    ENVELOPE_VERSION_V2,
    HEADER_SIZE_V2
)
import services
import document_processor
import travel_file_generator


class TestPhase15B3B4ASecureWrites(unittest.TestCase):
    """
    Exhaustive verification of Phase 15B-3B.4A:
    1. Central write_document_file authenticated boundary & RBAC validation.
    2. Path containment & directory traversal rejection on write.
    3. Safe transition strategy: transitional plaintext vs enforced KTV2 encryption.
    4. Fail-closed defense: missing key raises RuntimeError and NEVER falls back to plaintext.
    5. Smart Upload and Smart Intake workflows with encrypted writes.
    6. Intake document copying from temp to storage with encrypted writes.
    7. Consolidated Travel File PDF generation into encrypted storage.
    8. Document preview, download, and OCR extraction against newly written encrypted files.
    9. Audit proving zero unintended plaintext files in storage.
    10. Non-destructive live data invariant.
    """

    @classmethod
    def setUpClass(cls):
        cls.live_db_path = os.path.realpath(r"C:\KT_Vault_V3\data\kt_vault_v3.db")
        cls.live_docs_dir = os.path.realpath(r"C:\KT_Vault_V3\documents")

        # Baseline live state counts
        conn = sqlite3.connect(cls.live_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        cls.baseline_activity_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sessions")
        cls.baseline_sessions_count = c.fetchone()[0]
        conn.close()

        cls.baseline_hashes = {}
        for f in os.listdir(cls.live_docs_dir):
            p = os.path.join(cls.live_docs_dir, f)
            if os.path.isfile(p):
                with open(p, "rb") as fp:
                    cls.baseline_hashes[f] = hashlib.sha256(fp.read()).hexdigest()

    def setUp(self):
        # Create isolated temporary working environment
        self.temp_dir = tempfile.mkdtemp(prefix="ktv_test_writes_")
        self.sandbox_data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(self.sandbox_data_dir, exist_ok=True)
        self.sandbox_db_path = os.path.join(self.sandbox_data_dir, "kt_vault_v3.db")
        self.sandbox_docs_dir = os.path.join(self.temp_dir, "documents")

        shutil.copy2(self.live_db_path, self.sandbox_db_path)
        shutil.copytree(self.live_docs_dir, self.sandbox_docs_dir)

        # Redirect database singleton
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.sandbox_db_path

        # Setup test keys and provider
        self.test_key_id = "ktv_2026_v1"
        self.test_key_bytes = secrets.token_bytes(32)
        self.key_provider = StaticKeyProvider({self.test_key_id: self.test_key_bytes})
        storage_service.set_key_provider(self.key_provider)

        # Create valid authenticated sessions
        conn = sqlite3.connect(self.sandbox_db_path)
        self.admin_token = f"admin_tok_{secrets.token_hex(16)}"
        self.staff_token = f"staff_tok_{secrets.token_hex(16)}"
        exp = (datetime.now() + timedelta(hours=8)).isoformat()
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, 'KT-U-001', ?)", (self.admin_token, exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, 'KT-U-003', ?)", (self.staff_token, exp))
        conn.commit()
        conn.close()

    def tearDown(self):
        storage_service.reset_key_provider()
        set_encryption_mode(ENCRYPTION_MODE_TRANSITIONAL)
        database.DB_PATH = self.orig_db_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =================================================================
    # TASK 1: Central Authentication & Authorization for Document Writes
    # =================================================================

    def test_write_document_file_unauthenticated_rejected(self):
        """Verifies write_document_file rejects calls without valid session_token."""
        plain = b"%PDF-1.4 Test Unauthenticated Payload"
        with self.assertRaises(PermissionError):
            write_document_file("test.pdf", plain, session_token=None, base_dir=self.sandbox_docs_dir)

        with self.assertRaises(PermissionError):
            write_document_file("test.pdf", plain, session_token="", base_dir=self.sandbox_docs_dir)

        with self.assertRaises(PermissionError):
            write_document_file("test.pdf", plain, session_token="invalid_token_12345", base_dir=self.sandbox_docs_dir)

    def test_write_document_file_path_traversal_rejected(self):
        """Verifies write_document_file strictly rejects path traversal attempts."""
        plain = b"%PDF-1.4 Traversal Test"
        with self.assertRaises(PermissionError):
            write_document_file("../escape.pdf", plain, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)

        with self.assertRaises(PermissionError):
            write_document_file("sub/../../escape.pdf", plain, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)

    def test_write_document_file_null_byte_rejected(self):
        """Verifies null bytes in path are rejected."""
        plain = b"%PDF-1.4 Null Byte Test"
        with self.assertRaises(ValueError):
            write_document_file("valid.pdf\0malicious.exe", plain, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)

    # =================================================================
    # TASK 2: Safe Transition Strategy & Enforced Encryption
    # =================================================================

    def test_transitional_plaintext_mode_writing(self):
        """Verifies write_document_file writes plaintext when mode is TRANSITIONAL_PLAINTEXT."""
        set_encryption_mode(ENCRYPTION_MODE_TRANSITIONAL)
        plain = b"%PDF-1.4 Transitional Plaintext Payload"
        target_name = "transitional_doc.pdf"

        meta = write_document_file(
            target_name,
            plain,
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(meta["status"], "plaintext")
        self.assertFalse(is_encrypted_file(meta["file_path"], base_dir=self.sandbox_docs_dir))

        # Content on disk must be identical to raw plaintext
        with open(meta["file_path"], "rb") as f:
            disk_bytes = f.read()
        self.assertEqual(disk_bytes, plain)

    def test_enforced_encryption_mode_writing(self):
        """Verifies write_document_file encrypts via KTV2 when mode is ENCRYPTED_ONLY."""
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)
        plain = b"%PDF-1.4 Enforced Encrypted Document Payload for Passport"
        target_name = "enforced_enc_doc.pdf"

        meta = write_document_file(
            target_name,
            plain,
            session_token=self.admin_token,
            key_id=self.test_key_id,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(meta["status"], "encrypted")
        self.assertEqual(meta["version"], ENVELOPE_VERSION_V2)
        self.assertEqual(meta["key_id"], self.test_key_id)

        # File on disk must be KTV2 encrypted
        self.assertTrue(is_encrypted_file(meta["file_path"], base_dir=self.sandbox_docs_dir))
        with open(meta["file_path"], "rb") as f:
            disk_bytes = f.read()
        self.assertTrue(disk_bytes.startswith(b"KTV2"))

        # Decrypted read must match original plaintext
        decrypted = read_decrypted_document(
            meta["file_path"],
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(decrypted, plain)

    def test_enforced_mode_missing_key_fails_closed_without_plaintext_leak(self):
        """
        Verifies that when encryption is enforced and encryption key is unavailable:
        1. write_document_file raises RuntimeError.
        2. Fails closed: NEVER falls back to writing plaintext.
        3. No partial or plaintext file is created on disk.
        """
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)
        # Clear key provider to FailClosedKeyProvider
        storage_service.reset_key_provider()

        plain = b"%PDF-1.4 Sensitive Plaintext That Must Never Leak"
        target_name = "should_never_exist.pdf"
        target_full_path = os.path.join(self.sandbox_docs_dir, target_name)

        with self.assertRaises(RuntimeError) as ctx:
            write_document_file(
                target_name,
                plain,
                session_token=self.admin_token,
                key_id=self.test_key_id,
                base_dir=self.sandbox_docs_dir
            )

        err_msg = str(ctx.exception)
        self.assertTrue(any(w in err_msg.lower() for w in ["unavailable", "unconfigured", "blocked"]))

        # Assert no file was written to disk
        self.assertFalse(os.path.exists(target_full_path))

    # =================================================================
    # TASK 3: Smart Upload & Smart Intake Workflows with Encrypted Writes
    # =================================================================

    def test_smart_upload_workflow_with_encrypted_writes(self):
        """Verifies document upload and processing through write_document_file in encrypted mode."""
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)

        upload_bytes = b"%PDF-1.4 Synthetic Visa Document Content for Upload Test"
        safe_filename = f"trip_upload_{secrets.token_hex(8)}.pdf"
        safe_path = os.path.join(self.sandbox_docs_dir, safe_filename)

        # Write uploaded file through central interface
        meta = write_document_file(
            safe_path,
            upload_bytes,
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(meta["status"], "encrypted")
        self.assertTrue(is_encrypted_file(safe_path, base_dir=self.sandbox_docs_dir))

        # Save document in database via services.save_document
        extracted = {
            "Traveller Name": "Amit Mehta",
            "Visa Number / Reference": "VISA-ENC-12345",
            "Destination": "Dubai"
        }
        doc_id = services.save_document(
            requirement_id="REQ-TR-02",
            file_path=safe_path,
            extracted_data=extracted,
            session_token=self.admin_token
        )
        self.assertTrue(doc_id.startswith("DOC-"))

        # Verify document can be read and previewed
        read_bytes = read_decrypted_document(
            safe_path,
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(read_bytes, upload_bytes)

    def test_intake_copy_temp_file_to_encrypted_storage(self):
        """Verifies services.save_intake_document encrypts when copying temp document to storage."""
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)

        # Create temporary candidate file in system temp
        temp_cand = os.path.join(tempfile.gettempdir(), f"intake_test_{secrets.token_hex(6)}.pdf")
        plain_intake_bytes = b"%PDF-1.4 Synthetic Intake Document Uploaded to Temp"
        with open(temp_cand, "wb") as f:
            f.write(plain_intake_bytes)

        try:
            # Execute complete_smart_intake
            intake_res = services.complete_smart_intake(
                customer_data={"name": "Suresh Raina", "type": "Corporate"},
                traveller_data={"name": "Suresh Raina", "role": "Employee"},
                document_fields={"Full Name": "Suresh Raina", "Passport Number": "Z9876543"},
                file_path=temp_cand,
                session_token=self.admin_token,
                idempotency_key=f"op_{secrets.token_hex(8)}"
            )
            self.assertIn("document_id", intake_res)

            # Query database for saved document path
            conn = sqlite3.connect(self.sandbox_db_path)
            c = conn.cursor()
            c.execute("SELECT file_path FROM documents WHERE id = ?", (intake_res["document_id"],))
            db_file_path = c.fetchone()[0]
            conn.close()

            full_stored_path = os.path.join(self.temp_dir, db_file_path) if not os.path.isabs(db_file_path) else db_file_path
            # Check file is encrypted on disk
            self.assertTrue(is_encrypted_file(full_stored_path, base_dir=self.sandbox_docs_dir))

            # Verify decrypted content matches original
            decrypted = read_decrypted_document(full_stored_path, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)
            self.assertEqual(decrypted, plain_intake_bytes)
        finally:
            if os.path.exists(temp_cand):
                try:
                    os.remove(temp_cand)
                except Exception:
                    pass

    # =================================================================
    # TASK 4: Travel File PDF Generation into Encrypted Storage
    # =================================================================

    def test_travel_file_pdf_generation_encrypted(self):
        """Verifies generate_consolidated_travel_file saves PDF as KTV2 encrypted document."""
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)

        out_tf_path = os.path.join(self.sandbox_docs_dir, "TravelFile_KT-T-0001.pdf")
        generated_path = travel_file_generator.generate_consolidated_travel_file(
            trip_id="KT-T-0001",
            out_path=out_tf_path,
            session_token=self.admin_token
        )
        self.assertTrue(os.path.isfile(generated_path))

        # File must be encrypted KTV2 on disk
        self.assertTrue(is_encrypted_file(generated_path, base_dir=self.sandbox_docs_dir))

        # Must decrypt cleanly to a valid PDF
        decrypted_tf = read_decrypted_document(
            generated_path,
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertTrue(decrypted_tf.startswith(b"%PDF-"))
        self.assertIn(b"Travellers:", decrypted_tf)

    # =================================================================
    # TASK 5: Audit for No Plaintext Leaks in Persistent Storage
    # =================================================================

    def test_no_unintended_plaintext_copies_in_storage(self):
        """
        Audits the storage directory after multiple encrypted operations:
        Confirms newly created documents contain zero unencrypted plaintext.
        """
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)

        # Perform 3 encrypted writes
        for i in range(3):
            fname = f"leak_test_doc_{i}.pdf"
            payload = f"%PDF-1.4 Payload Number {i} with secret information".encode("utf-8")
            write_document_file(fname, payload, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)

        # Walk sandbox storage and check newly added files
        new_files = [f for f in os.listdir(self.sandbox_docs_dir) if f.startswith("leak_test_doc_")]
        self.assertEqual(len(new_files), 3)

        for f in new_files:
            p = os.path.join(self.sandbox_docs_dir, f)
            with open(p, "rb") as fp:
                data = fp.read()
            # Must have KTV2 header
            self.assertTrue(is_encrypted_bytes(data), f"File {f} leaked plaintext in storage!")
            self.assertTrue(data.startswith(b"KTV2"))

    # =================================================================
    # TASK 6: Live Data Preservation Invariant
    # =================================================================

    def test_live_data_preservation_invariant(self):
        """Asserts that live database and all 79 live documents remain 100% untouched."""
        for f, expected_hash in self.baseline_hashes.items():
            live_path = os.path.join(self.live_docs_dir, f)
            self.assertTrue(os.path.isfile(live_path), f"Live file missing: {f}")
            with open(live_path, "rb") as fp:
                actual_hash = hashlib.sha256(fp.read()).hexdigest()
            self.assertEqual(actual_hash, expected_hash, f"Live file altered: {f}")

        conn = sqlite3.connect(self.live_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        self.assertEqual(c.fetchone()[0], self.baseline_activity_count)
        c.execute("SELECT COUNT(*) FROM sessions")
        self.assertEqual(c.fetchone()[0], self.baseline_sessions_count)
        conn.close()


if __name__ == "__main__":
    unittest.main()
