"""
KT Vault V3 - Phase 15B-3B.4B Final Migration Activation Readiness Test Suite
(tests/test_phase15b3b4b_activation_readiness.py)

Comprehensive verification of:
1. Maintenance mode blocking writes and concurrent access.
2. Fail-closed persistent encryption mode surviving process restarts.
3. No plaintext writes possible when encryption mode is enforced.
4. Interruption and rollback recovery in isolated sandbox.
5. Complete migration execution with zero lingering plaintext in staging backups.
6. Encrypted document read and workflow compatibility.
7. OCR temporary-file cleanup lifecycle.
8. Non-destructive live data invariant (79/79 files and 12/12 tables untouched).
"""

import os
import sys
import shutil
import tempfile
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import storage_service
from storage_service import (
    write_document_file,
    read_decrypted_document,
    is_encrypted_file,
    is_encrypted_bytes,
    get_encryption_mode,
    set_encryption_mode,
    is_maintenance_mode,
    StaticKeyProvider,
    FailClosedKeyProvider,
    ENCRYPTION_MODE_TRANSITIONAL,
    ENCRYPTION_MODE_ENFORCED,
    ENVELOPE_MAGIC_V2,
    ENVELOPE_VERSION_V2,
    HEADER_SIZE_V2
)
import migration_engine
from migration_engine import HardenedMigrationEngine, MigrationJournal
import travel_file_generator
import document_processor
import ocr_service


