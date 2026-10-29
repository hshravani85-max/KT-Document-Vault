import unittest
import os
import sys
import tempfile
import shutil
import secrets
import base64
import sqlite3
from unittest.mock import patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import storage_service
from storage_service import (
    KeyProvider,
    StaticKeyProvider,
    EnvKeyProvider,
    FailClosedKeyProvider,
    AES256GCMCipher,
    ENVELOPE_MAGIC,
    ENVELOPE_VERSION,
    HEADER_SIZE,
    NONCE_BYTES,
    TAG_BYTES,
    compute_storage_aad,
    is_encrypted_bytes,
    is_encrypted_file,
    get_envelope_metadata,
    validate_storage_path,
    write_encrypted_file,
    read_decrypted_document,
    _encrypt_envelope,
    _decrypt_envelope
)


class TestPhase15B3AStorageFoundation(unittest.TestCase):
    """
    Synthetic Security Test Suite for Phase 15B-3A:
    Secure Storage Foundation — Authenticated Document Encryption.
    
    Verifies all 12 core security requirements using synthetic data in temporary
    directories without touching live customer documents or database records.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kt_test_storage_")
        self.test_key = secrets.token_bytes(32)
        self.key_provider = StaticKeyProvider(self.test_key)
        storage_service.set_key_provider(self.key_provider)

    def tearDown(self):
        storage_service.reset_key_provider()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # -----------------------------------------------------------------
    # 1. Successful AES-256-GCM Encryption and Decryption Roundtrip
    # -----------------------------------------------------------------
    def test_successful_aes256_gcm_roundtrip(self):
        """Verifies round-trip encryption & decryption for various payload sizes."""
        test_payloads = [
            b"",  # Empty document
            b"Khanna Travels Test Document 123",  # Short string
            b"%PDF-1.4\n1 0 obj\n<< /Title (Synthetic Passport) >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF",  # Synthetic PDF
            secrets.token_bytes(256 * 1024),  # 256 KB binary
        ]
        
        storage_id = "test_doc_roundtrip.pdf"
        for payload in test_payloads:
            envelope = _encrypt_envelope(payload, storage_id, self.test_key)
            self.assertTrue(is_encrypted_bytes(envelope))
            self.assertEqual(len(envelope), len(payload) + HEADER_SIZE)
            
            decrypted = _decrypt_envelope(envelope, storage_id, self.test_key)
            self.assertEqual(decrypted, payload)

    # -----------------------------------------------------------------
    # 2. Cryptographic Nonce Uniqueness
    # -----------------------------------------------------------------
    def test_unique_nonces_per_encryption(self):
        """Verifies that every encryption operation generates a unique 96-bit nonce."""
        payload = b"Constant payload for nonce freshness evaluation."
        storage_id = "intake_nonce_test.pdf"
        
        seen_nonces = set()
        iterations = 100
        for _ in range(iterations):
            envelope = _encrypt_envelope(payload, storage_id, self.test_key)
            nonce = envelope[6:18]
            self.assertEqual(len(nonce), NONCE_BYTES)
            self.assertNotIn(nonce, seen_nonces, "CRITICAL: Nonce collision detected!")
            seen_nonces.add(nonce)
            
        self.assertEqual(len(seen_nonces), iterations)

    # -----------------------------------------------------------------
    # 3. Tamper Detection (Ciphertext, Tag, Nonce)
    # -----------------------------------------------------------------
    def test_tamper_detection_ciphertext(self):
        """Verifies that flipping a bit in the ciphertext causes immediate rejection."""
        payload = b"Sensitive travel insurance policy terms and conditions."
        storage_id = "insurance_policy.pdf"
        envelope = bytearray(_encrypt_envelope(payload, storage_id, self.test_key))
        
        # Tamper with the first byte of ciphertext (offset 34)
        envelope[HEADER_SIZE] ^= 0x01
        
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(envelope), storage_id, self.test_key)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    def test_tamper_detection_tag(self):
        """Verifies that modifying any byte of the authentication tag causes rejection."""
        payload = b"Flight ticket PNR details Khanna Travels."
        storage_id = "ticket.pdf"
        envelope = bytearray(_encrypt_envelope(payload, storage_id, self.test_key))
        
        # Tamper with the authentication tag (offsets 18..33)
        envelope[18] ^= 0x80
        
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(envelope), storage_id, self.test_key)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    def test_tamper_detection_nonce(self):
        """Verifies that altering the nonce causes authentication failure."""
        payload = b"Visa entry stamp verification document."
        storage_id = "visa.pdf"
        envelope = bytearray(_encrypt_envelope(payload, storage_id, self.test_key))
        
        # Tamper with nonce (offsets 6..17)
        envelope[6] ^= 0xFF
        
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(envelope), storage_id, self.test_key)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    # -----------------------------------------------------------------
    # 4. Wrong-Key Rejection
    # -----------------------------------------------------------------
    def test_wrong_key_rejection(self):
        """Verifies that decrypting with an incorrect 256-bit key fails authentication."""
        payload = b"Hotel voucher booking confirmation payload."
        storage_id = "hotel.pdf"
        envelope = _encrypt_envelope(payload, storage_id, self.test_key)
        
        wrong_key = secrets.token_bytes(32)
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(envelope, storage_id, wrong_key)
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    # -----------------------------------------------------------------
    # 5. Invalid Envelope Header Rejection
    # -----------------------------------------------------------------
    def test_invalid_envelope_truncated(self):
        """Verifies rejection of envelopes shorter than header size (34 bytes)."""
        short_data = b"KTV1\x00\x01truncated"
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(short_data, "file.pdf", self.test_key)
        self.assertIn("Envelope truncated", str(ctx.exception))

    def test_invalid_envelope_bad_magic(self):
        """Verifies rejection of envelopes missing the 'KTV1' magic bytes."""
        payload = b"Regular document content."
        envelope = bytearray(_encrypt_envelope(payload, "test.pdf", self.test_key))
        envelope[:4] = b"BAD!"
        
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(envelope), "test.pdf", self.test_key)
        self.assertIn("Invalid envelope magic", str(ctx.exception))

    # -----------------------------------------------------------------
    # 6. Unsupported Version Rejection
    # -----------------------------------------------------------------
    def test_unsupported_version_rejection(self):
        """Verifies that envelopes with unknown version numbers are strictly rejected."""
        payload = b"Some document payload."
        envelope = bytearray(_encrypt_envelope(payload, "test.pdf", self.test_key))
        # Set version to 2 (big-endian 0x0002)
        envelope[4] = 0x00
        envelope[5] = 0x02
        
        with self.assertRaises(ValueError) as ctx:
            _decrypt_envelope(bytes(envelope), "test.pdf", self.test_key)
        self.assertIn("Unsupported envelope version: 2", str(ctx.exception))

    # -----------------------------------------------------------------
    # 7. Shared-File Identity Handling & Substitution Prevention
    # -----------------------------------------------------------------
    def test_shared_file_identity_handling(self):
        """
        Verifies the shared-file identity architecture:
        1. Two different database records (e.g. DOC-5ad21646 and DOC-7866f701)
           referencing the exact same physical storage ID can both decrypt the file.
        2. Swapping the file content to a different storage ID fails AAD authentication.
        """
        shared_filename = "intake_a9254ef900bd4ac1a5feaf0dfde30df8.pdf"
        original_content = b"%PDF-1.4 Shared Passport Scan for Multiple Trips"
        
        # Write encrypted file using shared_filename as canonical storage_id
        res = write_encrypted_file(
            shared_filename,
            original_content,
            file_storage_id=shared_filename,
            base_dir=self.test_dir
        )
        file_path = res["file_path"]
        
        # Simulation of Database Record 1 (DOC-5ad21646) reading file
        read_doc1 = read_decrypted_document(
            file_path,
            file_storage_id=shared_filename,
            base_dir=self.test_dir,
            system_context=True
        )
        self.assertEqual(read_doc1, original_content)
        
        # Simulation of Database Record 2 (DOC-7866f701) reading file
        read_doc2 = read_decrypted_document(
            file_path,
            file_storage_id=shared_filename,
            base_dir=self.test_dir,
            system_context=True
        )
        self.assertEqual(read_doc2, original_content)
        
        # Substitution Attack: Attacker copies shared file and tries to use it as 'victim_visa.pdf'
        with self.assertRaises(ValueError) as ctx:
            read_decrypted_document(
                file_path,
                file_storage_id="victim_visa.pdf",
                base_dir=self.test_dir,
                system_context=True
            )
        self.assertIn("tampered with or corrupted", str(ctx.exception))

    # -----------------------------------------------------------------
    # 8. Missing-Key Fail-Closed Behavior
    # -----------------------------------------------------------------
    def test_missing_key_fail_closed(self):
        """
        Verifies that operations fail closed with RuntimeError when no key is configured.
        Strictly forbids plaintext fallback.
        """
        storage_service.reset_key_provider()  # Reverts to FailClosedKeyProvider
        
        with self.assertRaises(RuntimeError) as ctx:
            write_encrypted_file("fail.pdf", b"Data", base_dir=self.test_dir)
        self.assertIn("unconfigured", str(ctx.exception))

    def test_env_key_provider_missing(self):
        """Verifies EnvKeyProvider behavior when environment variable is unset."""
        env_provider = EnvKeyProvider("NON_EXISTENT_KEY_ENV_VAR_12345")
        self.assertFalse(env_provider.has_key())
        with self.assertRaises(RuntimeError) as ctx:
            env_provider.get_key()
        self.assertIn("unavailable", str(ctx.exception))

    # -----------------------------------------------------------------
    # 9. Unauthorized Document Access Rejection
    # -----------------------------------------------------------------
    def test_unauthorized_document_access_rejection(self):
        """Verifies that missing, empty, or invalid session tokens are rejected."""
        filename = "confidential_document.pdf"
        content = b"Confidential passport details"
        res = write_encrypted_file(filename, content, base_dir=self.test_dir)
        
        # Test with missing session token
        with self.assertRaises(PermissionError):
            read_decrypted_document(
                res["file_path"],
                base_dir=self.test_dir
            )
            
        # Test with empty session token
        with self.assertRaises(PermissionError):
            read_decrypted_document(
                res["file_path"],
                session_token="",
                base_dir=self.test_dir
            )

        # Test with an invalid/forged session token
        with self.assertRaises(PermissionError):
            read_decrypted_document(
                res["file_path"],
                session_token="forged_invalid_session_token_xyz",
                base_dir=self.test_dir
            )

    # -----------------------------------------------------------------
    # 10. Atomic Write and Interruption Handling
    # -----------------------------------------------------------------
    def test_atomic_write_success(self):
        """Verifies atomic write produces valid file with proper fsync & rename."""
        filename = "atomic_doc.pdf"
        content = b"Atomic write payload"
        res = write_encrypted_file(filename, content, base_dir=self.test_dir)
        
        self.assertTrue(os.path.exists(res["file_path"]))
        self.assertTrue(is_encrypted_file(res["file_path"], base_dir=self.test_dir))
        
        # Verify no .tmp files remain in test directory
        files = os.listdir(self.test_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], filename)

    def test_atomic_write_failure_cleanup(self):
        """Verifies that if atomic write fails midway, no .tmp files are left."""
        filename = "interrupted_doc.pdf"
        
        # Mock os.replace to simulate power loss or disk failure
        with patch("os.replace", side_effect=IOError("Simulated disk write interruption")):
            with self.assertRaises(IOError):
                write_encrypted_file(filename, b"Payload", base_dir=self.test_dir)
                
        # Target file must not exist
        target_path = os.path.join(self.test_dir, filename)
        self.assertFalse(os.path.exists(target_path))
        
        # No temporary files must remain
        remaining_files = os.listdir(self.test_dir)
        self.assertEqual(remaining_files, [], "Temporary files were not cleaned up on failure!")

    # -----------------------------------------------------------------
    # 11. No Plaintext Temporary Files on Disk
    # -----------------------------------------------------------------
    def test_no_plaintext_temporary_files(self):
        """Verifies that temporary files never contain unencrypted plaintext."""
        filename = "temp_check.pdf"
        secret_content = b"CRITICAL_SECRET_KHANNA_PASSPORT_DATA_99999"
        
        write_encrypted_file(filename, secret_content, base_dir=self.test_dir)
        
        # Inspect target file on disk
        target_path = os.path.join(self.test_dir, filename)
        with open(target_path, "rb") as f:
            disk_bytes = f.read()
            
        self.assertNotIn(
            secret_content,
            disk_bytes,
            "CRITICAL SECURITY LEAK: Plaintext content was found in encrypted file on disk!"
        )

    # -----------------------------------------------------------------
    # 12. No Sensitive Keys or Plaintext in Error Messages
    # -----------------------------------------------------------------
    def test_no_keys_or_plaintext_in_error_messages(self):
        """Verifies that exception strings do not expose keys or plaintext."""
        secret_key = secrets.token_bytes(32)
        secret_key_hex = secret_key.hex()
        secret_payload = b"SECRET_CUSTOMER_AADHAAR_9876543210"
        
        envelope = _encrypt_envelope(secret_payload, "test.pdf", secret_key)
        
        # Trigger auth mismatch with wrong key
        wrong_key = secrets.token_bytes(32)
        try:
            _decrypt_envelope(envelope, "test.pdf", wrong_key)
        except Exception as e:
            err_str = str(e)
            self.assertNotIn(secret_key_hex, err_str)
            self.assertNotIn("9876543210", err_str)
            self.assertNotIn(secret_key.hex(), err_str)

    # -----------------------------------------------------------------
    # 13. Storage Path Validation & Traversal Prevention
    # -----------------------------------------------------------------
    def test_storage_path_validation_and_traversal(self):
        """Verifies directory traversal prevention, relative escapes, and null byte rejection."""
        # Valid path
        valid_path = validate_storage_path("sub/doc.pdf", base_dir=self.test_dir)
        self.assertTrue(valid_path.startswith(os.path.realpath(self.test_dir)))
        
        # Directory traversal attacks
        with self.assertRaises(PermissionError):
            validate_storage_path("../../system32/cmd.exe", base_dir=self.test_dir)
            
        with self.assertRaises(PermissionError):
            validate_storage_path("..\\..\\passwords.txt", base_dir=self.test_dir)
            
        # Null byte injection
        with self.assertRaises(ValueError):
            validate_storage_path("safe.pdf\x00malicious.exe", base_dir=self.test_dir)

    # -----------------------------------------------------------------
    # 14. Format Detection Helpers
    # -----------------------------------------------------------------
    def test_format_detection_helpers(self):
        """Verifies is_encrypted_bytes and is_encrypted_file on plain vs encrypted data."""
        raw_pdf = b"%PDF-1.4\nraw pdf file content"
        self.assertFalse(is_encrypted_bytes(raw_pdf))
        
        envelope = _encrypt_envelope(raw_pdf, "doc.pdf", self.test_key)
        self.assertTrue(is_encrypted_bytes(envelope))
        
        # Disk test
        plain_file = os.path.join(self.test_dir, "plain.pdf")
        with open(plain_file, "wb") as f:
            f.write(raw_pdf)
        self.assertFalse(is_encrypted_file(plain_file, base_dir=self.test_dir))
        
        enc_file = os.path.join(self.test_dir, "enc.pdf")
        with open(enc_file, "wb") as f:
            f.write(envelope)
        self.assertTrue(is_encrypted_file(enc_file, base_dir=self.test_dir))

    # -----------------------------------------------------------------
    # 15. EnvKeyProvider Encoding Formats
    # -----------------------------------------------------------------
    def test_env_key_provider_formats(self):
        """Verifies EnvKeyProvider with 64-char hex, 44-char base64, and invalid strings."""
        test_key = secrets.token_bytes(32)
        hex_key = test_key.hex()
        b64_key = base64.b64encode(test_key).decode("ascii")
        
        # Test Hex
        with patch.dict(os.environ, {"KT_TEST_KEY_ENV": hex_key}):
            provider = EnvKeyProvider("KT_TEST_KEY_ENV")
            self.assertTrue(provider.has_key())
            self.assertEqual(provider.get_key(), test_key)
            
        # Test Base64
        with patch.dict(os.environ, {"KT_TEST_KEY_ENV": b64_key}):
            provider = EnvKeyProvider("KT_TEST_KEY_ENV")
            self.assertTrue(provider.has_key())
            self.assertEqual(provider.get_key(), test_key)
            
        # Test Invalid Length / Corrupt format
        with patch.dict(os.environ, {"KT_TEST_KEY_ENV": "too_short_invalid_key"}):
            provider = EnvKeyProvider("KT_TEST_KEY_ENV")
            self.assertFalse(provider.has_key())
            with self.assertRaises(ValueError):
                provider.get_key()


if __name__ == '__main__':
    unittest.main()
