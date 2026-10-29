"""
KT Vault V3 - Checkpoint 3B: Safe Key Escrow Passphrase Rotation
Phase 15B-3B.5 Implementation

Purpose:
  Safely re-exports the existing Windows DPAPI master key (ktv_2026_v1)
  under a NEW operator-chosen escrow passphrase to a NEW escrow file.
  
Guarantees:
  1. DOES NOT generate or modify the master key.
  2. DOES NOT overwrite or delete the existing escrow file.
  3. Enforces maintenance mode.
  4. Validates key fingerprint (eb3dbffe98475f7a) before and after rotation.
  5. Verifies in-memory decryption before completing.
"""

import os
import sys
import getpass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage_service
import key_management

EXPECTED_FINGERPRINT = "eb3dbffe98475f7a"
KEY_ID = "ktv_2026_v1"
ORIGINAL_ESCROW_PATH = r"C:\KT_Vault_Backup_Safe\ktv_2026_v1_escrow.json"
ROTATED_ESCROW_PATH = r"C:\KT_Vault_Backup_Safe\ktv_2026_v1_escrow_v2.json"


def main():
    print("=" * 65)
    print("KT VAULT V3 - ESCROW PASSPHRASE ROTATION")
    print(f"Target Key ID: {KEY_ID} (Fingerprint: {EXPECTED_FINGERPRINT})")
    print("=" * 65)

    # 1. Maintenance Mode Check
    if not storage_service.is_maintenance_mode():
        print("\n[CRITICAL ERROR] Maintenance mode is NOT active!", file=sys.stderr)
        sys.exit(1)

    # 2. Verify Existing DPAPI Key
    provider = key_management.WindowsDPAPIKeyProvider()
    if not provider.has_key(KEY_ID):
        print(f"\n[CRITICAL ERROR] DPAPI key '{KEY_ID}' does not exist!", file=sys.stderr)
        sys.exit(1)

    raw_key = provider.get_key(KEY_ID)
    current_fp = key_management.KeyEscrowService.compute_fingerprint(raw_key)
    if current_fp != EXPECTED_FINGERPRINT:
        print(f"\n[CRITICAL ERROR] Fingerprint mismatch! Found {current_fp}, expected {EXPECTED_FINGERPRINT}", file=sys.stderr)
        sys.exit(1)

    # 3. Collision Prevention for Rotated Escrow
    if os.path.exists(ROTATED_ESCROW_PATH):
        print(f"\n[ABORT] Rotated escrow file already exists at: {ROTATED_ESCROW_PATH}", file=sys.stderr)
        print("Will not overwrite existing escrow file.", file=sys.stderr)
        sys.exit(1)

    # 4. Prompt for NEW Passphrase BEFORE proceeding
    print("\n[STEP 1/4] Operator New Escrow Passphrase Collection")
    print("Enter a NEW, high-entropy passphrase to protect the master key escrow.")
    print("Minimum length: 12 characters.\n")

    p1 = getpass.getpass("Enter NEW Key Escrow Passphrase: ")
    p2 = getpass.getpass("Confirm NEW Key Escrow Passphrase: ")

    if p1 != p2:
        print("\n[ABORT] Passphrases do not match. No changes made.", file=sys.stderr)
        sys.exit(1)

    passphrase = p1.strip()
    if len(passphrase) < 12:
        print("\n[ABORT] Passphrase is shorter than 12 characters. No changes made.", file=sys.stderr)
        sys.exit(1)

    # 5. Export NEW Escrow Package
    print(f"\n[STEP 2/4] Exporting replacement escrow to: {ROTATED_ESCROW_PATH}...")
    try:
        actual_path = key_management.KeyEscrowService.export_escrow_file(
            key=raw_key,
            key_id=KEY_ID,
            passphrase=passphrase,
            output_path=ROTATED_ESCROW_PATH,
            iterations=key_management.DEFAULT_PBKDF2_ITERATIONS
        )
        print(f"          Successfully exported: {actual_path}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed to export replacement escrow: {e}", file=sys.stderr)
        sys.exit(1)

    # 6. In-Memory Verification
    print("[STEP 3/4] Verifying recovery of replacement escrow in RAM...")
    try:
        rec_id, rec_key = key_management.KeyEscrowService.import_escrow_file(
            actual_path,
            passphrase
        )
        assert rec_id == KEY_ID, f"Recovered key ID mismatch: {rec_id}"
        assert rec_key == raw_key, "Recovered key bytes mismatch!"
        rec_fp = key_management.KeyEscrowService.compute_fingerprint(rec_key)
        assert rec_fp == EXPECTED_FINGERPRINT, f"Fingerprint mismatch: {rec_fp}"
        print(f"          In-Memory Recovery: PASS")
        print(f"          Key Fingerprint:    {rec_fp}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Escrow verification failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 7. Memory Hygiene
        del p1, p2, passphrase, raw_key
        if "rec_key" in locals():
            del rec_key

    print("\n[STEP 4/4] Verification Summary")
    print("=" * 65)
    print("ROTATION COMPLETE & VERIFIED")
    print(f"Master Key:          UNTOUCHED (DPAPI: ktv_2026_v1)")
    print(f"Original Escrow:     PRESERVED ({ORIGINAL_ESCROW_PATH})")
    print(f"Replacement Escrow:  ACTIVE ({ROTATED_ESCROW_PATH})")
    print(f"Verified Fingerprint:{EXPECTED_FINGERPRINT}")
    print("=" * 65)


if __name__ == "__main__":
    main()
