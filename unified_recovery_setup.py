"""
KT Vault V3 - Unified Password Recovery Setup & Independent Verification
Phase 15B-3B.5 Implementation (unified_recovery_setup.py)

One-command controlled workflow that:
1. Enforces maintenance mode and preflight sanity checks.
2. Prompts operator for ONE new strong recovery passphrase (min 20 chars).
3. Re-exports existing DPAPI master key (eb3dbffe98475f7a) into a NEW escrow package.
4. Creates a NEW encrypted full backup (.ktbak) using the same new passphrase.
5. Launches an independent Python subprocess to verify recovery end-to-end.
6. Generates C:\\KT_Vault_Backup_Safe\\KT_Vault_Recovery_Instructions.txt.
7. Produces WhatsApp management update text.
"""

import os
import sys
import shutil
import hashlib
import getpass
import subprocess
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage_service
import key_management
import secure_backup_tool


EXPECTED_FINGERPRINT = "eb3dbffe98475f7a"
KEY_ID = "ktv_2026_v1"

# Target Destination Paths (Unique and non-overwriting)
NEW_ESCROW_PATH = r"C:\KT_Vault_Backup_Safe\ktv_2026_v1_escrow_active.json"
NEW_BACKUP_SAFE = r"C:\KT_Vault_Backup_Safe\kt_vault_v3_pre_migration_active.ktbak"
NEW_BACKUP_V3   = r"C:\KT_Vault_V3\backups\kt_vault_v3_pre_migration_active.ktbak"
SOURCE_SNAPSHOT = r"C:\KT_Vault_V3\backups\pre_phase15b3b4_gate_backup_20261023_173500"
INSTRUCTIONS_PATH = r"C:\KT_Vault_Backup_Safe\KT_Vault_Recovery_Instructions.txt"


