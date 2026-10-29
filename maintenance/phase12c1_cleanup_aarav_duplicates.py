"""
Khanna Travels Vault V3 - Phase 12C-1
Authorized Surgical Cleanup of Aarav Demo Duplicate Test Records

Authorized Deletion Scope:
1. documents: DOC-5ee2c21a (broken duplicate passport record)
2. requirements: REQ-TRV-bc9763 (duplicate requirement)
3. travellers: KT-TR-0005 (duplicate traveller)

Preserved Records:
- customers: KT-C-0004 (AARAV DEMO)
- travellers: KT-TR-0004 (AARAV DEMO)
- requirements: REQ-TRV-c7232a (Passport, TRAVELLER_VAULT)
- documents: DOC-c966f3e1 (documents/intake_6921d331b6d4451888796cd3bab3e6b5.pdf)
"""

import sqlite3
import os
import hashlib
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

AUDIT_MARKER = "Administrative cleanup (Phase 12C-1)"
AUDIT_DESCRIPTION = (
    "Administrative cleanup (Phase 12C-1): removed duplicate traveller KT-TR-0005, "
    "duplicate requirement REQ-TRV-bc9763, and broken document DOC-5ee2c21a for customer KT-C-0004. "
    "Preserved legitimate traveller KT-TR-0004 and document DOC-c966f3e1."
)


