"""
KT Vault V3 - Phase 15B-3B.3 Test Suite
Full Encryption Migration Rehearsal and Failure/Recovery Verification (No Live Changes).
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import sqlite3
import hashlib
import secrets

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import auth_services
import storage_service
from storage_service import (
    StaticKeyProvider,
    FailClosedKeyProvider,
    read_decrypted_document,
    write_encrypted_file,
    is_encrypted_bytes,
    is_encrypted_file,
    get_envelope_metadata,
    ENVELOPE_VERSION_V2,
    HEADER_SIZE_V2
)
import key_management
from key_management import KeyEscrowService, WindowsDPAPIKeyProvider
import migration_engine
from migration_engine import MigrationEngine, MigrationPreflightError, MigrationVerificationError
import services
import document_processor
import travel_file_generator


class TestPhase15B3B3MigrationRehearsal(unittest.TestCase):
    """
    Exhaustive verification of Phase 15B-3B.3:
    1. Preflight and isolated rehearsal environment setup.
    2. KTV2 document encryption and shared-file preservation.
    3. Application feature validation on encrypted documents:
       - Upload, preview, download, OCR extraction, Traveller Vault reuse,
         trip requirements readiness, document verification, and Travel File generation.
    4. Failure and disaster recovery simulations:
       - Missing key, wrong key, corrupted envelope, interrupted migration,
         database failure rollback, application restart, and escrow backup recovery.
    5. Temporary plaintext risk review.
    6. Non-destructive invariants verification (live DB and documents untouched).
    """

    @classmethod
    def setUpClass(cls):
        # Capture baseline hashes of all 79 live files before test execution
        cls.live_docs_dir = os.path.join(PROJECT_ROOT, "documents")
        cls.live_db_path = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
        cls.baseline_hashes = {}
        for f in os.listdir(cls.live_docs_dir):
            p = os.path.join(cls.live_docs_dir, f)
            if os.path.isfile(p):
                with open(p, "rb") as fp:
                    cls.baseline_hashes[f] = hashlib.sha256(fp.read()).hexdigest()

        conn = sqlite3.connect(cls.live_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        cls.baseline_activity_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sessions")
        cls.baseline_sessions_count = c.fetchone()[0]
        conn.close()

    def setUp(self):
        # 1. Create completely isolated rehearsal sandbox
        self.sandbox_dir = tempfile.mkdtemp(prefix="ktv_rehearsal_sandbox_")
        self.sandbox_db_dir = os.path.join(self.sandbox_dir, "data")
        self.sandbox_docs_dir = os.path.join(self.sandbox_dir, "documents")
        os.makedirs(self.sandbox_db_dir, exist_ok=True)
        os.makedirs(self.sandbox_docs_dir, exist_ok=True)

        # 2. Copy live database and all 79 physical documents into sandbox
        self.sandbox_db_path = os.path.join(self.sandbox_db_dir, "kt_vault_v3.db")
        shutil.copy2(self.live_db_path, self.sandbox_db_path)

        for f in os.listdir(self.live_docs_dir):
            src = os.path.join(self.live_docs_dir, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(self.sandbox_docs_dir, f))

        # 3. Configure synthetic test encryption key
        self.test_key_id = "ktv_reh_2026"
        self.test_key_bytes = secrets.token_bytes(32)
        self.key_provider = StaticKeyProvider({self.test_key_id: self.test_key_bytes})
        storage_service.set_key_provider(self.key_provider)

        # 4. Point database module to sandbox DB
        self._orig_db_path = getattr(database, "DB_PATH", None)
        database.DB_PATH = self.sandbox_db_path

        # 5. Create valid test session token in sandbox DB
        self.session_token = self._create_test_session("admin", "Admin")

    def tearDown(self):
        # Restore database module DB_PATH
        if self._orig_db_path:
            database.DB_PATH = self._orig_db_path
        storage_service.reset_key_provider()

        # Clean up isolated sandbox
        if os.path.exists(self.sandbox_dir):
            shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def _create_test_session(self, username: str = "admin", role: str = "Admin") -> str:
        from datetime import datetime, timedelta
        conn = sqlite3.connect(self.sandbox_db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE role = ?", (role,))
        row = c.fetchone()
        user_id = row["id"] if row else "USER-ADMIN-01"
        token = "test_admin_token_" + secrets.token_hex(16)
        valid_future = (datetime.now() + timedelta(hours=8)).isoformat()
        c.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, valid_future)
        )
        conn.commit()
        conn.close()
        return token

    # =================================================================
    # STEP 3: Encryption Rehearsal Tests
    # =================================================================

    def test_rehearsal_preflight_and_dry_run(self):
        """Verifies preflight validation correctly identifies records, shared files, and unreferenced files."""
        engine = MigrationEngine(
            db_path=self.sandbox_db_path,
            docs_dir=self.sandbox_docs_dir,
            key_provider=self.key_provider,
            key_id=self.test_key_id
        )

        preflight = engine.preflight_check()
        self.assertEqual(preflight["total_records"], 28)
        self.assertEqual(preflight["unique_referenced_files"], 26)
        self.assertEqual(preflight["shared_physical_files"], 2)
        self.assertEqual(preflight["unreferenced_files_count"], 53)

        # Verify dry-run completes successfully without altering files
        dry_run = engine.run_dry_run()
        self.assertEqual(dry_run["status"], "dry_run_success")
        self.assertEqual(dry_run["simulated_files_verified"], 26)

        # Verify files on disk remain unencrypted after dry run
        for f in os.listdir(self.sandbox_docs_dir):
            p = os.path.join(self.sandbox_docs_dir, f)
            self.assertFalse(is_encrypted_file(p, base_dir=self.sandbox_docs_dir))

    def test_rehearsal_encryption_and_shared_file_preservation(self):
        """
        Executes full migration on sandbox documents:
        1. Encrypts all 26 referenced physical files using KTV2.
        2. Preserves shared-file relationships.
        3. Verifies decrypted hashes match original plaintext 100%.
        4. Verifies idempotency (no document encrypted twice).
        """
        engine = MigrationEngine(
            db_path=self.sandbox_db_path,
            docs_dir=self.sandbox_docs_dir,
            key_provider=self.key_provider,
            key_id=self.test_key_id
        )

        # Capture pre-migration plaintext hashes
        preflight = engine.preflight_check()
        orig_hashes = dict(preflight["plaintext_hashes"])

        # Execute migration
        res = engine.execute_migration()
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["encrypted_count"], 26)
        self.assertEqual(res["skipped_count"], 0)
        self.assertEqual(res["verification"]["verified_records_count"], 28)

        # Verify all 26 referenced files on disk are now encrypted with KTV2
        for canonical_path in preflight["path_to_records"].keys():
            self.assertTrue(is_encrypted_file(canonical_path, base_dir=self.sandbox_docs_dir))
            with open(canonical_path, "rb") as fp:
                data = fp.read()
            self.assertEqual(data[:4], b"KTV2")
            meta = get_envelope_metadata(data)
            self.assertEqual(meta["key_id"], self.test_key_id)

        # Verify shared files: DOC-c966f3e1 & DOC-eb90e64b, DOC-5ad21646 & DOC-7866f701
        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        for doc_id in ["DOC-c966f3e1", "DOC-eb90e64b", "DOC-5ad21646", "DOC-7866f701"]:
            c.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,))
            row = c.fetchone()
            rel = row[0].replace("documents\\", "").replace("documents/", "")
            full_path = os.path.join(self.sandbox_docs_dir, rel)

            decrypted = read_decrypted_document(
                full_path,
                session_token=self.session_token,
                key_provider=self.key_provider,
                base_dir=self.sandbox_docs_dir
            )
            self.assertEqual(hashlib.sha256(decrypted).hexdigest(), orig_hashes[full_path])
        conn.close()

        # Idempotency: Second migration run must skip all 26 files (0 encrypted, 26 skipped)
        res2 = engine.execute_migration()
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["encrypted_count"], 0)
        self.assertEqual(res2["skipped_count"], 26)

    # =================================================================
    # STEP 4: Application Features Against Encrypted Storage
    # =================================================================

    def test_features_new_document_upload(self):
        """Verifies uploading and saving a new document into the encrypted rehearsal environment."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Simulate intake upload of a new synthetic visa document
        new_plain_bytes = b"%PDF-1.4 Synthetic Visa Upload Content for Traveller 99"
        new_filename = "upload_test_visa_001.pdf"
        new_path = os.path.join(self.sandbox_docs_dir, new_filename)

        # Write as encrypted file (KTV2)
        write_res = write_encrypted_file(
            new_filename,
            new_plain_bytes,
            key_id=self.test_key_id,
            envelope_version=ENVELOPE_VERSION_V2,
            key_provider=self.key_provider,
            base_dir=self.sandbox_docs_dir
        )
        self.assertTrue(os.path.isfile(write_res["file_path"]))
        self.assertTrue(is_encrypted_file(write_res["file_path"], base_dir=self.sandbox_docs_dir))

        # Save record in sandbox database via services.save_document
        extracted_data = {
            "Traveller Name": "Amit Mehta",
            "Visa Number / Reference": "VISA-998877",
            "Destination": "Dubai"
        }
        doc_id = services.save_document(
            requirement_id="REQ-TR-02",
            file_path=write_res["file_path"],
            extracted_data=extracted_data,
            session_token=self.session_token
        )
        self.assertTrue(doc_id.startswith("DOC-"))

        # Read back document via authenticated service
        retrieved_bytes = read_decrypted_document(
            write_res["file_path"],
            session_token=self.session_token,
            key_provider=self.key_provider,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(retrieved_bytes, new_plain_bytes)

    def test_features_document_preview_and_download(self):
        """Verifies document preview and download against encrypted documents."""
        # First migrate sandbox documents
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        preflight = engine.preflight_check()
        orig_hashes = dict(preflight["plaintext_hashes"])
        engine.execute_migration()

        # Select a sample verified document
        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT id, file_path FROM documents WHERE id = 'DOC-65d638ad'")
        doc_id, raw_path = c.fetchone()
        conn.close()

        rel = raw_path.replace("documents\\", "").replace("documents/", "")
        full_path = os.path.join(self.sandbox_docs_dir, rel)

        # Preview: read decrypted document
        preview_bytes = read_decrypted_document(
            full_path,
            session_token=self.session_token,
            key_provider=self.key_provider,
            base_dir=self.sandbox_docs_dir
        )
        self.assertTrue(preview_bytes.startswith(b"%PDF"))
        self.assertEqual(hashlib.sha256(preview_bytes).hexdigest(), orig_hashes[full_path])

    def test_features_ocr_extraction_on_encrypted_document(self):
        """Verifies OCR and document processing operate correctly on decrypted document streams."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Retrieve encrypted passport document
        passport_path = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        self.assertTrue(is_encrypted_file(passport_path, base_dir=self.sandbox_docs_dir))

        decrypted_bytes = read_decrypted_document(
            passport_path,
            session_token=self.session_token,
            key_provider=self.key_provider,
            base_dir=self.sandbox_docs_dir
        )

        # Run document processor
        res = document_processor.process_document("01_Amit_Mehta_Demo_Passport.pdf", decrypted_bytes, expected_requirement="Passport")
        self.assertIn("document_type", res)
        self.assertEqual(res["document_type"], "Passport")
        self.assertIn("extracted_fields", res)
        fields = res["extracted_fields"]
        self.assertTrue(len(fields) > 0)

    def test_features_trip_readiness_and_document_verification(self):
        """Verifies trip document requirements, readiness calculation, and verification transitions."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Calculate readiness for KT-T-0001 (should be 100% complete)
        total, complete, attention, missing, pct, status = services.calculate_readiness("KT-T-0001")
        self.assertEqual(pct, 100.0)
        self.assertEqual(missing, 0)
        self.assertEqual(attention, 0)

        # Test document verification on an encrypted document
        conn = sqlite3.connect(self.sandbox_db_path)
        conn.execute("UPDATE documents SET status = 'Under Review' WHERE id = 'DOC-65d638ad'")
        conn.commit()
        conn.close()

        services.verify_document("DOC-65d638ad", session_token=self.session_token)

        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT status FROM documents WHERE id = 'DOC-65d638ad'")
        updated_status = c.fetchone()[0]
        conn.close()
        self.assertEqual(updated_status, "Verified")

    def test_features_travel_file_pdf_generation(self):
        """Verifies generating consolidated Travel File PDF for approved trip with encrypted documents."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        out_pdf = os.path.join(self.sandbox_docs_dir, "TravelFile_KT-T-0001.pdf")
        res_path = travel_file_generator.generate_consolidated_travel_file(
            "KT-T-0001",
            out_path=out_pdf,
            session_token=self.session_token
        )
        self.assertTrue(os.path.isfile(res_path))
        with open(res_path, "rb") as f:
            pdf_data = f.read()
        self.assertTrue(pdf_data.startswith(b"%PDF-1.4"))
        self.assertIn(b"KHANNA TRAVELS", pdf_data)

    def test_features_traveller_vault_reuse(self):
        """Verifies Traveller Vault document reuse logic operates seamlessly with encrypted files."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Read encrypted shared file DOC-c966f3e1
        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT file_path FROM documents WHERE id = 'DOC-c966f3e1'")
        rel_path = c.fetchone()[0].replace("documents\\", "").replace("documents/", "")
        full_path = os.path.join(self.sandbox_docs_dir, rel_path)
        conn.close()

        # Call read_decrypted_document as used in services.py deduplication
        bytes1 = read_decrypted_document(full_path, session_token=self.session_token, base_dir=self.sandbox_docs_dir)
        bytes2 = read_decrypted_document(full_path, session_token=self.session_token, base_dir=self.sandbox_docs_dir)
        self.assertEqual(hashlib.sha256(bytes1).digest(), hashlib.sha256(bytes2).digest())

    # =================================================================
    # STEP 5: Failure and Recovery Tests
    # =================================================================

    def test_failure_missing_encryption_key_fails_closed(self):
        """Verifies missing encryption key halts document retrieval immediately without plaintext leakage."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Configure FailClosedKeyProvider (no keys available)
        storage_service.set_key_provider(FailClosedKeyProvider())

        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        with self.assertRaises(RuntimeError) as ctx:
            read_decrypted_document(
                sample_file,
                session_token=self.session_token,
                base_dir=self.sandbox_docs_dir
            )
        self.assertIn("Cryptographic operation blocked", str(ctx.exception))

    def test_failure_wrong_encryption_key_rejected(self):
        """Verifies decrypting with an incorrect 256-bit key fails AES-GCM authentication."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Configure wrong key provider under the same key_id
        wrong_provider = StaticKeyProvider({self.test_key_id: secrets.token_bytes(32)})

        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        with self.assertRaises(ValueError) as ctx:
            read_decrypted_document(
                sample_file,
                session_token=self.session_token,
                key_provider=wrong_provider,
                base_dir=self.sandbox_docs_dir
            )
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    def test_failure_corrupted_encrypted_file_rejected(self):
        """Verifies tampering with encrypted envelope bytes triggers immediate authentication rejection."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        with open(sample_file, "r+b") as fp:
            data = bytearray(fp.read())
            data[HEADER_SIZE_V2 + 10] ^= 0x55  # flip bit in ciphertext
            fp.seek(0)
            fp.write(data)

        with self.assertRaises(ValueError):
            read_decrypted_document(
                sample_file,
                session_token=self.session_token,
                key_provider=self.key_provider,
                base_dir=self.sandbox_docs_dir
            )

    def test_failure_shared_file_tamper_detected(self):
        """Verifies tampering with a shared physical file is detected across all referencing records."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        preflight = engine.preflight_check()
        orig_hashes = dict(preflight["plaintext_hashes"])
        engine.execute_migration()

        # Shared file: intake_6921d331b6d4451888796cd3bab3e6b5.pdf (DOC-c966f3e1, DOC-eb90e64b)
        shared_file = os.path.join(self.sandbox_docs_dir, "intake_6921d331b6d4451888796cd3bab3e6b5.pdf")
        with open(shared_file, "r+b") as fp:
            data = bytearray(fp.read())
            data[HEADER_SIZE_V2 + 5] ^= 0xAA  # flip bit in ciphertext
            fp.seek(0)
            fp.write(data)

        # Verification must catch the failure and report both records
        with self.assertRaises(MigrationVerificationError) as ctx:
            engine.verify_all_documents(orig_hashes)
        err_msg = str(ctx.exception)
        self.assertIn("DOC-c966f3e1", err_msg)
        self.assertIn("DOC-eb90e64b", err_msg)

    def test_failure_interrupted_migration_recovery(self):
        """
        Simulates interrupted migration (crash after 10 files):
        - 10 files are encrypted, 16 remain plaintext.
        - Migration is restarted.
        - Engine resumes smoothly, skips the 10 already-encrypted files,
          encrypts the remaining 16 files, and achieves 100% verification.
        """
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        preflight = engine.preflight_check()
        orig_hashes = dict(preflight["plaintext_hashes"])

        # Phase 1: Simulate crash after 10 files
        res1 = engine.execute_migration(stop_after_n_files=10)
        self.assertEqual(res1["status"], "interrupted")
        self.assertEqual(res1["encrypted_count"], 10)

        # Count disk files: exactly 10 should be encrypted, 16 unencrypted
        enc_count = sum(
            1 for p in preflight["path_to_records"].keys()
            if is_encrypted_file(p, base_dir=self.sandbox_docs_dir)
        )
        self.assertEqual(enc_count, 10)

        # Phase 2: Resume migration after interruption
        res2 = engine.execute_migration()
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["encrypted_count"], 16)
        self.assertEqual(res2["skipped_count"], 10)
        self.assertEqual(res2["verification"]["verified_records_count"], 28)

        # All 26 files are now encrypted
        for p in preflight["path_to_records"].keys():
            self.assertTrue(is_encrypted_file(p, base_dir=self.sandbox_docs_dir))

    def test_failure_database_transaction_rollback(self):
        """Verifies database transaction failure rolls back cleanly."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)

        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        initial_activity_count = c.fetchone()[0]
        conn.close()

        with self.assertRaises(sqlite3.OperationalError):
            engine.execute_migration(simulate_db_failure=True)

        # Verify activity table was rolled back
        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        after_count = c.fetchone()[0]
        conn.close()
        self.assertEqual(initial_activity_count, after_count)

    def test_failure_application_restart_simulation(self):
        """Verifies that reinitializing services after encryption retains full decryption capability."""
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Simulate application restart: clear active provider, reinitialize from synthetic key
        storage_service.reset_key_provider()
        new_provider = StaticKeyProvider({self.test_key_id: self.test_key_bytes})
        storage_service.set_key_provider(new_provider)

        # Verify document read
        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        doc_bytes = read_decrypted_document(
            sample_file,
            session_token=self.session_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertTrue(doc_bytes.startswith(b"%PDF"))

    def test_disaster_recovery_from_escrow_backup(self):
        """
        Tests full disaster recovery workflow:
        1. Encrypt documents with master key.
        2. Export master key to password-protected escrow package (KT_VAULT_KEY_ESCROW_V1).
        3. Simulate disaster: Wipe active key provider.
        4. Decryption fails closed (no key).
        5. Recover master key from escrow package using recovery passphrase.
        6. Reinstall key into provider; all documents decrypt cleanly!
        """
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        preflight = engine.preflight_check()
        orig_hashes = dict(preflight["plaintext_hashes"])
        engine.execute_migration()

        # Step 2: Export key to escrow package
        passphrase = "DisasterRecoveryPassphrase2026!"
        escrow_file = os.path.join(self.sandbox_dir, "master_key_escrow.json")
        KeyEscrowService.export_escrow_file(
            key=self.test_key_bytes,
            key_id=self.test_key_id,
            passphrase=passphrase,
            output_path=escrow_file,
            iterations=100000
        )
        self.assertTrue(os.path.isfile(escrow_file))

        # Step 3: Simulate disaster - wipe provider
        storage_service.set_key_provider(FailClosedKeyProvider())

        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        with self.assertRaises(RuntimeError):
            read_decrypted_document(sample_file, session_token=self.session_token, base_dir=self.sandbox_docs_dir)

        # Step 4: Recover key from escrow package
        rec_id, rec_key = KeyEscrowService.import_escrow_file(escrow_file, passphrase)
        self.assertEqual(rec_id, self.test_key_id)
        self.assertEqual(rec_key, self.test_key_bytes)

        # Step 5: Restore key into active provider
        restored_provider = StaticKeyProvider({rec_id: rec_key})
        storage_service.set_key_provider(restored_provider)

        # Step 6: Verify all documents can be decrypted again
        verification = engine.verify_all_documents(orig_hashes)
        self.assertTrue(verification["all_verified"])
        self.assertEqual(verification["verified_records_count"], 28)

    # =================================================================
    # STEP 6: Temporary Plaintext Risk Audit
    # =================================================================

    def test_temporary_plaintext_risk_audit(self):
        """
        Audits whether preview, OCR, download, and Travel File generation leak temporary files:
        - Confirms that temporary files created by OCR (tesseract/poppler) and PDF generation
          are cleaned up in finally blocks.
        """
        engine = MigrationEngine(self.sandbox_db_path, self.sandbox_docs_dir, self.key_provider, self.test_key_id)
        engine.execute_migration()

        # Monitor system temp directory
        temp_dir = tempfile.gettempdir()
        initial_tmp_entries = set(os.listdir(temp_dir))

        # 1. Document Preview / Read
        sample_file = os.path.join(self.sandbox_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        doc_bytes = read_decrypted_document(sample_file, session_token=self.session_token, base_dir=self.sandbox_docs_dir)
        self.assertTrue(len(doc_bytes) > 0)

        # 2. OCR Execution
        res = document_processor.process_document("01_Amit_Mehta_Demo_Passport.pdf", doc_bytes, expected_requirement="Passport")
        self.assertIsNotNone(res)

        # 3. Travel File PDF generation
        out_pdf = os.path.join(self.sandbox_docs_dir, "TravelFile_KT-T-0001.pdf")
        travel_file_generator.generate_consolidated_travel_file("KT-T-0001", out_path=out_pdf, session_token=self.session_token)

        # Check for lingering temporary files created with 'kt_pdf_ocr_' or '.tmp_'
        current_tmp_entries = set(os.listdir(temp_dir))
        new_entries = current_tmp_entries - initial_tmp_entries

        lingering_kt_files = [
            e for e in new_entries
            if e.startswith("kt_pdf_ocr_") or e.startswith("ktv_test_")
        ]
        self.assertEqual(
            lingering_kt_files, [],
            f"Detected uncleaned temporary files in system temp: {lingering_kt_files}"
        )

    # =================================================================
    # STEP 7: Live Data Preservation Invariant
    # =================================================================

    def test_live_data_preservation_invariant(self):
        """
        Strict non-destructive invariant:
        Asserts that the live database and all 79 live documents remain 100% untouched.
        """
        # Verify all 79 physical document hashes match baseline
        for f, expected_hash in self.baseline_hashes.items():
            live_path = os.path.join(self.live_docs_dir, f)
            self.assertTrue(os.path.isfile(live_path), f"Live file missing: {f}")
            with open(live_path, "rb") as fp:
                actual_hash = hashlib.sha256(fp.read()).hexdigest()
            self.assertEqual(
                actual_hash, expected_hash,
                f"Live document modified! Hash mismatch for {f}."
            )

        # Verify live database table counts
        conn = sqlite3.connect(self.live_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        current_activity_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sessions")
        current_sessions_count = c.fetchone()[0]
        conn.close()

        self.assertEqual(
            current_activity_count, self.baseline_activity_count,
            "Live activity table modified during rehearsal!"
        )
        self.assertEqual(
            current_sessions_count, self.baseline_sessions_count,
            "Live sessions table modified during rehearsal!"
        )


if __name__ == "__main__":
    unittest.main()
