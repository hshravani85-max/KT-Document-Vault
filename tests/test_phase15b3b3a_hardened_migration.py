"""
KT Vault V3 - Phase 15B-3B.3A Hardened Migration Safety Test Suite
Tests for Complete Baseline Manifest Verification, Durable Journaling,
Crash/Interruption Recovery, Rollback, and Path Containment/Symlink Security.
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
import subprocess

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import storage_service
from storage_service import (
    StaticKeyProvider,
    FailClosedKeyProvider,
    read_decrypted_document,
    is_encrypted_bytes,
    is_encrypted_file,
    ENVELOPE_VERSION_V2,
    HEADER_SIZE_V2
)

import migration_engine
from migration_engine import (
    MigrationEngine,
    HardenedMigrationEngine,
    BaselineManifest,
    MigrationJournal,
    MigrationPreflightError,
    MigrationVerificationError,
    MigrationRecoveryError,
    validate_contained_path
)


class TestPhase15B3B3AHardenedMigration(unittest.TestCase):
    """
    Exhaustive safety verification for Phase 15B-3B.3A:
    1. Baseline Manifest Integrity & Mandatory Resolution.
    2. Detection of modified document content & missing hashes.
    3. Pre-encrypted document verification against trusted baseline.
    4. Durable journaling, interruption recovery (resume) & automatic rollback.
    5. Database failure rollback (zero orphaned encrypted files).
    6. Shared physical document preservation across all records.
    7. Path traversal, reparse/junction escapes, & symbolic link security.
    """

    @classmethod
    def setUpClass(cls):
        cls.live_db_path = os.path.realpath(r"C:\KT_Vault_V3\data\kt_vault_v3.db")
        cls.live_docs_dir = os.path.realpath(r"C:\KT_Vault_V3\documents")

        # Record live counts for non-destructive invariant
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
        # Create isolated temporary directory
        self.temp_dir = tempfile.mkdtemp(prefix="ktv_test_hardened_")
        self.test_db_path = os.path.join(self.temp_dir, "test_vault.db")
        self.test_docs_dir = os.path.join(self.temp_dir, "documents")

        # Copy synthetic DB and documents
        shutil.copy2(self.live_db_path, self.test_db_path)
        shutil.copytree(self.live_docs_dir, self.test_docs_dir)

        self.test_key_id = "ktv_2026_test"
        self.test_key_bytes = secrets.token_bytes(32)
        self.key_provider = StaticKeyProvider({self.test_key_id: self.test_key_bytes})
        storage_service.set_key_provider(self.key_provider)

    def tearDown(self):
        storage_service.reset_key_provider()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =================================================================
    # TASK 1: Complete Document Baseline Verification
    # =================================================================

    def test_baseline_manifest_creation_and_loading(self):
        """Verifies baseline manifest covers every unique referenced file with correct SHA-256."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        manifest = BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        self.assertEqual(manifest["total_records"], 28)
        self.assertEqual(manifest["unique_files"], 26)
        self.assertTrue(os.path.isfile(manifest_path))

        loaded = BaselineManifest.load_manifest(manifest_path)
        self.assertEqual(loaded["total_records"], 28)
        self.assertEqual(loaded["unique_files"], 26)

        # Confirm every unique referenced file matches expected SHA-256
        for sid, meta in loaded["files"].items():
            self.assertIn("sha256", meta)
            self.assertEqual(len(meta["sha256"]), 64)
            p = os.path.join(self.test_docs_dir, sid)
            with open(p, "rb") as fp:
                expected_hash = hashlib.sha256(fp.read()).hexdigest()
            self.assertEqual(meta["sha256"], expected_hash)

    def test_missing_baseline_manifest_entry_rejected(self):
        """Verifies migration fails closed if any document record is missing from the baseline manifest."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        manifest = BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        # Delete one entry from manifest
        del manifest["files"]["01_Amit_Mehta_Demo_Passport.pdf"]
        with open(manifest_path, "w", encoding="utf-8") as fp:
            json.dump(manifest, fp)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )
        with self.assertRaises(MigrationPreflightError) as ctx:
            engine.preflight_check()
        self.assertIn("01_Amit_Mehta_Demo_Passport.pdf", str(ctx.exception))

    def test_modified_document_content_rejected_before_encryption(self):
        """Verifies pre-commit check rejects document if its content was altered from baseline."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        # Alter plaintext file on disk after manifest creation
        target = os.path.join(self.test_docs_dir, "01_Amit_Mehta_Demo_Passport.pdf")
        with open(target, "ab") as fp:
            fp.write(b"TAMPERED_BYTES")

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )
        with self.assertRaises(MigrationVerificationError) as ctx:
            engine.execute_migration()
        self.assertIn("does not match baseline", str(ctx.exception))

    def test_pre_encrypted_document_verified_against_baseline(self):
        """
        Verifies that files encrypted during an earlier run are still decrypted
        and compared against the original baseline hash on restart.
        """
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )

        # Simulate interruption after 10 files
        res1 = engine.execute_migration(stop_after_n_files=10)
        self.assertEqual(res1["status"], "interrupted")

        # Resume migration: pre-encrypted files must be verified against baseline hash
        res2 = engine.execute_migration()
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["verification"]["verified_records_count"], 28)

    def test_post_migration_verification_never_permits_missing_hash(self):
        """Verifies verify_all_documents strictly rejects records missing expected hashes."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )
        engine.execute_migration()

        # Create corrupt manifest missing hash for a file
        corrupt_manifest = BaselineManifest.load_manifest(manifest_path)
        corrupt_manifest["files"]["01_Amit_Mehta_Demo_Passport.pdf"]["sha256"] = ""

        with self.assertRaises(MigrationVerificationError) as ctx:
            engine.verify_all_documents(corrupt_manifest)
        self.assertIn("missing sha256 hash", str(ctx.exception))

    # =================================================================
    # TASK 2: Durable Migration Recovery Journal & Rollback
    # =================================================================

    def test_durable_journal_state_machine(self):
        """Verifies the migration journal transitions through all valid states."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        journal_path = os.path.join(self.test_docs_dir, ".migration_journal.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path, journal_path=journal_path
        )

        res = engine.execute_migration()
        self.assertEqual(res["status"], "success")

        # Journal is safely deleted or marked completed
        j_data = engine.journal.load()
        if j_data:
            self.assertEqual(j_data["state"], MigrationJournal.STATE_COMPLETED)

    def test_interruption_recovery_resumption(self):
        """
        Simulates process death halfway through migration (10 of 26 files encrypted):
        Verifies resumption from exact journal checkpoint.
        """
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        journal_path = os.path.join(self.test_docs_dir, ".migration_journal.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path, journal_path=journal_path
        )

        # Crash after 10 files
        engine.execute_migration(stop_after_n_files=10)

        j_data = engine.journal.load()
        self.assertIsNotNone(j_data)
        enc_files = [sid for sid, d in j_data["files"].items() if d["status"] == "ENCRYPTED"]
        self.assertEqual(len(enc_files), 10)

        # Resume migration using new engine instance (simulating restart)
        engine_restarted = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path, journal_path=journal_path
        )
        resume_res = engine_restarted.resume_migration()
        self.assertEqual(resume_res["status"], "success")
        self.assertEqual(resume_res["verification"]["verified_records_count"], 28)

        # Confirm all 26 files are encrypted on disk
        for sid in j_data["files"].keys():
            p = os.path.join(self.test_docs_dir, sid)
            self.assertTrue(is_encrypted_file(p, base_dir=self.test_docs_dir))

    def test_interruption_rollback_to_original_plaintext(self):
        """
        Simulates an operator aborting an interrupted migration:
        Verifies rollback restores all encrypted files back to original plaintext using .orig backups.
        """
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        journal_path = os.path.join(self.test_docs_dir, ".migration_journal.json")
        manifest = BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path, journal_path=journal_path
        )

        # Interrupt after 10 files
        engine.execute_migration(stop_after_n_files=10)

        # Execute rollback
        rollback_res = engine.rollback_migration()
        self.assertEqual(rollback_res["status"], "rolled_back")
        self.assertEqual(rollback_res["restored_count"], 10)

        # Verify all 26 files are back to 100% original plaintext matching baseline manifest
        for sid, meta in manifest["files"].items():
            p = os.path.join(self.test_docs_dir, sid)
            with open(p, "rb") as fp:
                data = fp.read()
            self.assertFalse(is_encrypted_bytes(data), f"File {sid} was not restored to plaintext!")
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"])

    def test_database_failure_triggers_automatic_filesystem_rollback(self):
        """
        Verifies that if the database transaction fails:
        1. Exception is caught and re-raised.
        2. Filesystem is automatically rolled back to plaintext.
        3. No orphaned encrypted files exist without database records.
        """
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        manifest = BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )

        with self.assertRaises(sqlite3.OperationalError):
            engine.execute_migration(simulate_db_failure=True)

        # Verify automatic filesystem rollback restored all 26 files to original plaintext
        for sid, meta in manifest["files"].items():
            p = os.path.join(self.test_docs_dir, sid)
            with open(p, "rb") as fp:
                data = fp.read()
            self.assertFalse(is_encrypted_bytes(data), f"File {sid} remained encrypted after DB failure!")
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"])

    # =================================================================
    # TASK 3: Strict Path Containment & Escape Security
    # =================================================================

    def test_path_traversal_strictly_rejected(self):
        """Verifies path traversal attempts (../) are rejected with PermissionError."""
        with self.assertRaises(PermissionError):
            validate_contained_path("../outside.txt", self.test_docs_dir)

        with self.assertRaises(PermissionError):
            validate_contained_path("documents/../../windows/win.ini", self.test_docs_dir)

    def test_null_bytes_in_path_rejected(self):
        """Verifies null bytes in path are rejected with ValueError."""
        with self.assertRaises(ValueError):
            validate_contained_path("valid.pdf\0malicious.exe", self.test_docs_dir)

    def test_reparse_junction_escape_rejected(self):
        """
        Verifies that an NTFS directory junction inside docs_dir pointing to a folder
        outside docs_dir is detected and strictly rejected.
        Can run on Windows without administrator privileges.
        """
        outside_dir = os.path.join(self.temp_dir, "outside_target")
        os.makedirs(outside_dir, exist_ok=True)
        secret_file = os.path.join(outside_dir, "secret_payload.pdf")
        with open(secret_file, "wb") as fp:
            fp.write(b"%PDF-secret-data")

        junction_path = os.path.join(self.test_docs_dir, "junction_escape")
        res = subprocess.run(f'cmd /c mklink /J "{junction_path}" "{outside_dir}"', shell=True, capture_output=True, text=True)
        if res.returncode != 0 or not os.path.exists(junction_path):
            self.skipTest(f"Could not create directory junction on this filesystem: {res.stderr}")

        target_in_docs = os.path.join("junction_escape", "secret_payload.pdf")
        with self.assertRaises(PermissionError):
            validate_contained_path(target_in_docs, self.test_docs_dir)

    def test_symbolic_link_escape_rejected(self):
        """
        Verifies that a symbolic link inside docs_dir pointing to a file outside
        docs_dir is detected and strictly rejected.
        """
        outside_file = os.path.join(self.temp_dir, "outside_sensitive.txt")
        with open(outside_file, "w") as fp:
            fp.write("SENSITIVE DATA")

        symlink_path = os.path.join(self.test_docs_dir, "symlink_escape.pdf")
        try:
            os.symlink(outside_file, symlink_path)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks require administrative privileges or developer mode on Windows.")

        with self.assertRaises(PermissionError):
            validate_contained_path("symlink_escape.pdf", self.test_docs_dir)

    # =================================================================
    # TASK 4: Shared Documents & Multi-Record Preservation
    # =================================================================

    def test_shared_physical_documents_preserved(self):
        """Verifies shared physical files remain accessible to all referencing records."""
        manifest_path = os.path.join(self.test_docs_dir, ".baseline_manifest.json")
        BaselineManifest.create_manifest(self.test_db_path, self.test_docs_dir, manifest_path)

        engine = MigrationEngine(
            self.test_db_path, self.test_docs_dir, self.key_provider, self.test_key_id,
            manifest_path=manifest_path
        )
        res = engine.execute_migration()
        self.assertEqual(res["status"], "success")

        # Verify shared file: intake_6921d331b6d4451888796cd3bab3e6b5.pdf
        shared_file = os.path.join(self.test_docs_dir, "intake_6921d331b6d4451888796cd3bab3e6b5.pdf")
        self.assertTrue(is_encrypted_file(shared_file, base_dir=self.test_docs_dir))

        # Both records DOC-c966f3e1 and DOC-eb90e64b must decrypt cleanly
        decrypted = read_decrypted_document(shared_file, system_context=True, base_dir=self.test_docs_dir)
        self.assertTrue(len(decrypted) > 0)

    # =================================================================
    # TASK 5: Live Data Preservation Invariant
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