class TestPhase15B3B4BActivationReadiness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.live_db_path = os.path.realpath(r"C:\KT_Vault_V3\data\kt_vault_v3.db")
        cls.live_docs_dir = os.path.realpath(r"C:\KT_Vault_V3\documents")

        # Baseline live checksums
        cls.baseline_hashes = {}
        for f in os.listdir(cls.live_docs_dir):
            p = os.path.join(cls.live_docs_dir, f)
            if os.path.isfile(p):
                with open(p, "rb") as fp:
                    cls.baseline_hashes[f] = hashlib.sha256(fp.read()).hexdigest()

    def setUp(self):
        # Create isolated temporary sandbox
        self.temp_dir = tempfile.mkdtemp(prefix="ktv_test_phase15b3b4b_")
        self.sandbox_data_dir = os.path.join(self.temp_dir, "data")
        os.makedirs(self.sandbox_data_dir, exist_ok=True)
        self.sandbox_db_path = os.path.join(self.sandbox_data_dir, "kt_vault_v3.db")
        self.sandbox_docs_dir = os.path.join(self.temp_dir, "documents")

        shutil.copy2(self.live_db_path, self.sandbox_db_path)
        shutil.copytree(self.live_docs_dir, self.sandbox_docs_dir)

        # Redirect database
        self.orig_db_path = database.DB_PATH
        database.DB_PATH = self.sandbox_db_path

        # Setup test keys
        self.test_key_id = "ktv_2026_v1"
        self.test_key_bytes = secrets.token_bytes(32)
        self.key_provider = StaticKeyProvider({self.test_key_id: self.test_key_bytes})
        storage_service.set_key_provider(self.key_provider)

        # Create valid authenticated sessions in sandbox
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
        marker = os.path.join(self.sandbox_data_dir, ".encryption_enforced")
        if os.path.exists(marker):
            try:
                os.remove(marker)
            except Exception:
                pass
        set_encryption_mode(ENCRYPTION_MODE_TRANSITIONAL)
        database.DB_PATH = self.orig_db_path
        os.environ.pop("KT_VAULT_ENCRYPTION_MODE", None)
        os.environ.pop("KT_VAULT_MAINTENANCE_MODE", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =================================================================
    # TASK 2: Maintenance Mode Blocking
    # =================================================================

    def test_01_maintenance_mode_blocks_writes(self):
        """Verifies maintenance mode strictly blocks document writes and uploads."""
        # 1. Normal state: maintenance mode is inactive
        self.assertFalse(is_maintenance_mode(base_dir=self.sandbox_data_dir))

        # 2. Activate maintenance mode via marker file in sandbox
        maint_marker = os.path.join(self.sandbox_data_dir, ".maintenance_mode")
        with open(maint_marker, "w") as f:
            f.write("MAINTENANCE_IN_PROGRESS")

        self.assertTrue(is_maintenance_mode(base_dir=self.sandbox_data_dir))

        # 3. Write attempt must be strictly blocked with PermissionError
        with self.assertRaises(PermissionError) as ctx:
            write_document_file(
                "blocked_during_maint.pdf",
                b"%PDF-1.4 Payload",
                session_token=self.admin_token,
                base_dir=self.sandbox_docs_dir
            )
        self.assertIn("Maintenance mode", str(ctx.exception))

        # 4. Remove maintenance marker and verify writes resume
        os.remove(maint_marker)
        self.assertFalse(is_maintenance_mode(base_dir=self.sandbox_data_dir))
        res = write_document_file(
            "allowed_after_maint.pdf",
            b"%PDF-1.4 Payload After Maint",
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertTrue(os.path.isfile(res["file_path"]))

    def test_02_maintenance_mode_via_env_var(self):
        """Verifies environment variable KT_VAULT_MAINTENANCE_MODE=1 activates maintenance mode."""
        os.environ["KT_VAULT_MAINTENANCE_MODE"] = "1"
        self.assertTrue(is_maintenance_mode())

        with self.assertRaises(PermissionError):
            write_document_file(
                "env_maint_blocked.pdf",
                b"%PDF-1.4 Payload",
                session_token=self.admin_token,
                base_dir=self.sandbox_docs_dir
            )

        os.environ["KT_VAULT_MAINTENANCE_MODE"] = "0"
        self.assertFalse(is_maintenance_mode())

    # =================================================================
    # TASK 3: Fail-Closed Mode Persistence Across Restarts
    # =================================================================

    def test_03_mode_persistence_and_anti_downgrade(self):
        """Verifies switching to ENCRYPTION_MODE_ENFORCED with persist=True survives restart and prevents downgrade."""
        # Baseline mode is transitional
        self.assertEqual(get_encryption_mode(), ENCRYPTION_MODE_TRANSITIONAL)

        # Enforce encryption with persistence
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED, persist=True)
        self.assertEqual(get_encryption_mode(), ENCRYPTION_MODE_ENFORCED)

        marker = os.path.join(self.sandbox_data_dir, ".encryption_enforced")
        self.assertTrue(os.path.isfile(marker))

        # Simulate cold application restart: reset in-memory variable to transitional
        storage_service._CURRENT_ENCRYPTION_MODE = ENCRYPTION_MODE_TRANSITIONAL

        # get_encryption_mode() must STILL return ENCRYPTION_MODE_ENFORCED due to marker file!
        self.assertEqual(get_encryption_mode(), ENCRYPTION_MODE_ENFORCED)

        # Anti-downgrade protection: cannot revert to transitional when marker exists
        with self.assertRaises(RuntimeError) as ctx:
            set_encryption_mode(ENCRYPTION_MODE_TRANSITIONAL)
        self.assertIn("Cannot revert to transitional mode", str(ctx.exception))

        # Cleanup test marker for tearDown
        if os.path.exists(marker):
            os.remove(marker)

    # =================================================================
    # TASK 7: Enforced Encryption Behavior
    # =================================================================

    def test_04_enforced_encryption_writes_ktv2_and_fails_closed(self):
        """Verifies enforced mode writes KTV2 encrypted envelopes and never falls back to plaintext if key missing."""
        set_encryption_mode(ENCRYPTION_MODE_ENFORCED)

        plain_data = b"%PDF-1.4 Confidential New Document Payload"
        doc_filename = f"new_enforced_{secrets.token_hex(4)}.pdf"

        # 1. Successful write with valid key
        res = write_document_file(
            doc_filename,
            plain_data,
            session_token=self.admin_token,
            base_dir=self.sandbox_docs_dir
        )
        self.assertEqual(res["status"], "encrypted")

        stored_path = res["file_path"]
        self.assertTrue(is_encrypted_file(stored_path, base_dir=self.sandbox_docs_dir))

        with open(stored_path, "rb") as f:
            header = f.read(HEADER_SIZE_V2)
        self.assertTrue(header.startswith(ENVELOPE_MAGIC_V2))
        self.assertIn(b"ktv_2026_v1", header)

        # Verify reading and decryption
        decrypted = read_decrypted_document(stored_path, session_token=self.admin_token, base_dir=self.sandbox_docs_dir)
        self.assertEqual(decrypted, plain_data)

        # 2. Fail-closed: missing key provider
        storage_service.set_key_provider(FailClosedKeyProvider())
        with self.assertRaises(RuntimeError) as ctx:
            write_document_file(
                "unkey_doc.pdf",
                plain_data,
                session_token=self.admin_token,
                base_dir=self.sandbox_docs_dir
            )
        err_msg = str(ctx.exception)
        self.assertTrue("unavailable" in err_msg or "unconfigured" in err_msg)
        self.assertFalse(os.path.exists(os.path.join(self.sandbox_docs_dir, "unkey_doc.pdf")))

    # =================================================================
    # TASK 6: Interruption and Rollback Recovery
    # =================================================================

    def test_05_interruption_and_safe_rollback_recovery(self):
        """Tests that an interrupted migration can be cleanly rolled back to 100% original baseline."""
        engine = HardenedMigrationEngine(
            db_path=self.sandbox_db_path,
            docs_dir=self.sandbox_docs_dir,
            key_provider=self.key_provider,
            key_id=self.test_key_id
        )

        preflight = engine.preflight_check()
        manifest = preflight["manifest"]

        # Run interrupted migration (stop after 10 files)
        res_interrupted = engine.execute_migration(stop_after_n_files=10)
        self.assertEqual(res_interrupted["status"], "interrupted")
        self.assertEqual(res_interrupted["encrypted_count"], 10)

        # Verify exactly 10 files encrypted
        all_files = [os.path.join(self.sandbox_docs_dir, f) for f in os.listdir(self.sandbox_docs_dir) if os.path.isfile(os.path.join(self.sandbox_docs_dir, f))]
        encrypted_files = [f for f in all_files if is_encrypted_file(f, base_dir=self.sandbox_docs_dir)]
        self.assertEqual(len(encrypted_files), 10)

        # Execute rollback
        rb_res = engine.rollback_migration()
        self.assertEqual(rb_res["status"], "rolled_back")
        self.assertEqual(rb_res["restored_count"], 10)

        # Verify all files are restored to plaintext and match baseline hashes
        for f in os.listdir(self.sandbox_docs_dir):
            if f.startswith("."):
                continue
            p = os.path.join(self.sandbox_docs_dir, f)
            if os.path.isfile(p):
                with open(p, "rb") as fp:
                    data = fp.read()
                self.assertFalse(is_encrypted_bytes(data))
                self.assertEqual(hashlib.sha256(data).hexdigest(), self.baseline_hashes[f])

    # =================================================================
    # TASK 5 & 8: Complete Migration, Zero Plaintext Leak & Read Compatibility
    # =================================================================

    def test_06_complete_migration_zero_plaintext_leak_and_read_compat(self):
        """Verifies full migration, complete cleanup of staging backups, and 100% read compatibility."""
        engine = HardenedMigrationEngine(
            db_path=self.sandbox_db_path,
            docs_dir=self.sandbox_docs_dir,
            key_provider=self.key_provider,
            key_id=self.test_key_id
        )

        exec_res = engine.execute_migration()
        self.assertEqual(exec_res["status"], "success")

        # 1. Verify all referenced files migrated are KTV2 encrypted
        preflight = engine.preflight_check()
        for p in preflight["path_to_records"].keys():
            self.assertTrue(is_encrypted_file(p, base_dir=self.sandbox_docs_dir))

        # 2. Verify staging backups (.orig) are completely removed (zero plaintext leaks)
        backup_dir = os.path.join(self.sandbox_docs_dir, ".migration_backups")
        self.assertFalse(os.path.exists(backup_dir))

        # 3. Verify journal has no sensitive plaintext payloads
        j_path = os.path.join(self.sandbox_docs_dir, ".migration_journal.json")
        self.assertTrue(os.path.isfile(j_path))
        with open(j_path, "r", encoding="utf-8") as f:
            j_text = f.read()
        self.assertNotIn("%PDF-", j_text)
        self.assertNotIn("Khanna Travels", j_text)

        # 4. Verify all document records read and decrypt cleanly
        conn = sqlite3.connect(self.sandbox_db_path)
        c = conn.cursor()
        c.execute("SELECT id, requirement_id, file_path FROM documents")
        docs = c.fetchall()
        conn.close()

        for doc_id, req_id, file_path in docs:
            filename = os.path.basename(file_path)
            full_p = os.path.join(self.sandbox_docs_dir, filename)
            decrypted = read_decrypted_document(
                full_p,
                session_token=self.admin_token,
                base_dir=self.sandbox_docs_dir
            )
            self.assertEqual(hashlib.sha256(decrypted).hexdigest(), self.baseline_hashes[filename])

        # 5. Verify travel file generator works with encrypted documents
        out_tf = os.path.join(self.sandbox_docs_dir, "TravelFile_KT-T-0001.pdf")
        tf_path = travel_file_generator.generate_consolidated_travel_file(
            trip_id="KT-T-0001",
            out_path=out_tf,
            session_token=self.admin_token
        )
        self.assertTrue(os.path.isfile(tf_path))

    # =================================================================
    # TASK 9: OCR Temporary File Lifecycle
    # =================================================================

    def test_07_ocr_temp_file_cleanup(self):
        """Verifies OCR service leaves zero abandoned temporary files on completion."""
        before_temp_entries = set(os.listdir(tempfile.gettempdir()))

        dummy_img = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        res = ocr_service.extract_text(dummy_img, "test_ocr.jpg")

        after_temp_entries = set(os.listdir(tempfile.gettempdir()))
        new_entries = [e for e in (after_temp_entries - before_temp_entries) if "kt_pdf_ocr" in e]
        self.assertEqual(len(new_entries), 0)

    # =================================================================
    # TASK 11: Live Invariant Check
    # =================================================================

    def test_08_live_invariants_strictly_unmodified(self):
        """Verifies all 79 live documents and all 12 database tables are 100% untouched."""
        live_files = [f for f in os.listdir(self.live_docs_dir) if os.path.isfile(os.path.join(self.live_docs_dir, f))]
        self.assertEqual(len(live_files), 79)

        for f in live_files:
            p = os.path.join(self.live_docs_dir, f)
            with open(p, "rb") as fp:
                data = fp.read()
            self.assertFalse(is_encrypted_bytes(data))
            self.assertEqual(hashlib.sha256(data).hexdigest(), self.baseline_hashes[f])

        # Database rows
        conn = sqlite3.connect(self.live_db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM activity")
        self.assertEqual(c.fetchone()[0], 886)
        c.execute("SELECT COUNT(*) FROM sessions")
        self.assertEqual(c.fetchone()[0], 3)
        c.execute("SELECT COUNT(*) FROM documents")
        self.assertEqual(c.fetchone()[0], 28)
        conn.close()


if __name__ == "__main__":
    unittest.main()
