"""
Phase 8.3 Migration: Dedicated Document Recovery Audit Table
KT Vault V3

IMPORTANT:
This script prepares the dedicated structured recovery audit mechanism.
DO NOT EXECUTE AUTOMATICALLY AGAINST PRODUCTION.
Explicit deployment authorization is required.
"""

import sqlite3
import os
import sys

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_recovery_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    pdf_sha256 TEXT NOT NULL,
    previous_extracted_data TEXT NOT NULL,
    new_extracted_data TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    outcome TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_recovery_audit_doc_id ON document_recovery_audit(document_id);
CREATE INDEX IF NOT EXISTS idx_recovery_audit_tx_id ON document_recovery_audit(transaction_id);
"""

def apply_migration(db_path: str) -> bool:
    """Applies the recovery audit schema to the specified database."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at: {db_path}")
        
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        return True
    finally:
        conn.close()

if __name__ == '__main__':
    print("This migration script must not be auto-executed directly against production.")
    print("Use test suites or explicit supervisor migration commands.")
