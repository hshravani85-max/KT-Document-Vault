"""
KT Vault V3 - Phase 15B-3B.2 Test Suite
Tests for Encryption Key Management, Versioned Envelope (KTV2), Windows DPAPI, and Disaster Recovery Escrow.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import secrets

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage_service
from storage_service import (
    StaticKeyProvider,
    FailClosedKeyProvider,
    _encrypt_envelope,
    _decrypt_envelope,
    get_envelope_metadata,
    is_encrypted_bytes,
    is_encrypted_file,
    write_encrypted_file,
    read_decrypted_document,
    ENVELOPE_MAGIC_V1,
    ENVELOPE_MAGIC_V2,
    ENVELOPE_VERSION_V1,
    ENVELOPE_VERSION_V2,
    HEADER_SIZE_V1,
    HEADER_SIZE_V2
)
import key_management
from key_management import (
    WindowsDPAPIKeyProvider,
    KeyEscrowService,
    is_dpapi_supported,
    ESCROW_FORMAT_VERSION
)


class TestPhase15B3B2KeyManagement(unittest.TestCase):
    """
    Comprehensive verification for Phase 15B-3B.2:
    - Windows DPAPI local key storage
    - Cross-platform disaster recovery escrow (PBKDF2 + AES-GCM)
    - Versioned key identification (KTV2 envelopes)
    - Multi-key rotation and simulated machine migration
    - Fail-closed security and secrecy verification
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ktv_test_km_")
        self.test_key_v1 = secrets.token_bytes(32)
        self.test_key_v2 = secrets.token_bytes(32)
        self.passphrase = "SecureAdminPassphrase2026!"

    def tearDown(self):
        storage_service.reset_key_provider()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # =================================================================
    # 1. Windows DPAPI Key Provider Tests
    # =================================================================

    def test_dpapi_supported_on_windows(self):
        """Verifies that Windows DPAPI is reported as supported on Windows."""
        if sys.platform == "win32":
            self.assertTrue(is_dpapi_supported(), "DPAPI should be supported on Windows.")

    @unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows OS")
    def test_dpapi_save_and_retrieve_key(self):
        """Verifies saving a 256-bit key encrypted with DPAPI and decrypting it back."""
        keys_dir = os.path.join(self.temp_dir, "keys")
        provider = WindowsDPAPIKeyProvider(keys_dir=keys_dir)

        # Initially key does not exist
        self.assertFalse(provider.has_key("test_key_1"))
        with self.assertRaises(RuntimeError):
            provider.get_key("test_key_1")

        # Save key
        saved_path = provider.save_key("test_key_1", self.test_key_v1)
        self.assertTrue(os.path.isfile(saved_path))
        self.assertTrue(provider.has_key("test_key_1"))

        # Retrieve key and verify equality
        recovered = provider.get_key("test_key_1")
        self.assertEqual(recovered, self.test_key_v1)

        # Verify on-disk file is NOT plaintext key
        with open(saved_path, "rb") as f:
            disk_bytes = f.read()
        self.assertNotIn(self.test_key_v1, disk_bytes, "Plaintext key must NEVER appear in on-disk DPAPI file.")

    @unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows OS")
    def test_dpapi_invalid_key_length_rejected(self):
        """Verifies that invalid key lengths (e.g. 16 or 64 bytes) are rejected."""
        keys_dir = os.path.join(self.temp_dir, "keys")
        provider = WindowsDPAPIKeyProvider(keys_dir=keys_dir)

        with self.assertRaises(ValueError):
            provider.save_key("short_key", b"only_16_bytes___")

        with self.assertRaises(ValueError):
            provider.save_key("long_key", b"x" * 64)

    @unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows OS")
    def test_dpapi_list_keys(self):
        """Verifies listing all stored key IDs in alphabetical order."""
        keys_dir = os.path.join(self.temp_dir, "keys")
        provider = WindowsDPAPIKeyProvider(keys_dir=keys_dir)

        provider.save_key("beta_key", self.test_key_v1)
        provider.save_key("alpha_key", self.test_key_v2)

        keys = provider.list_keys()
        self.assertEqual(keys, ["alpha_key", "beta_key"])

    def test_dpapi_path_traversal_rejected(self):
        """Verifies path traversal attempts in key_id are blocked."""
        keys_dir = os.path.join(self.temp_dir, "keys")
        provider = WindowsDPAPIKeyProvider(keys_dir=keys_dir)

        for bad_id in ["../evil", "..\\evil", "sub/dir", "key*name", "key:name"]:
            with self.assertRaises(ValueError):
                provider._get_key_path(bad_id)

    @unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows OS")
    def test_dpapi_secrecy_repr(self):
        """Verifies that provider __repr__ redacts raw key bytes."""
        keys_dir = os.path.join(self.temp_dir, "keys")
        provider = WindowsDPAPIKeyProvider(keys_dir=keys_dir)
        provider.save_key("secret_key", self.test_key_v1)

        rep = repr(provider)
        self.assertNotIn(self.test_key_v1.hex(), rep)
        self.assertIn("secret_key", rep)

    # =================================================================
    # 2. Key Escrow & Disaster Recovery Tests
    # =================================================================

    def test_escrow_create_and_recover_package(self):
        """Verifies creating an escrow package and recovering the original key."""
        pkg = KeyEscrowService.create_escrow_package(
            key=self.test_key_v1,
            key_id="vault_2026_k1",
            passphrase=self.passphrase,
            iterations=100000  # fast for unit tests
        )

        self.assertEqual(pkg["format"], ESCROW_FORMAT_VERSION)
        self.assertEqual(pkg["key_id"], "vault_2026_k1")
        self.assertEqual(pkg["kdf"]["algorithm"], "PBKDF2-HMAC-SHA256")
        self.assertEqual(pkg["encryption"]["algorithm"], "AES-256-GCM")

        # Assert plaintext key is not in JSON package
        pkg_json = json.dumps(pkg)
        self.assertNotIn(self.test_key_v1.hex(), pkg_json)

        # Recover key
        recovered_id, recovered_key = KeyEscrowService.recover_key_from_escrow_package(
            pkg, self.passphrase
        )
        self.assertEqual(recovered_id, "vault_2026_k1")
        self.assertEqual(recovered_key, self.test_key_v1)

    def test_escrow_wrong_passphrase_rejected(self):
        """Verifies recovery fails closed when an incorrect passphrase is supplied."""
        pkg = KeyEscrowService.create_escrow_package(
            key=self.test_key_v1,
            key_id="vault_2026_k1",
            passphrase=self.passphrase,
            iterations=100000
        )

        with self.assertRaises(ValueError) as ctx:
            KeyEscrowService.recover_key_from_escrow_package(pkg, "WrongPasswordHere123!")
        self.assertIn("Key recovery failed", str(ctx.exception))

    def test_escrow_tampered_ciphertext_rejected(self):
        """Verifies tamper detection on escrow ciphertext or authentication tag."""
        pkg = KeyEscrowService.create_escrow_package(
            key=self.test_key_v1,
            key_id="vault_2026_k1",
            passphrase=self.passphrase,
            iterations=100000
        )

        # Tamper with ciphertext
        ct_bytes = bytearray(bytes.fromhex(pkg["encryption"]["ciphertext_hex"]))
        ct_bytes[0] ^= 0xFF
        pkg["encryption"]["ciphertext_hex"] = ct_bytes.hex()

        with self.assertRaises(ValueError) as ctx:
            KeyEscrowService.recover_key_from_escrow_package(pkg, self.passphrase)
        self.assertIn("Key recovery failed", str(ctx.exception))

    def test_escrow_short_passphrase_rejected(self):
        """Verifies passphrases shorter than 12 characters are rejected."""
        with self.assertRaises(ValueError) as ctx:
            KeyEscrowService.create_escrow_package(
                key=self.test_key_v1,
                key_id="key1",
                passphrase="short",
                iterations=100000
            )
        self.assertIn("must be at least 12 characters", str(ctx.exception))

    def test_escrow_export_and_import_file(self):
        """Verifies file-based export and import of escrow packages."""
        escrow_file = os.path.join(self.temp_dir, "key_escrow_backup.json")

        exported_path = KeyEscrowService.export_escrow_file(
            key=self.test_key_v1,
            key_id="ktv_master_v1",
            passphrase=self.passphrase,
            output_path=escrow_file,
            iterations=100000
        )
        self.assertTrue(os.path.isfile(exported_path))

        # Import from file
        rec_id, rec_key = KeyEscrowService.import_escrow_file(escrow_file, self.passphrase)
        self.assertEqual(rec_id, "ktv_master_v1")
        self.assertEqual(rec_key, self.test_key_v1)

    # =================================================================
    # 3. Versioned Envelope (KTV2) & Multi-Key Storage Tests
    # =================================================================

    def test_ktv2_envelope_header_structure(self):
        """Verifies KTV2 envelope has 50-byte header with embedded key_id."""
        payload = b"Top secret customer travel passport data"
        storage_id = "test_passport.pdf"
        envelope = _encrypt_envelope(
            payload, storage_id, self.test_key_v1, key_id="ktv_2026_v1", version=ENVELOPE_VERSION_V2
        )

        self.assertEqual(envelope[:4], ENVELOPE_MAGIC_V2)
        self.assertTrue(is_encrypted_bytes(envelope))
        self.assertEqual(len(envelope), HEADER_SIZE_V2 + len(payload))

        meta = get_envelope_metadata(envelope)
        self.assertEqual(meta["magic"], "KTV2")
        self.assertEqual(meta["version"], 1)
        self.assertEqual(meta["key_id"], "ktv_2026_v1")
        self.assertEqual(meta["header_size"], HEADER_SIZE_V2)
        self.assertEqual(meta["ciphertext_length"], len(payload))

    def test_ktv2_automatic_key_resolution_and_decryption(self):
        """Verifies _decrypt_envelope extracts key_id from KTV2 header and resolves key."""
        payload = b"Classified itinerary information"
        storage_id = "itinerary_doc.pdf"

        envelope = _encrypt_envelope(
            payload, storage_id, self.test_key_v1, key_id="ktv_key_a", version=ENVELOPE_VERSION_V2
        )

        # Create multi-key provider
        provider = StaticKeyProvider({
            "ktv_key_a": self.test_key_v1,
            "ktv_key_b": self.test_key_v2
        })

        # Decrypt without explicitly supplying key; provider resolves automatically via key_id
        decrypted = _decrypt_envelope(envelope, storage_id, key_provider=provider)
        self.assertEqual(decrypted, payload)

    def test_ktv2_missing_key_in_provider_fails_closed(self):
        """Verifies decryption fails when key_id in KTV2 envelope is not in key provider."""
        payload = b"Important document"
        envelope = _encrypt_envelope(
            payload, "file.pdf", self.test_key_v1, key_id="missing_key", version=ENVELOPE_VERSION_V2
        )

        provider = StaticKeyProvider({"other_key": self.test_key_v2})

        with self.assertRaises(RuntimeError) as ctx:
            _decrypt_envelope(envelope, "file.pdf", key_provider=provider)
        self.assertIn("missing_key", str(ctx.exception))

    def test_ktv2_tamper_detection(self):
        """Verifies tampering with KTV2 ciphertext, nonce, or key_id fails authentication."""
        payload = b"Protected travel voucher"
        storage_id = "voucher.pdf"
        envelope = bytearray(_encrypt_envelope(
            payload, storage_id, self.test_key_v1, key_id="test_key", version=ENVELOPE_VERSION_V2
        ))

        # Tamper with key_id in header (bytes 6..21)
        envelope[6] ^= 0xFF
        with self.assertRaises(ValueError):
            _decrypt_envelope(bytes(envelope), storage_id, self.test_key_v1)

    # =================================================================
    # 4. Multi-Key Rotation and Coexistence
    # =================================================================

    def test_multi_key_rotation_and_coexistence(self):
        """Verifies documents encrypted under different keys coexist and decrypt seamlessly."""
        doc1_plain = b"Passport of Traveller 1"
        doc2_plain = b"Visa of Traveller 2"

        env1 = _encrypt_envelope(doc1_plain, "doc1.pdf", self.test_key_v1, key_id="k2025", version=ENVELOPE_VERSION_V2)
        env2 = _encrypt_envelope(doc2_plain, "doc2.pdf", self.test_key_v2, key_id="k2026", version=ENVELOPE_VERSION_V2)

        provider = StaticKeyProvider({
            "k2025": self.test_key_v1,
            "k2026": self.test_key_v2
        })

        self.assertEqual(_decrypt_envelope(env1, "doc1.pdf", key_provider=provider), doc1_plain)
        self.assertEqual(_decrypt_envelope(env2, "doc2.pdf", key_provider=provider), doc2_plain)

    # =================================================================
    # 5. Computer Migration & Disaster Recovery Simulation
    # =================================================================

    @unittest.skipUnless(sys.platform == "win32", "DPAPI requires Windows OS")
    def test_simulated_computer_migration(self):
        """
        Simulates end-to-end disaster recovery / machine migration:
        1. Computer A stores key in its local DPAPI store.
        2. Computer A encrypts customer document (KTV2).
        3. Computer A exports key to an encrypted escrow package with admin passphrase.
        4. Simulated Computer B (isolated DPAPI directory) receives the document and escrow file.
        5. Computer B cannot initially decrypt the document (key missing).
        6. Computer B imports the escrow file using the admin passphrase into its own DPAPI store.
        7. Computer B successfully decrypts the document!
        """
        dir_machine_a = os.path.join(self.temp_dir, "machine_a_keys")
        dir_machine_b = os.path.join(self.temp_dir, "machine_b_keys")
        escrow_file = os.path.join(self.temp_dir, "transfer_escrow.json")

        # Computer A setup
        provider_a = WindowsDPAPIKeyProvider(keys_dir=dir_machine_a)
        provider_a.save_key("ktv_master_2026", self.test_key_v1)

        # Computer A encrypts document
        secret_document = b"Customer confidential passport copy - Machine A"
        storage_id = "cust_pass_001.pdf"
        doc_envelope = _encrypt_envelope(
            secret_document, storage_id, self.test_key_v1, key_id="ktv_master_2026", version=ENVELOPE_VERSION_V2
        )

        # Computer A exports escrow package
        KeyEscrowService.export_escrow_file(
            key=self.test_key_v1,
            key_id="ktv_master_2026",
            passphrase=self.passphrase,
            output_path=escrow_file,
            iterations=100000
        )

        # Computer B setup (isolated store)
        provider_b = WindowsDPAPIKeyProvider(keys_dir=dir_machine_b)
        self.assertFalse(provider_b.has_key("ktv_master_2026"))

        # Computer B attempts decryption before recovery -> Fails
        with self.assertRaises(RuntimeError):
            _decrypt_envelope(doc_envelope, storage_id, key_provider=provider_b)

        # Computer B recovers key from escrow file into its DPAPI store
        rec_id, rec_key = KeyEscrowService.import_escrow_file(escrow_file, self.passphrase)
        provider_b.save_key(rec_id, rec_key)

        # Computer B now successfully decrypts the document!
        decrypted = _decrypt_envelope(doc_envelope, storage_id, key_provider=provider_b)
        self.assertEqual(decrypted, secret_document)

    # =================================================================
    # 6. Backward Compatibility with KTV1 Envelopes
    # =================================================================

    def test_ktv1_backward_compatibility(self):
        """Verifies that existing KTV1 envelopes decrypt seamlessly alongside KTV2."""
        payload = b"Existing KTV1 document content"
        storage_id = "legacy_doc.pdf"
        envelope_v1 = _encrypt_envelope(payload, storage_id, self.test_key_v1, version=ENVELOPE_VERSION_V1)

        self.assertEqual(envelope_v1[:4], ENVELOPE_MAGIC_V1)
        self.assertTrue(is_encrypted_bytes(envelope_v1))

        # Decrypt using provider with 'master' key
        provider = StaticKeyProvider({"master": self.test_key_v1})
        decrypted = _decrypt_envelope(envelope_v1, storage_id, key_provider=provider)
        self.assertEqual(decrypted, payload)


if __name__ == "__main__":
    unittest.main()