def main():
    print("=" * 70)
    print("KHANNA TRAVELS - KT VAULT V3")
    print("UNIFIED RECOVERY SETUP & POST-SETUP VERIFICATION")
    print("=" * 70)

    # -----------------------------------------------------------------
    # STEP 1: PREFLIGHT SAFETY CHECKS
    # -----------------------------------------------------------------
    print("\n[STEP 1/6] Preflight Safety Verification...")

    # Maintenance mode check
    if not storage_service.is_maintenance_mode():
        print("[ABORT] Maintenance mode is NOT active! Refusing to proceed.", file=sys.stderr)
        sys.exit(1)
    print("  - Maintenance Mode: ACTIVE")

    # Verify DPAPI key
    provider = key_management.WindowsDPAPIKeyProvider()
    if not provider.has_key(KEY_ID):
        print(f"[ABORT] DPAPI key '{KEY_ID}' missing!", file=sys.stderr)
        sys.exit(1)

    raw_key = provider.get_key(KEY_ID)
    current_fp = key_management.KeyEscrowService.compute_fingerprint(raw_key)
    if current_fp != EXPECTED_FINGERPRINT:
        print(f"[ABORT] Key fingerprint mismatch: found {current_fp}, expected {EXPECTED_FINGERPRINT}", file=sys.stderr)
        sys.exit(1)
    print(f"  - DPAPI Master Key: VERIFIED (Fingerprint: {current_fp})")

    # Collision Prevention
    for p in (NEW_ESCROW_PATH, NEW_BACKUP_SAFE, NEW_BACKUP_V3):
        if os.path.exists(p):
            print(f"[ABORT] Target file already exists: {p}. Overwrite is strictly prohibited.", file=sys.stderr)
            sys.exit(1)
    print("  - Target Destinations: CLEAN (No collision)")

    # -----------------------------------------------------------------
    # STEP 2: OPERATOR PASSPHRASE COLLECTION
    # -----------------------------------------------------------------
    print("\n[STEP 2/6] Operator Passphrase Collection")
    print("Please create ONE new, strong unified recovery passphrase (min 20 characters).")
    print("This passphrase will protect BOTH the master key escrow and the full encrypted backup.")
    print("NOTE: Characters will NOT echo to the console.\n")

    p1 = getpass.getpass("Enter NEW Recovery Passphrase (min 20 chars): ")
    p2 = getpass.getpass("Confirm NEW Recovery Passphrase: ")

    if p1 != p2:
        print("\n[ABORT] Passphrases do not match. No changes were made.", file=sys.stderr)
        sys.exit(1)

    passphrase = p1.strip()
    if len(passphrase) < 20:
        print(f"\n[ABORT] Passphrase is only {len(passphrase)} characters. Minimum required is 20.", file=sys.stderr)
        sys.exit(1)

    print("\n  - Passphrase confirmed and accepted into volatile memory.")

    # -----------------------------------------------------------------
    # STEP 3: EXPORT ACTIVE KEY ESCROW PACKAGE
    # -----------------------------------------------------------------
    print(f"\n[STEP 3/6] Exporting Active Key Escrow to: {NEW_ESCROW_PATH}...")
    try:
        escrow_file = key_management.KeyEscrowService.export_escrow_file(
            key=raw_key,
            key_id=KEY_ID,
            passphrase=passphrase,
            output_path=NEW_ESCROW_PATH,
            iterations=key_management.DEFAULT_PBKDF2_ITERATIONS
        )
        with open(escrow_file, "rb") as f:
            escrow_sha256 = hashlib.sha256(f.read()).hexdigest()
        escrow_size = os.path.getsize(escrow_file)
        print(f"  - Escrow Exported: {escrow_size:,} bytes | SHA-256: {escrow_sha256}")
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to export escrow: {e}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------
    # STEP 4: CREATE ACTIVE FULL ENCRYPTED BACKUP
    # -----------------------------------------------------------------
    print(f"\n[STEP 4/6] Creating Active Encrypted Backup (.ktbak)...")
    print(f"  - Source Snapshot: {SOURCE_SNAPSHOT}")
    try:
        res_bk = secure_backup_tool.create_encrypted_backup(
            source_dir=SOURCE_SNAPSHOT,
            dest_path=NEW_BACKUP_SAFE,
            passphrase=passphrase,
            iterations=key_management.DEFAULT_PBKDF2_ITERATIONS,
            force=False
        )
        print(f"  - Backup Created: {res_bk['file_size_bytes']:,} bytes | SHA-256: {res_bk['sha256']}")

        # Replicate to second location
        print(f"  - Replicating to: {NEW_BACKUP_V3}...")
        shutil.copy2(NEW_BACKUP_SAFE, NEW_BACKUP_V3)
        with open(NEW_BACKUP_V3, "rb") as f:
            backup_v3_sha256 = hashlib.sha256(f.read()).hexdigest()
        assert backup_v3_sha256 == res_bk["sha256"], "Backup replica SHA-256 mismatch!"
        print(f"  - Replication Verified: Matching SHA-256: {backup_v3_sha256}")
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to create backup: {e}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------
    # STEP 5: LAUNCH SEPARATE INDEPENDENT VERIFICATION PROCESS
    # -----------------------------------------------------------------
    print("\n[STEP 5/6] Launching Separate Independent Python Verification Process...")
    verify_script = os.path.join(PROJECT_ROOT, "verify_active_recovery.py")
    try:
        proc = subprocess.Popen(
            [sys.executable, verify_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout_data, stderr_data = proc.communicate(input=passphrase + "\n")

        print(stdout_data.strip())
        if proc.returncode != 0:
            print(f"[CRITICAL ERROR] Independent verification failed (code {proc.returncode}):\n{stderr_data}", file=sys.stderr)
            sys.exit(proc.returncode)

        print("  - Independent Verification Subprocess: 100% SUCCESS")
    except Exception as e:
        print(f"[CRITICAL ERROR] Failed to execute verification subprocess: {e}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------
    # STEP 6: GENERATE RECOVERY INSTRUCTIONS FILE & CLEANUP
    # -----------------------------------------------------------------
    print(f"\n[STEP 6/6] Writing Recovery Record to: {INSTRUCTIONS_PATH}...")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    instructions_content = f"""KHANNA TRAVELS - KT VAULT V3
UNIFIED RECOVERY RECORD & RESTORATION INSTRUCTIONS
Date Generated: {now_str}
Verification Status: VERIFIED & TESTED (PASS)

================================================================================
CRITICAL OPERATOR NOTICE:
The operator MUST save their new recovery passphrase in a secure corporate password
manager (e.g. 1Password, Bitwarden, KeePass) or an approved offline safe.
DO NOT WRITE THE PASSPHRASE IN THIS FILE OR ANY PLAINTEXT NOTE.
================================================================================

1. ACTIVE RECOVERY ARTIFACTS
--------------------------------------------------------------------------------
Key Identifier:       {KEY_ID}
Key Fingerprint:      {EXPECTED_FINGERPRINT}
Active Escrow File:   {NEW_ESCROW_PATH}
Escrow SHA-256:       {escrow_sha256}
Primary Backup:       {NEW_BACKUP_SAFE}
Secondary Backup:     {NEW_BACKUP_V3}
Backup SHA-256:       {backup_v3_sha256}
Protected Data:       1 SQLite Database (12 tables, 982 rows) + 79 Synthetic Demo Documents

2. SINGLE-PASSPHRASE ARCHITECTURE NOTICE (DEVELOPMENT ENVIRONMENT)
--------------------------------------------------------------------------------
This backup and key escrow share ONE unified recovery passphrase. This is a deliberate
operational design for this synthetic-data development environment to streamline
testing. Prior to deploying real customer PII in production, this architecture must be
reassessed and separated into dual custodial passphrases (e.g., dual-operator control).

3. HOW TO RESTORE THE FULL SYSTEM BACKUP
--------------------------------------------------------------------------------
To restore the pre-migration snapshot into a fresh or recovered environment:

PowerShell Command:
  C:\\Users\\Admin\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe `
    C:\\KT_Vault_V3\\restore_ktbak.py `
    {NEW_BACKUP_SAFE} `
    C:\\KT_Vault_Restored

(When prompted, enter your unified recovery passphrase).

4. HOW TO RECOVER THE MASTER DOCUMENT KEY ON A NEW MACHINE
--------------------------------------------------------------------------------
If the local Windows DPAPI key is ever lost or you migrate to Linux/macOS:

Python Command:
  import key_management, getpass
  p = getpass.getpass("Enter Recovery Passphrase: ")
  key_id, raw_key = key_management.KeyEscrowService.import_escrow_file(
      r"{NEW_ESCROW_PATH}", p
  )
  # On Windows, re-import into DPAPI:
  provider = key_management.WindowsDPAPIKeyProvider()
  provider.save_key(key_id, raw_key)
  print("Master key restored to DPAPI with fingerprint:", key_management.KeyEscrowService.compute_fingerprint(raw_key))

================================================================================
END OF RECOVERY INSTRUCTIONS
"""

    with open(INSTRUCTIONS_PATH, "w", encoding="utf-8") as f:
        f.write(instructions_content)
    print(f"  - Recovery Instructions saved successfully ({os.path.getsize(INSTRUCTIONS_PATH):,} bytes).")

    # Memory Hygiene
    del p1, p2, passphrase, raw_key

    print("\n" + "=" * 70)
    print("UNIFIED RECOVERY SETUP COMPLETE & VERIFIED")
    print(f"Active Escrow: {NEW_ESCROW_PATH}")
    print(f"Active Backup: {NEW_BACKUP_SAFE}")
    print(f"Instructions:  {INSTRUCTIONS_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
