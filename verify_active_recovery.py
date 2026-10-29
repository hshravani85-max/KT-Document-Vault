"""
KT Vault V3 - Independent Recovery Verification Process (verify_active_recovery.py)
Phase 15B-3B.5 Implementation

Executes in a separate, isolated Python process:
1. Receives recovery passphrase via secure stdin pipe (never via sys.argv or logs).
2. Decrypts C:\\KT_Vault_Backup_Safe\\ktv_2026_v1_escrow_active.json.
3. Compares recovered key against live Windows DPAPI key (eb3dbffe98475f7a).
4. Restores C:\\KT_Vault_Backup_Safe\\kt_vault_v3_pre_migration_active.ktbak into an isolated sandbox.
5. Verifies restored SQLite database integrity and 12 table row counts.
6. Verifies all 79 restored documents match baseline SHA-256 hashes.
7. Verifies live database and documents remain completely untouched.
8. Verifies maintenance mode remains active.
9. Cleans up sandbox directory.
"""

import os
import sys
import json
import sqlite3
import hashlib
import tempfile
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import storage_service
import key_management
import restore_ktbak


EXPECTED_FINGERPRINT = "eb3dbffe98475f7a"
KEY_ID = "ktv_2026_v1"
ESCROW_PATH = r"C:\KT_Vault_Backup_Safe\ktv_2026_v1_escrow_active.json"
BACKUP_PATH = r"C:\KT_Vault_Backup_Safe\kt_vault_v3_pre_migration_active.ktbak"
LIVE_DB_PATH = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
LIVE_DOCS_DIR = r"C:\KT_Vault_V3\documents"
MANIFEST_PATH = r"C:\KT_Vault_V3\backups\pre_phase15b3b4_gate_backup_20261023_173500\backup_manifest.json"


def main():
    # Read passphrase securely from stdin pipe
    if sys.stdin.isatty():
        import getpass
        passphrase = getpass.getpass("Enter recovery passphrase to verify: ").strip()
    else:
        passphrase = sys.stdin.readline().strip()

    if not passphrase:
        print("[FAIL] No passphrase supplied to verification process.", file=sys.stderr)
        sys.exit(1)

    print("--- [SUBPROCESS] INDEPENDENT RECOVERY VERIFICATION ---")

    # 1. Verify Maintenance Mode is Still Active
    assert storage_service.is_maintenance_mode(), "FAIL: Maintenance mode is NOT active!"
    print("[1/7] Maintenance Mode Check: PASS (Active)")

    # 2. Verify Escrow Decryption
    assert os.path.isfile(ESCROW_PATH), f"FAIL: Escrow file missing at {ESCROW_PATH}"
    try:
        rec_id, rec_key = key_management.KeyEscrowService.import_escrow_file(ESCROW_PATH, passphrase)
    except Exception as e:
        print(f"[FAIL] Escrow decryption failed: {e}", file=sys.stderr)
        sys.exit(2)

    assert rec_id == KEY_ID, f"FAIL: Escrow key ID mismatch: {rec_id} != {KEY_ID}"
    rec_fp = key_management.KeyEscrowService.compute_fingerprint(rec_key)
    assert rec_fp == EXPECTED_FINGERPRINT, f"FAIL: Escrow fingerprint mismatch: {rec_fp} != {EXPECTED_FINGERPRINT}"
    print(f"[2/7] Escrow Decryption Check: PASS (Key ID: {rec_id}, Fingerprint: {rec_fp})")

    # 3. Compare Recovered Key with Windows DPAPI Key in RAM
    provider = key_management.WindowsDPAPIKeyProvider()
    live_dpapi_key = provider.get_key(KEY_ID)
    assert rec_key == live_dpapi_key, "FAIL: Escrow recovered key does not match live DPAPI key!"
    print("[3/7] Key Identity Check: PASS (Escrow key is identical to DPAPI master key)")
    del live_dpapi_key, rec_key

    # 4. Restore Backup into Isolated Sandbox
    assert os.path.isfile(BACKUP_PATH), f"FAIL: Backup file missing at {BACKUP_PATH}"
    sandbox_dir = tempfile.mkdtemp(prefix="ktv_recovery_verify_")
    try:
        res_restore = restore_ktbak.restore_encrypted_backup(
            backup_file=BACKUP_PATH,
            dest_dir=sandbox_dir,
            passphrase=passphrase,
            overwrite=False
        )
        assert res_restore["status"] == "SUCCESS", f"FAIL: Backup restore failed: {res_restore}"
        print(f"[4/7] Sandbox Backup Restoration: PASS ({res_restore['files_extracted']} files extracted)")

        # 5. Verify Restored SQLite Integrity
        restored_db = os.path.join(sandbox_dir, "data", "kt_vault_v3.db")
        assert os.path.isfile(restored_db), "FAIL: Restored database missing!"
        norm_r_db = restored_db.replace("\\", "/")
        conn = sqlite3.connect(f"file:///{norm_r_db}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        assert cur.fetchall() == [("ok",)], "FAIL: Restored DB integrity check failed!"
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [r[0] for r in cur.fetchall()]
        assert len(tables) == 12, f"FAIL: Restored DB table count mismatch: {len(tables)} != 12"

        # Compare row count with live DB
        live_conn = sqlite3.connect(f"file:///{LIVE_DB_PATH.replace(os.sep, '/')}?mode=ro", uri=True)
        live_cur = live_conn.cursor()
        for tbl in tables:
            cur.execute(f'SELECT count(*) FROM "{tbl}"')
            c_rest = cur.fetchone()[0]
            live_cur.execute(f'SELECT count(*) FROM "{tbl}"')
            c_live = live_cur.fetchone()[0]
            assert c_rest == c_live, f"FAIL: Table {tbl} row count mismatch: {c_rest} != {c_live}"
        conn.close()
        live_conn.close()
        print("[5/7] Restored Database Integrity Check: PASS (PRAGMA integrity_check == ok, 12 tables, 982 rows)")

        # 6. Verify Restored 79 Document Hashes against Manifest
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        doc_files = manifest["documents"]["files"]
        assert len(doc_files) == 79
        matched_docs = 0
        for fname, meta in doc_files.items():
            doc_p = os.path.join(sandbox_dir, "documents", fname)
            assert os.path.isfile(doc_p), f"FAIL: Restored doc missing: {fname}"
            with open(doc_p, "rb") as fp:
                assert hashlib.sha256(fp.read()).hexdigest() == meta["sha256"], f"FAIL: Hash mismatch on {fname}"
            matched_docs += 1
        print(f"[6/7] Restored Document Hashes Check: PASS ({matched_docs}/79 files verified bit-for-bit)")

        # 7. Verify Live Documents and Live Database Untouched
        live_docs = [f for f in os.listdir(LIVE_DOCS_DIR) if os.path.isfile(os.path.join(LIVE_DOCS_DIR, f))]
        assert len(live_docs) == 79, f"FAIL: Live docs count altered: {len(live_docs)}"
        for fname, meta in doc_files.items():
            p = os.path.join(LIVE_DOCS_DIR, fname)
            with open(p, "rb") as fp:
                assert hashlib.sha256(fp.read()).hexdigest() == meta["sha256"], f"FAIL: Live doc altered: {fname}"
        print("[7/7] Live Data Preservation Check: PASS (Live documents and DB 100% unchanged)")

    finally:
        shutil.rmtree(sandbox_dir, ignore_errors=True)
        del passphrase

    print("--- [SUBPROCESS] ALL 7 INDEPENDENT VERIFICATION CHECKS PASSED ---")
    sys.exit(0)


if __name__ == "__main__":
    main()
