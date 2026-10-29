"""
Phase 8.3 Non-Destructive Rollback: Safe Archival of Document Recovery Audit Table
KT Vault V3

Safely rolls back the Phase 8.3 recovery audit schema WITHOUT deleting any audit records.
Renames document_recovery_audit to a unique timestamped archive table and re-indexes it.
Zero data loss. Zero modification of customer documents or files.
"""

import sqlite3
import os
import re
from datetime import datetime

PROD_DB_CANONICAL = os.path.realpath(r"C:\KT_Vault_V3\data\kt_vault_v3.db")

def rollback_migration(db_path: str, allow_production: bool = False) -> dict:
    """
    Safely archives the document_recovery_audit table to preserve audit history.
    
    Args:
        db_path: Path to SQLite database file.
        allow_production: Explicit bool flag required to run against production database.
        
    Returns:
        dict with success status, archived table name, and record count preserved.
    """
    if not db_path or not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at: {db_path}")

    target_real = os.path.realpath(db_path)
    if target_real.lower() == PROD_DB_CANONICAL.lower() and not allow_production:
        raise PermissionError(
            "SAFETY PROTECTION: Rollback on production database requires explicit authorization. "
            "Pass allow_production=True to authorize execution on production."
        )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Check if table exists
        tbl_check = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_recovery_audit'"
        ).fetchone()
        
        if not tbl_check:
            return {
                "success": False,
                "archived_table": None,
                "records_preserved": 0,
                "message": "Table 'document_recovery_audit' does not exist in target database. Nothing to rollback."
            }

        # Count existing audit records
        rec_count = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]

        # Generate unique non-colliding archive table name
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_archive_name = f"document_recovery_audit_archive_{timestamp_str}"
        archive_name = base_archive_name
        counter = 1

        while conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (archive_name,)).fetchone():
            archive_name = f"{base_archive_name}_{counter}"
            counter += 1

        # Sanitize archive_name for SQL identifier safety
        if not re.match(r'^[a-zA-Z0-9_]+$', archive_name):
            raise ValueError(f"Invalid archive table name generated: '{archive_name}'")

        # Atomic transaction
        conn.execute("BEGIN IMMEDIATE")

        # 1. Rename table to archive
        conn.execute(f"ALTER TABLE document_recovery_audit RENAME TO {archive_name}")

        # 2. Free up original index names while preserving archive indexability
        conn.execute("DROP INDEX IF EXISTS idx_recovery_audit_tx_id")
        conn.execute("DROP INDEX IF EXISTS idx_recovery_audit_doc_id")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{archive_name}_tx ON {archive_name}(transaction_id)")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{archive_name}_doc ON {archive_name}(document_id)")

        # 3. Verify record preservation
        archived_count = conn.execute(f"SELECT count(*) FROM {archive_name}").fetchone()[0]
        if archived_count != rec_count:
            raise RuntimeError(
                f"Data integrity mismatch during archival: expected {rec_count} records, got {archived_count}."
            )

        conn.commit()

        return {
            "success": True,
            "archived_table": archive_name,
            "records_preserved": archived_count,
            "message": f"Successfully archived 'document_recovery_audit' to '{archive_name}'. Preserved {archived_count} audit records."
        }

    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    print("KT Vault V3 - Non-Destructive Rollback Utility")
    print("This script safely archives document_recovery_audit to a timestamped table.")
    print("Direct execution against production is prohibited without explicit authorization.")
