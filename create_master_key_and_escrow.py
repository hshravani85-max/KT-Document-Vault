"""
KT Vault V3 - Checkpoint 3B: Operator-Controlled Master Key and Recovery Escrow
Phase 15B-3B.5 Implementation

Executes:
1. Preflight safety checks: verifies maintenance mode is active, zero writers,
   and neither the DPAPI key file nor the escrow destination already exists.
2. Prompts operator interactively for recovery escrow passphrase BEFORE key creation.
3. Generates 256-bit cryptographically secure key (ktv_2026_v1).
4. Persists key under Windows DPAPI (CryptProtectData).
5. Exports cross-platform recovery package via KeyEscrowService (AES-256-GCM / 600k iterations).
6. Performs non-destructive in-memory verification against DPAPI key.
7. Purges all raw key and passphrase variables from memory.

Safety Guarantee:
  Never prints, logs, or transmits raw key bytes or passphrases.
"""

import os
import sys
import secrets
import getpass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage_service
import key_management


def main():
    print("=" * 65)
    print("KT VAULT V3 - PHASE 15B-3B.5: CHECKPOINT 3B")
    print("OPERATOR-CONTROLLED MASTER KEY & RECOVERY ESCROW")
    print("=" * 65)

    # 1. Verify Maintenance Mode Guard
    if not storage_service.is_maintenance_mode():
        print("\n[CRITICAL ERROR] Maintenance mode is NOT active!", file=sys.stderr)
        print("Master key setup must occur strictly under dual maintenance mode.", file=sys.stderr)
        sys.exit(1)

    key_id = "ktv_2026_v1"
    provider = key_management.WindowsDPAPIKeyProvider()
    dpapi_path = provider._get_key_path(key_id)
    escrow_path = r"C:\KT_Vault_Backup_Safe\ktv_2026_v1_escrow.json"

    # 2. Collision / Overwrite Prevention
    if os.path.exists(dpapi_path):
        print(f"\n[ABORT] DPAPI key file already exists at: {dpapi_path}", file=sys.stderr)
        print("Overwriting existing production keys is strictly prohibited.", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(escrow_path):
        print(f"\n[ABORT] Key escrow package already exists at: {escrow_path}", file=sys.stderr)
        print("Overwriting existing key escrow files is strictly prohibited.", file=sys.stderr)
        sys.exit(1)

    # 3. Prompt for Escrow Passphrase BEFORE generating or persisting key
    print("\n[STEP 1/5] Operator Escrow Passphrase Collection")
    print("Please enter a new, high-entropy passphrase to protect the master key escrow.")
    print("Minimum length: 12 characters. (This is distinct from the KT Vault backup passphrase.)\n")

    p1 = getpass.getpass("Enter Key Escrow Passphrase: ")
    p2 = getpass.getpass("Confirm Key Escrow Passphrase: ")

    if p1 != p2:
        print("\n[ABORT] Passphrases do not match. No key was generated.", file=sys.stderr)
        sys.exit(1)

    passphrase = p1.strip()
    if len(passphrase) < 12:
        print("\n[ABORT] Passphrase is shorter than 12 characters. No key was generated.", file=sys.stderr)
        sys.exit(1)

    # 4. Generate 256-bit Master Key
    print(f"\n[STEP 2/5] Generating 256-bit Master Key ('{key_id}')...")
    raw_key = secrets.token_bytes(32)
    fingerprint = key_management.KeyEscrowService.compute_fingerprint(raw_key)

    # 5. Persist via Windows DPAPI
    print("[STEP 3/5] Persisting key via Windows DPAPI (CryptProtectData)...")
    try:
        actual_dpapi_path = provider.save_key(key_id, raw_key)
        print(f"          Successfully saved: {actual_dpapi_path}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed to save key via DPAPI: {e}", file=sys.stderr)
        sys.exit(1)

    # 6. Export Encrypted Escrow Package
    print(f"[STEP 4/5] Exporting disaster recovery escrow to: {escrow_path}...")
    try:
        actual_escrow_path = key_management.KeyEscrowService.export_escrow_file(
            key=raw_key,
            key_id=key_id,
            passphrase=passphrase,
            output_path=escrow_path,
            iterations=key_management.DEFAULT_PBKDF2_ITERATIONS
        )
        print(f"          Successfully exported: {actual_escrow_path}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Failed to export escrow file: {e}", file=sys.stderr)
        print(f"PARTIAL STATE WARNING: DPAPI key exists at {actual_dpapi_path}, but escrow export failed!", file=sys.stderr)
        sys.exit(1)

    # 7. In-Memory Verification
    print("[STEP 5/5] Performing non-destructive escrow decryption verification in RAM...")
    try:
        recovered_id, recovered_key = key_management.KeyEscrowService.import_escrow_file(
            actual_escrow_path,
            passphrase
        )
        assert recovered_id == key_id, "Recovered key ID mismatch!"
        assert recovered_key == raw_key, "Recovered key bytes mismatch!"
        assert recovered_key == provider.get_key(key_id), "Recovered key does not match live DPAPI key!"
        rec_fp = key_management.KeyEscrowService.compute_fingerprint(recovered_key)
        assert rec_fp == fingerprint, "Fingerprint verification mismatch!"
        print(f"          Escrow Verification: PASS")
        print(f"          Key Fingerprint:     {fingerprint}")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Escrow verification failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 8. Memory Hygiene
        del p1, p2, passphrase, raw_key
        if "recovered_key" in locals():
            del recovered_key

    print("\n" + "=" * 65)
    print("CHECKPOINT 3B SUCCESSFUL: MASTER KEY AND ESCROW VERIFIED")
    print(f"DPAPI Key:   {actual_dpapi_path}")
    print(f"Escrow File: {actual_escrow_path}")
    print(f"Fingerprint: {fingerprint}")
    print("=" * 65)


if __name__ == "__main__":
    main()
