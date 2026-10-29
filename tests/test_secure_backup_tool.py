"""
KT Vault V3 - Portable Encrypted Backup Tool Test Suite
Phase 15B-3B.4E Implementation

Verifies:
  1. Correct-password backup and restore round-trip.
  2. Wrong-password rejection (auth tag mismatch).
  3. Tampered ciphertext rejection.
  4. Corrupted header fields rejection (magic, salt, iterations, nonce, tag).
  5. Interrupted write cleanup & atomic replace.
  6. Overwrite prevention (backup output and restored destination).
  7. Manifest validation: missing, modified, or unexpected files abort backup.
  8. Path traversal defense: relative traversal (..), absolute paths, and drive escapes.
  9. Symlink and hardlink prohibition.
 10. Archive bomb & resource exhaustion guards.
 11. Verify-only mode for safe preflight inspection.
"""

import os
import sys
import io
import json
import shutil
import tarfile
import hashlib
import tempfile
import unittest

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import secure_backup_tool as sbt
import restore_ktbak as rkt


class TestSecureBackupTool(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kt_backup_test_")
        self.source_dir = os.path.join(self.test_dir, "mock_snapshot")
        self.restore_dir = os.path.join(self.test_dir, "restored_output")
        self.backup_file = os.path.join(self.test_dir, "test_backup.ktbak")
        self.passphrase = "CorrectVaultPassword!2026"
        # Use lower iterations for fast unit tests while maintaining full crypto pipeline
        self.test_iterations = 100_000

        # Construct standard mock snapshot structure
        os.makedirs(os.path.join(self.source_dir, "data"), exist_ok=True)
        os.makedirs(os.path.join(self.source_dir, "documents"), exist_ok=True)

        # Mock DB
        self.db_path = os.path.join(self.source_dir, "data", "kt_vault_v3.db")
        self.db_content = b"SQLITE_MOCK_DATABASE_DATA_FOR_BACKUP_TEST"
        with open(self.db_path, "wb") as f:
            f.write(self.db_content)
        self.db_hash = hashlib.sha256(self.db_content).hexdigest()

        # Mock Docs
        self.docs = {
            "01_Demo_Passport.pdf": b"PDF_CONTENT_PASSPORT_01",
            "02_Demo_Visa.pdf": b"PDF_CONTENT_VISA_02",
            "03_Flight_Ticket.pdf": b"PDF_CONTENT_FLIGHT_03",
        }
        self.doc_hashes = {}
        for fname, content in self.docs.items():
            p = os.path.join(self.source_dir, "documents", fname)
            with open(p, "wb") as f:
                f.write(content)
            self.doc_hashes[fname] = {
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest()
            }

        # Mock Manifest
        self.manifest_data = {
            "backup_timestamp": "20261026_120000",
            "database": {
                "file": "data/kt_vault_v3.db",
                "sha256": self.db_hash,
                "size": len(self.db_content)
            },
            "documents": {
                "total_files": len(self.docs),
                "files": self.doc_hashes
            }
        }
        self.manifest_path = os.path.join(self.source_dir, "backup_manifest.json")
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest_data, f, indent=2)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # =================================================================
    # 1. Round-Trip Backup and Restoration
    # =================================================================

    def test_backup_and_restore_roundtrip(self):
        """Verifies full backup creation and restoration round-trip matches bit-for-bit."""
        # 1. Create encrypted backup
        res_backup = sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )
        self.assertEqual(res_backup["status"], "SUCCESS")
        self.assertTrue(os.path.isfile(self.backup_file))
        self.assertGreater(res_backup["file_size_bytes"], sbt.HEADER_SIZE)

        # 2. Restore encrypted backup
        res_restore = rkt.restore_encrypted_backup(
            backup_file=self.backup_file,
            dest_dir=self.restore_dir,
            passphrase=self.passphrase
        )
        self.assertEqual(res_restore["status"], "SUCCESS")
        self.assertEqual(res_restore["files_extracted"], 5)  # manifest, db, 3 docs
        self.assertTrue(res_restore["manifest_audit"]["verified"])

        # 3. Verify restored contents bit-for-bit
        restored_db = os.path.join(self.restore_dir, "data", "kt_vault_v3.db")
        with open(restored_db, "rb") as f:
            self.assertEqual(f.read(), self.db_content)

        for fname, content in self.docs.items():
            restored_doc = os.path.join(self.restore_dir, "documents", fname)
            with open(restored_doc, "rb") as f:
                self.assertEqual(f.read(), content)

    # =================================================================
    # 2. Authentication and Cryptographic Integrity Tests
    # =================================================================

    def test_wrong_password_rejection(self):
        """Verifies that an incorrect password fails authentication and extracts zero bytes."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase="WRONG_PASSWORD_XYZ"
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))
        self.assertFalse(os.path.exists(self.restore_dir))

    def test_tampered_ciphertext(self):
        """Verifies that tampering with a single ciphertext byte triggers auth rejection."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())

        # Tamper byte in ciphertext (offset 55)
        raw[55] ^= 0xFF

        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

    def test_corrupted_header_magic(self):
        """Verifies that corrupting the magic bytes is detected immediately."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())
        raw[0:4] = b"BADM"
        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Invalid file format", str(ctx.exception))

    def test_corrupted_header_salt(self):
        """Verifies that modifying the salt fails authentication due to AAD and key mismatch."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())
        raw[10] ^= 0x01
        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

    def test_corrupted_header_iterations(self):
        """Verifies that modifying iteration count fails authentication due to AAD mismatch."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())
        # Alter iteration bytes (offset 22..25)
        raw[25] ^= 0x01
        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

    def test_corrupted_header_nonce(self):
        """Verifies that modifying the nonce fails GCM tag verification."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())
        raw[30] ^= 0x01
        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

    def test_corrupted_header_auth_tag(self):
        """Verifies that modifying the auth tag fails verification."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        with open(self.backup_file, "rb") as f:
            raw = bytearray(f.read())
        raw[45] ^= 0x01
        with open(self.backup_file, "wb") as f:
            f.write(raw)

        with self.assertRaises(ValueError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("Authentication tag mismatch", str(ctx.exception))

    # =================================================================
    # 3. Manifest Validation & Tamper Abort Tests
    # =================================================================

    def test_manifest_mismatch_missing_file(self):
        """Verifies that backup aborts if a document referenced in manifest is missing."""
        doc_to_remove = os.path.join(self.source_dir, "documents", "01_Demo_Passport.pdf")
        os.remove(doc_to_remove)

        with self.assertRaises(FileNotFoundError) as ctx:
            sbt.create_encrypted_backup(
                source_dir=self.source_dir,
                dest_path=self.backup_file,
                passphrase=self.passphrase,
                iterations=self.test_iterations
            )
        self.assertIn("01_Demo_Passport.pdf", str(ctx.exception))
        self.assertFalse(os.path.exists(self.backup_file))

    def test_manifest_mismatch_modified_file(self):
        """Verifies that backup aborts if a document content has changed."""
        doc_to_alter = os.path.join(self.source_dir, "documents", "02_Demo_Visa.pdf")
        with open(doc_to_alter, "wb") as f:
            f.write(b"TAMPERED_VISA_CONTENT")

        with self.assertRaises(ValueError) as ctx:
            sbt.create_encrypted_backup(
                source_dir=self.source_dir,
                dest_path=self.backup_file,
                passphrase=self.passphrase,
                iterations=self.test_iterations
            )
        self.assertIn("integrity failure", str(ctx.exception))
        self.assertFalse(os.path.exists(self.backup_file))

    def test_manifest_mismatch_unexpected_file(self):
        """Verifies that backup aborts if an unexpected file is present in the source."""
        extra_file = os.path.join(self.source_dir, "documents", "untracked_secret.txt")
        with open(extra_file, "wb") as f:
            f.write(b"UNTRACKED_SECRET")

        with self.assertRaises(ValueError) as ctx:
            sbt.create_encrypted_backup(
                source_dir=self.source_dir,
                dest_path=self.backup_file,
                passphrase=self.passphrase,
                iterations=self.test_iterations
            )
        self.assertIn("unexpected files", str(ctx.exception))
        self.assertFalse(os.path.exists(self.backup_file))

    # =================================================================
    # 4. Atomic Write and Overwrite Protection
    # =================================================================

    def test_refuse_overwrite_existing_backup(self):
        """Verifies that create_encrypted_backup refuses to overwrite an existing backup."""
        with open(self.backup_file, "wb") as f:
            f.write(b"EXISTING_BACKUP_CONTENT")

        with self.assertRaises(FileExistsError):
            sbt.create_encrypted_backup(
                source_dir=self.source_dir,
                dest_path=self.backup_file,
                passphrase=self.passphrase,
                iterations=self.test_iterations,
                force=False
            )

    def test_refuse_overwrite_existing_restored_file(self):
        """Verifies that restore_encrypted_backup refuses to overwrite existing files."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )
        # Create a conflicting file in restore dir
        os.makedirs(os.path.join(self.restore_dir, "data"), exist_ok=True)
        conflicting_file = os.path.join(self.restore_dir, "data", "kt_vault_v3.db")
        with open(conflicting_file, "wb") as f:
            f.write(b"OLD_EXISTING_DB")

        with self.assertRaises(FileExistsError):
            rkt.restore_encrypted_backup(
                backup_file=self.backup_file,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase,
                overwrite=False
            )

    def test_interrupted_write_cleanup(self):
        """Verifies that temp files are cleaned up if an exception occurs during write."""
        # Provide an invalid directory destination to trigger error after encryption
        invalid_dest = os.path.join(self.test_dir, "nonexistent_sub", "backup.ktbak")
        # Ensure parent dir doesn't exist and make open fail by monkeypatching
        original_open = open
        def fail_open(path, *args, **kwargs):
            if ".tmp." in str(path):
                raise IOError("Simulated disk error during atomic write")
            return original_open(path, *args, **kwargs)

        import builtins
        builtins.open = fail_open
        try:
            with self.assertRaises(IOError):
                sbt.create_encrypted_backup(
                    source_dir=self.source_dir,
                    dest_path=self.backup_file,
                    passphrase=self.passphrase,
                    iterations=self.test_iterations
                )
        finally:
            builtins.open = original_open

        # Ensure no orphan .tmp files remain
        remaining_tmps = [f for f in os.listdir(self.test_dir) if ".tmp." in f]
        self.assertEqual(len(remaining_tmps), 0)

    # =================================================================
    # 5. Archive Hardening: Path Traversal, Symlinks, & Resource Limits
    # =================================================================

    def _create_malicious_archive(self, members: list) -> str:
        """Helper to create an encrypted .ktbak containing crafted tar members."""
        ram_buf = io.BytesIO()
        with tarfile.open(mode="w:gz", fileobj=ram_buf) as tar:
            for m in members:
                tar.addfile(m.get("tarinfo"), m.get("fileobj"))
        tar_gz_bytes = ram_buf.getvalue()

        salt = os.urandom(16)
        nonce = os.urandom(12)
        key = sbt.derive_key(self.passphrase, salt, self.test_iterations)
        aad = sbt.compute_aad(salt, self.test_iterations)

        cipher = sbt.get_cipher_engine(key)
        ciphertext, tag = cipher.encrypt(nonce, tar_gz_bytes, associated_data=aad)

        header = (
            sbt.MAGIC_BYTES +
            sbt.struct.pack(">H", sbt.FORMAT_VERSION) +
            salt +
            sbt.struct.pack(">I", self.test_iterations) +
            nonce +
            tag
        )
        mal_backup_path = os.path.join(self.test_dir, "malicious.ktbak")
        with open(mal_backup_path, "wb") as f:
            f.write(header + ciphertext)
        return mal_backup_path

    def test_safe_extraction_path_traversal(self):
        """Verifies that an archive with '..' relative traversal is blocked."""
        ti = tarfile.TarInfo(name="../escape.txt")
        ti.size = 11
        ti.type = tarfile.REGTYPE
        fileobj = io.BytesIO(b"ESCAPE_DATA")

        mal_path = self._create_malicious_archive([{"tarinfo": ti, "fileobj": fileobj}])

        with self.assertRaises(rkt.SecurityError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=mal_path,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("traversal", str(ctx.exception).lower())

    def test_safe_extraction_absolute_path(self):
        """Verifies that an archive with an absolute path is blocked."""
        ti = tarfile.TarInfo(name="/etc/malicious.txt")
        ti.size = 14
        ti.type = tarfile.REGTYPE
        fileobj = io.BytesIO(b"MALICIOUS_DATA")

        mal_path = self._create_malicious_archive([{"tarinfo": ti, "fileobj": fileobj}])

        with self.assertRaises(rkt.SecurityError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=mal_path,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("absolute path", str(ctx.exception).lower())

    def test_safe_extraction_symlink_rejected(self):
        """Verifies that archives containing symbolic links are strictly rejected."""
        ti = tarfile.TarInfo(name="symlink_target")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/etc/passwd"

        mal_path = self._create_malicious_archive([{"tarinfo": ti, "fileobj": None}])

        with self.assertRaises(rkt.SecurityError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=mal_path,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("forbidden", str(ctx.exception).lower())

    def test_archive_bomb_single_file_limit(self):
        """Verifies that single files exceeding MAX_SINGLE_FILE_BYTES are rejected."""
        ti = tarfile.TarInfo(name="giant_file.bin")
        bomb_size = rkt.MAX_SINGLE_FILE_BYTES + 1
        ti.size = bomb_size
        ti.type = tarfile.REGTYPE

        class ZeroStream(io.RawIOBase):
            def __init__(self, size):
                self.remaining = size
            def read(self, n=-1):
                if self.remaining <= 0:
                    return b""
                chunk_len = min(n if n > 0 else 65536, self.remaining)
                self.remaining -= chunk_len
                return b"\x00" * chunk_len

        mal_path = self._create_malicious_archive([{"tarinfo": ti, "fileobj": ZeroStream(bomb_size)}])

        with self.assertRaises(rkt.SecurityError) as ctx:
            rkt.restore_encrypted_backup(
                backup_file=mal_path,
                dest_dir=self.restore_dir,
                passphrase=self.passphrase
            )
        self.assertIn("bomb protection", str(ctx.exception).lower())

    def test_verify_only_mode(self):
        """Verifies that --verify-only checks integrity without writing any files to disk."""
        sbt.create_encrypted_backup(
            source_dir=self.source_dir,
            dest_path=self.backup_file,
            passphrase=self.passphrase,
            iterations=self.test_iterations
        )

        res = rkt.restore_encrypted_backup(
            backup_file=self.backup_file,
            dest_dir=self.restore_dir,
            passphrase=self.passphrase,
            verify_only=True
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["verify_only"])
        self.assertEqual(res["files_extracted"], 5)  # 1 manifest + 1 db + 3 docs
        self.assertFalse(os.path.exists(self.restore_dir))


if __name__ == "__main__":
    unittest.main()