def run_cleanup():
    print("=== KT VAULT V3 - PHASE 12C-1 AUTHORIZED SURGICAL CLEANUP ===")
    print(f"Target Database: {DB_PATH}")
    assert os.path.exists(DB_PATH), f"Database not found: {DB_PATH}"

    # Connect with timeout and foreign keys enabled
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    # 1. Idempotency Check: Was cleanup already completed?
    already_audit = cur.execute(
        "SELECT id, description, timestamp FROM activity WHERE customer_id = 'KT-C-0004' AND description LIKE ?",
        (f"%{AUDIT_MARKER}%",)
    ).fetchone()

    trav5_exists = cur.execute("SELECT id FROM travellers WHERE id = 'KT-TR-0005'").fetchone()
    req_bc_exists = cur.execute("SELECT id FROM requirements WHERE id = 'REQ-TRV-bc9763'").fetchone()
    doc_5e_exists = cur.execute("SELECT id FROM documents WHERE id = 'DOC-5ee2c21a'").fetchone()

    if already_audit and not trav5_exists and not req_bc_exists and not doc_5e_exists:
        print("\nSTATUS: CLEANUP ALREADY COMPLETED")
        print(f"Audit Log ID: {already_audit[0]} | Timestamp: {already_audit[2]}")
        print("Target records KT-TR-0005, REQ-TRV-bc9763, DOC-5ee2c21a do not exist.")
        conn.close()
        return "CLEANUP ALREADY COMPLETED"

    # If in partial state without audit entry or with unexpected state, verify preconditions
    print("\n--- Pre-Execution Verification ---")
    assert trav5_exists, "Precondition failed: KT-TR-0005 does not exist!"
    assert req_bc_exists, "Precondition failed: REQ-TRV-bc9763 does not exist!"
    assert doc_5e_exists, "Precondition failed: DOC-5ee2c21a does not exist!"

    # Validate relationships of target records
    t5_row = cur.execute("SELECT customer_id FROM travellers WHERE id = 'KT-TR-0005'").fetchone()
    assert t5_row and t5_row[0] == "KT-C-0004", f"Security violation: KT-TR-0005 customer is {t5_row}, not KT-C-0004!"

    r_row = cur.execute("SELECT traveller_id FROM requirements WHERE id = 'REQ-TRV-bc9763'").fetchone()
    assert r_row and r_row[0] == "KT-TR-0005", f"Security violation: REQ-TRV-bc9763 traveller is {r_row}, not KT-TR-0005!"

    d_row = cur.execute("SELECT requirement_id, file_path FROM documents WHERE id = 'DOC-5ee2c21a'").fetchone()
    assert d_row and d_row[0] == "REQ-TRV-bc9763", f"Security violation: DOC-5ee2c21a requirement is {d_row}, not REQ-TRV-bc9763!"
    broken_file = d_row[1]
    broken_abs = os.path.join(PROJECT_ROOT, broken_file) if not os.path.isabs(broken_file) else broken_file
    assert not os.path.exists(broken_abs), f"Unexpected state: file for DOC-5ee2c21a exists on disk: {broken_abs}"

    # Validate preserved records are present
    cust4 = cur.execute("SELECT id, status FROM customers WHERE id = 'KT-C-0004'").fetchone()
    trav4 = cur.execute("SELECT id FROM travellers WHERE id = 'KT-TR-0004' AND customer_id = 'KT-C-0004'").fetchone()
    req_c7 = cur.execute("SELECT id FROM requirements WHERE id = 'REQ-TRV-c7232a' AND traveller_id = 'KT-TR-0004'").fetchone()
    doc_c9 = cur.execute("SELECT id, file_path FROM documents WHERE id = 'DOC-c966f3e1' AND requirement_id = 'REQ-TRV-c7232a'").fetchone()

    assert cust4 and cust4[1] == "Active", "Precondition failed: Customer KT-C-0004 missing or inactive!"
    assert trav4, "Precondition failed: Preserved traveller KT-TR-0004 missing!"
    assert req_c7, "Precondition failed: Preserved requirement REQ-TRV-c7232a missing!"
    assert doc_c9, "Precondition failed: Preserved document DOC-c966f3e1 missing!"

    legit_file = doc_c9[1]
    legit_abs = os.path.join(PROJECT_ROOT, legit_file) if not os.path.isabs(legit_file) else legit_file
    assert os.path.exists(legit_abs), f"Precondition failed: Legitimate passport file missing on disk: {legit_abs}"
    assert os.path.getsize(legit_abs) == 137141, f"Precondition failed: Legitimate passport size mismatch ({os.path.getsize(legit_abs)})"

    # Dependency check: verify no foreign keys from other tables reference the target IDs
    tt_check = cur.execute("SELECT count(*) FROM trip_travellers WHERE traveller_id = 'KT-TR-0005'").fetchone()[0]
    assert tt_check == 0, "Dependency violation: KT-TR-0005 is referenced in trip_travellers!"

    dh_check = cur.execute("SELECT count(*) FROM document_history WHERE document_id = 'DOC-5ee2c21a'").fetchone()[0]
    assert dh_check == 0, "Dependency violation: DOC-5ee2c21a is referenced in document_history!"

    print("Pre-execution validation: ALL PRECONDITIONS PASSED [OK]")

    # 2. Execute Transaction
    print("\n--- Executing Surgical Deletion Transaction ---")
    conn.execute("BEGIN IMMEDIATE;")
    try:
        # Step 1: Delete broken document DOC-5ee2c21a
        cur.execute("DELETE FROM documents WHERE id = 'DOC-5ee2c21a';")
        doc_deleted = cur.rowcount
        print(f"1. Deleted from documents WHERE id = 'DOC-5ee2c21a' (rows affected: {doc_deleted})")
        assert doc_deleted == 1, f"Expected 1 deleted document row, got {doc_deleted}"

        # Step 2: Delete duplicate requirement REQ-TRV-bc9763
        cur.execute("DELETE FROM requirements WHERE id = 'REQ-TRV-bc9763';")
        req_deleted = cur.rowcount
        print(f"2. Deleted from requirements WHERE id = 'REQ-TRV-bc9763' (rows affected: {req_deleted})")
        assert req_deleted == 1, f"Expected 1 deleted requirement row, got {req_deleted}"

        # Step 3: Delete duplicate traveller KT-TR-0005
        cur.execute("DELETE FROM travellers WHERE id = 'KT-TR-0005';")
        trav_deleted = cur.rowcount
        print(f"3. Deleted from travellers WHERE id = 'KT-TR-0005' (rows affected: {trav_deleted})")
        assert trav_deleted == 1, f"Expected 1 deleted traveller row, got {trav_deleted}"

        # Step 4: Insert Administrative Audit Entry
        cur.execute(
            "INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, datetime('now'));",
            ("KT-C-0004", AUDIT_DESCRIPTION)
        )
        audit_inserted = cur.rowcount
        audit_id = cur.lastrowid
        print(f"4. Inserted administrative audit entry (ID: {audit_id}, rows affected: {audit_inserted})")
        assert audit_inserted == 1, f"Expected 1 inserted activity row, got {audit_inserted}"

        # Step 5: In-transaction foreign key verification
        fk_in_tx = cur.execute("PRAGMA foreign_key_check;").fetchall()
        print(f"5. In-transaction PRAGMA foreign_key_check: {fk_in_tx}")
        assert fk_in_tx == [], f"Foreign key violation detected inside transaction: {fk_in_tx}"

        # Step 6: Verify preserved records remain present
        assert cur.execute("SELECT count(*) FROM customers WHERE id = 'KT-C-0004'").fetchone()[0] == 1
        assert cur.execute("SELECT count(*) FROM travellers WHERE id = 'KT-TR-0004'").fetchone()[0] == 1
        assert cur.execute("SELECT count(*) FROM requirements WHERE id = 'REQ-TRV-c7232a'").fetchone()[0] == 1
        assert cur.execute("SELECT count(*) FROM documents WHERE id = 'DOC-c966f3e1'").fetchone()[0] == 1

        # Commit Transaction
        conn.commit()
        print("\nTRANSACTION COMMITTED SUCCESSFULLY [OK]")

    except Exception as ex:
        print(f"\nERROR DURING CLEANUP: {ex}")
        conn.rollback()
        print("TRANSACTION ROLLED BACK [NO CHANGES COMMITTED]")
        conn.close()
        raise ex

    conn.close()

    # 3. Post-Cleanup Fresh Verification
    print("\n--- Post-Cleanup Fresh Connection Verification ---")
    v_conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    v_cur = v_conn.cursor()

    integ = v_cur.execute("PRAGMA integrity_check;").fetchall()
    fk = v_cur.execute("PRAGMA foreign_key_check;").fetchall()
    print(f"PRAGMA integrity_check: {integ}")
    print(f"PRAGMA foreign_key_check: {fk}")
    assert integ == [('ok',)], f"Post-cleanup integrity failed: {integ}"
    assert fk == [], f"Post-cleanup foreign key violations: {fk}"

    # Table counts
    tables = [r[0] for r in v_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    new_counts = {t: v_cur.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    print("\nPost-Cleanup Table Counts:")
    for t in ["customers", "travellers", "requirements", "documents", "trips", "trip_travellers", "activity"]:
        print(f"  {t:20}: {new_counts[t]}")

    v_conn.close()

    # File integrity check
    assert os.path.exists(legit_abs), "Legitimate file missing after cleanup!"
    assert os.path.getsize(legit_abs) == 137141, "Legitimate file size altered after cleanup!"

    return "CLEANUP SUCCESSFUL"


if __name__ == "__main__":
    status = run_cleanup()
    print(f"\nFINAL CLEANUP STATUS: {status}")
