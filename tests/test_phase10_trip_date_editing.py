import unittest
import os
import sys
import io
import json
import sqlite3
import hashlib
import tempfile
import shutil
from datetime import datetime, timedelta

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import database
import services
import auth_services

PROD_DB_PATH = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
PHASE10_BASELINE_SHA256 = ("aad3781fa1628fe5459b050cea8ff76947f47d320d71d1bf244f50c699c8971e", "c71b76035b46c6db338e033d6e1dbdcd753dba47d3028b8cb65c576910934ef7", "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d")
PHASE10_BASELINE_SIZE = (143360, 147456, 167936)

SAMPLE_MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Length 120 >>\nstream\n"
    b"BT /F1 12 Tf 72 712 Td (Date: 12 Dec 2026 to 18 Dec 2026 Flight EK501 Hotel Atlantis Dubai) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \n0000000206 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n378\n%%EOF\n"
)

INIT_TEST_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT,
    customer_type TEXT,
    status TEXT,
    mobile TEXT,
    email TEXT
);
CREATE TABLE IF NOT EXISTS travellers (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    name TEXT,
    type TEXT,
    role TEXT,
    dob TEXT,
    relationship TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);
CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    customer_id TEXT,
    name TEXT,
    destination TEXT,
    start_date TEXT,
    end_date TEXT,
    trip_type TEXT,
    service TEXT,
    department TEXT,
    status TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);
CREATE TABLE IF NOT EXISTS trip_travellers (
    trip_id TEXT,
    traveller_id TEXT,
    PRIMARY KEY(trip_id, traveller_id),
    FOREIGN KEY(trip_id) REFERENCES trips(id),
    FOREIGN KEY(traveller_id) REFERENCES travellers(id)
);
CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    trip_id TEXT,
    traveller_id TEXT,
    name TEXT,
    type TEXT,
    UNIQUE(trip_id, traveller_id, name)
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    trip_id TEXT,
    traveller_id TEXT,
    requirement_id TEXT,
    file_path TEXT,
    original_filename TEXT,
    doc_type TEXT,
    status TEXT,
    extracted_data TEXT,
    confidence REAL,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    verified_at DATETIME,
    verified_by TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT,
    customer_id TEXT,
    description TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT,
    event_type TEXT,
    previous_status TEXT,
    new_status TEXT,
    actor TEXT,
    reason TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash BLOB,
    salt BLOB,
    full_name TEXT,
    role TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

class TestPhase10TripDateEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Verify production DB baseline
        if not os.path.exists(PROD_DB_PATH):
            raise FileNotFoundError(f"Production database missing: {PROD_DB_PATH}")
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        
        # 2. Setup isolated temporary directory and test database
        cls.test_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.test_dir, "data")
        cls.docs_dir = os.path.join(cls.test_dir, "documents")
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.docs_dir, exist_ok=True)
        
        cls.test_db_path = os.path.join(cls.data_dir, "kt_vault_v3.db")
        cls.orig_db_path = database.DB_PATH
        database.DB_PATH = cls.test_db_path
        
        # Initialize schema
        conn = sqlite3.connect(cls.test_db_path)
        conn.executescript(INIT_TEST_SCHEMA_SQL)
        
        # Create users for all three roles
        users_data = [
            ("U-STAFF", "staff1", "Staff User", "Staff"),
            ("U-SUPER", "super1", "Senior Supervisor", "Supervisor"),
            ("U-ADMIN", "admin1", "System Administrator", "Admin"),
        ]
        for uid, uname, fname, role in users_data:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, uname, b"fakehash", b"fakesalt", fname, role)
            )
            
        # Create valid sessions (expires in 24 hours)
        exp = (datetime.now() + timedelta(hours=24)).isoformat()
        cls.staff_token = "token-staff-001"
        cls.super_token = "token-super-001"
        cls.admin_token = "token-admin-001"
        
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.super_token, "U-SUPER", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN", exp))
        
        # Create sample sample customer and base trips
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-001', 'Test Customer', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type) VALUES ('TR-001', 'C-001', 'Test Traveller', 'ADULT')")
        
        # Standard trip for testing
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-TEST-01', 'C-001', 'Paris Holiday', 'Paris', '2026-10-01', '2026-10-10', 'HOLIDAY', 'DRAFT')"
        )
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-TEST-01', 'TR-001')")
        
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        
        # Verify production DB remained untouched
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        if curr_sha256 != cls.initial_prod_db_sha256 or curr_size != cls.initial_prod_db_size:
            raise RuntimeError("CRITICAL: Production database was modified during testing!")

    def test_01_staff_cannot_edit_trip_dates(self):
        """1. Staff role must be rejected with PermissionError when attempting date edits."""
        with self.assertRaises(PermissionError) as ctx:
            services.update_trip_dates(
                trip_id="T-TEST-01",
                new_start_date="2026-10-02",
                new_end_date="2026-10-11",
                session_token=self.staff_token,
                reason="Staff attempting date correction"
            )
        self.assertIn("Requires one of", str(ctx.exception))

    def test_02_supervisor_can_submit_valid_correction(self):
        """2. Supervisor can successfully update trip dates with valid reason."""
        result = services.update_trip_dates(
            trip_id="T-TEST-01",
            new_start_date="2026-10-02",
            new_end_date="2026-10-12",
            session_token=self.super_token,
            reason="Flight schedule revised by airline",
            expected_current_start_date="2026-10-01",
            expected_current_end_date="2026-10-10"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["new_dates"], ("2026-10-02", "2026-10-12"))
        self.assertEqual(result["actor"], "Senior Supervisor")
        
        # Verify in DB
        conn = database.get_connection()
        t = conn.execute("SELECT start_date, end_date FROM trips WHERE id='T-TEST-01'").fetchone()
        conn.close()
        self.assertEqual(t["start_date"], "2026-10-02")
        self.assertEqual(t["end_date"], "2026-10-12")

    def test_03_admin_can_submit_valid_correction(self):
        """3. Admin can successfully update trip dates."""
        result = services.update_trip_dates(
            trip_id="T-TEST-01",
            new_start_date="2026-10-03",
            new_end_date="2026-10-13",
            session_token=self.admin_token,
            reason="Admin schedule alignment with supplier voucher",
            expected_current_start_date="2026-10-02",
            expected_current_end_date="2026-10-12"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["new_dates"], ("2026-10-03", "2026-10-13"))

    def test_04_missing_or_short_reason_rejected(self):
        """4. Missing, whitespace-only, or < 5 characters reason must be rejected."""
        invalid_reasons = [None, "", "   ", "fix", "done"]
        for r in invalid_reasons:
            with self.subTest(reason=r):
                with self.assertRaises(ValueError) as ctx:
                    services.update_trip_dates(
                        trip_id="T-TEST-01",
                        new_start_date="2026-10-03",
                        new_end_date="2026-10-14",
                        session_token=self.super_token,
                        reason=r
                    )
                self.assertIn("reason is mandatory", str(ctx.exception).lower())

    def test_05_inverted_dates_rejected(self):
        """5. Inverted date range (end < start) must be rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            services.update_trip_dates(
                trip_id="T-TEST-01",
                new_start_date="2026-10-20",
                new_end_date="2026-10-10",
                session_token=self.super_token,
                reason="Attempting inverted dates"
            )
        self.assertIn("cannot be earlier", str(ctx.exception).lower())

    def test_06_nonexistent_trip_rejected(self):
        """6. Nonexistent trip ID is rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            services.update_trip_dates(
                trip_id="T-DOES-NOT-EXIST",
                new_start_date="2026-10-01",
                new_end_date="2026-10-10",
                session_token=self.super_token,
                reason="Attempting non-existent trip"
            )
        self.assertIn("Trip not found", str(ctx.exception))

    def test_07_concurrent_stale_edit_protection(self):
        """7. Concurrent or stale edits are rejected when expected dates do not match stored dates."""
        with self.assertRaises(ValueError) as ctx:
            services.update_trip_dates(
                trip_id="T-TEST-01",
                new_start_date="2026-10-05",
                new_end_date="2026-10-15",
                session_token=self.super_token,
                reason="Stale view update",
                expected_current_start_date="2020-01-01", # wrong expected start date
                expected_current_end_date="2026-10-13"
            )
        self.assertIn("Concurrent edit conflict", str(ctx.exception))

    def test_08_conflicting_verified_documents_prevent_edit(self):
        """8. Conflicting Verified documents prevent the edit with detailed error messages."""
        # Create a trip with a Verified Hotel Voucher
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-CONFLICT', 'C-001', 'Conflict Trip', 'Dubai', '2026-12-12', '2026-12-18', 'HOLIDAY', 'DRAFT')"
        )
        conn.execute("INSERT INTO requirements (id, trip_id, name, type) VALUES ('REQ-HOTEL', 'T-CONFLICT', 'Hotel Voucher', 'TRIP')")
        
        # Hotel voucher check-in 12 Dec 2026, check-out 18 Dec 2026
        hotel_meta = {
            "Hotel Name": "Atlantis The Palm",
            "Check-in Date": "12 Dec 2026",
            "Check-out Date": "18 Dec 2026"
        }
        test_pdf = os.path.join(self.docs_dir, "test_hotel.pdf")
        with open(test_pdf, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
            
        conn.execute(
            "INSERT INTO documents (id, trip_id, requirement_id, file_path, original_filename, doc_type, status, extracted_data) "
            "VALUES ('DOC-HOTEL', 'T-CONFLICT', 'REQ-HOTEL', ?, 'test_hotel.pdf', 'Hotel Voucher', 'Verified', ?)",
            (test_pdf, json.dumps(hotel_meta))
        )
        conn.commit()
        conn.close()
        
        # Attempt edit that truncates trip before hotel check-out (new end 17 Dec vs hotel check-out 18 Dec)
        with self.assertRaises(ValueError) as ctx:
            services.update_trip_dates(
                trip_id="T-CONFLICT",
                new_start_date="2026-12-12",
                new_end_date="2026-12-17",
                session_token=self.super_token,
                reason="Shorten trip by one day"
            )
        self.assertIn("Hotel Voucher", str(ctx.exception))
        self.assertIn("after proposed trip end date", str(ctx.exception))

    def test_09_missing_or_corrupt_verified_document_dates_handled_conservatively(self):
        """9. Missing or unparseable document dates in Verified documents are flagged as conflicts."""
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-CORRUPT', 'C-001', 'Corrupt Trip', 'Dubai', '2026-12-12', '2026-12-18', 'HOLIDAY', 'DRAFT')"
        )
        conn.execute("INSERT INTO requirements (id, trip_id, name, type) VALUES ('REQ-FLT', 'T-CORRUPT', 'Flight Ticket', 'TRIP')")
        # Empty dates in verified flight ticket
        bad_meta = {"Airline": "Emirates"}
        test_pdf = os.path.join(self.docs_dir, "test_corrupt.pdf")
        with open(test_pdf, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
            
        conn.execute(
            "INSERT INTO documents (id, trip_id, requirement_id, file_path, original_filename, doc_type, status, extracted_data) "
            "VALUES ('DOC-FLT', 'T-CORRUPT', 'REQ-FLT', ?, 'test_corrupt.pdf', 'Flight Ticket', 'Verified', ?)",
            (test_pdf, json.dumps(bad_meta))
        )
        conn.commit()
        conn.close()
        
        eval_res = services.validate_trip_date_consistency("T-CORRUPT", "2026-12-12", "2026-12-18")
        self.assertFalse(eval_res["compatible"])
        self.assertTrue(any("missing departure/return flight dates" in c for c in eval_res["conflicts"]))

    def test_10_compatible_corrections_preserve_verified_status(self):
        """10. Compatible date corrections preserve all Verified document statuses."""
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-COMPAT', 'C-001', 'Compatible Trip', 'Dubai', '2026-12-10', '2026-12-20', 'HOLIDAY', 'DRAFT')"
        )
        conn.execute("INSERT INTO requirements (id, trip_id, name, type) VALUES ('REQ-V1', 'T-COMPAT', 'Hotel Voucher', 'TRIP')")
        hotel_meta = {"Check-in Date": "12 Dec 2026", "Check-out Date": "18 Dec 2026"}
        test_pdf = os.path.join(self.docs_dir, "test_compat.pdf")
        with open(test_pdf, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
        conn.execute(
            "INSERT INTO documents (id, trip_id, requirement_id, file_path, original_filename, doc_type, status, extracted_data) "
            "VALUES ('DOC-V1', 'T-COMPAT', 'REQ-V1', ?, 'test_compat.pdf', 'Hotel Voucher', 'Verified', ?)",
            (test_pdf, json.dumps(hotel_meta))
        )
        conn.commit()
        conn.close()
        
        # New dates: 2026-12-12 to 2026-12-18 (exactly envelopes hotel)
        res = services.update_trip_dates(
            trip_id="T-COMPAT",
            new_start_date="2026-12-12",
            new_end_date="2026-12-18",
            session_token=self.super_token,
            reason="Aligned trip dates with hotel voucher booking"
        )
        self.assertTrue(res["success"])
        
        # Verify document status remains 'Verified'
        conn = database.get_connection()
        doc = conn.execute("SELECT status FROM documents WHERE id='DOC-V1'").fetchone()
        conn.close()
        self.assertEqual(doc["status"], "Verified")

    def test_11_audit_logging_completeness(self):
        """11. Successful updates create a complete activity log entry."""
        res = services.update_trip_dates(
            trip_id="T-TEST-01",
            new_start_date="2026-10-04",
            new_end_date="2026-10-14",
            session_token=self.super_token,
            reason="Supervisor adjusted itinerary after client call"
        )
        self.assertTrue(res["success"])
        
        conn = database.get_connection()
        act = conn.execute("SELECT * FROM activity WHERE trip_id='T-TEST-01' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIsNotNone(act)
        desc = act["description"]
        self.assertIn("Trip dates updated from 2026-10-03 - 2026-10-13 to 2026-10-04 - 2026-10-14", desc)
        self.assertIn("Senior Supervisor", desc)
        self.assertIn("Supervisor adjusted itinerary after client call", desc)

    def test_12_failed_updates_leave_database_unchanged(self):
        """12. Failed updates roll back cleanly and leave database unchanged."""
        conn = database.get_connection()
        orig = conn.execute("SELECT start_date, end_date FROM trips WHERE id='T-CONFLICT'").fetchone()
        orig_start, orig_end = orig["start_date"], orig["end_date"]
        conn.close()
        
        with self.assertRaises(ValueError):
            services.update_trip_dates(
                trip_id="T-CONFLICT",
                new_start_date="2026-12-15", # Conflict! Hotel check-in is 12 Dec
                new_end_date="2026-12-18",
                session_token=self.super_token,
                reason="Invalid date shift"
            )
            
        conn = database.get_connection()
        curr = conn.execute("SELECT start_date, end_date FROM trips WHERE id='T-CONFLICT'").fetchone()
        conn.close()
        self.assertEqual(curr["start_date"], orig_start)
        self.assertEqual(curr["end_date"], orig_end)

    def test_13_finalized_trip_cannot_be_edited(self):
        """13. Trips in 'TRAVEL FILE READY' status cannot be edited."""
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-FINAL', 'C-001', 'Finalized Trip', 'Paris', '2026-10-01', '2026-10-10', 'HOLIDAY', 'TRAVEL FILE READY')"
        )
        conn.commit()
        conn.close()
        
        with self.assertRaises(ValueError) as ctx:
            services.update_trip_dates(
                trip_id="T-FINAL",
                new_start_date="2026-10-02",
                new_end_date="2026-10-11",
                session_token=self.admin_token,
                reason="Attempting to edit finalized file"
            )
        self.assertIn("Cannot modify finalized travel file", str(ctx.exception))

    def test_14_final_approval_blocks_date_conflicts(self):
        """14. Final approval blocks trips with date conflicts and succeeds after correction (Rohan scenario)."""
        # Set up a trip mirroring Rohan's exact synthetic case:
        # Trip dates: 2026-12-11 to 2026-12-18 (stored date typo: 11 Dec)
        # All documents verified for 12 Dec 2026 to 18 Dec 2026
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, status) "
            "VALUES ('T-ROHAN-MOCK', 'C-001', 'Rohan Dubai Demo Holiday Mock', 'Dubai', '2026-12-11', '2026-12-18', 'HOLIDAY', 'DRAFT')"
        )
        conn.execute("INSERT INTO requirements (id, trip_id, name, type) VALUES ('R-INS', 'T-ROHAN-MOCK', 'Travel Insurance', 'TRIP')")
        test_pdf = os.path.join(self.docs_dir, "test_rohan.pdf")
        with open(test_pdf, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
            
        ins_meta = {"Valid From": "12 Dec 2026", "Valid Until": "18 Dec 2026"}
        conn.execute(
            "INSERT INTO documents (id, trip_id, requirement_id, file_path, original_filename, doc_type, status, extracted_data) "
            "VALUES ('D-INS', 'T-ROHAN-MOCK', 'R-INS', ?, 'test_rohan.pdf', 'Travel Insurance', 'Verified', ?)",
            (test_pdf, json.dumps(ins_meta))
        )
        conn.commit()
        conn.close()
        
        # Verify 100% readiness
        _, comp, att, miss, pct, b_status = services.calculate_readiness("T-ROHAN-MOCK")
        self.assertEqual(pct, 100)
        self.assertEqual(b_status, "READY FOR FINAL REVIEW")
        
        # Final approval MUST FAIL because trip starts on 11 Dec, but Insurance starts on 12 Dec
        with self.assertRaises(ValueError) as ctx:
            services.approve_travel_file("T-ROHAN-MOCK", self.super_token)
        self.assertIn("Approval blocked: Material trip-date conflicts detected", str(ctx.exception))
        self.assertIn("leaving traveller uninsured", str(ctx.exception))
        
        # Now Supervisor corrects the date from 2026-12-11 to 2026-12-12
        fix_res = services.update_trip_dates(
            trip_id="T-ROHAN-MOCK",
            new_start_date="2026-12-12",
            new_end_date="2026-12-18",
            session_token=self.super_token,
            reason="Corrected calendar selection typo from 11 Dec to 12 Dec to align with vouchers",
            expected_current_start_date="2026-12-11",
            expected_current_end_date="2026-12-18"
        )
        self.assertTrue(fix_res["success"])
        
        # Now final approval MUST SUCCEED
        appr_res = services.approve_travel_file("T-ROHAN-MOCK", self.super_token)
        self.assertTrue(appr_res["success"])
        self.assertEqual(appr_res["status"], "TRAVEL FILE READY")
        
        # Verify DB status
        conn = database.get_connection()
        t = conn.execute("SELECT status FROM trips WHERE id='T-ROHAN-MOCK'").fetchone()
        conn.close()
        self.assertEqual(t["status"], "TRAVEL FILE READY")

    def test_15_readiness_and_workflows_remain_operational(self):
        """15. Existing readiness calculation and trip retrieval remain fully functional."""
        details = services.get_trip_details("T-TEST-01")
        self.assertIsNotNone(details)
        self.assertEqual(details["id"], "T-TEST-01")
        
        total, comp, att, miss, pct, b_status = services.calculate_readiness("T-TEST-01")
        self.assertIsInstance(pct, int)
        self.assertIn(b_status, ["NOT READY", "READY FOR FINAL REVIEW", "TRAVEL FILE READY"])

    def test_16_metadata_pdf_text_discrepancy_detection(self):
        """16. verify_metadata_pdf_date_agreement detects discrepancies between metadata and PDF text."""
        # PDF has "12 Dec 2026"
        pdf_path = os.path.join(self.docs_dir, "test_agreement.pdf")
        with open(pdf_path, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
            
        d_valid = services.parse_flexible_date("12 Dec 2026")
        agrees, msg = services.verify_metadata_pdf_date_agreement(pdf_path, d_valid, "12 Dec 2026")
        self.assertTrue(agrees)
        
        d_phantom = services.parse_flexible_date("25 Dec 2026")
        agrees2, msg2 = services.verify_metadata_pdf_date_agreement(pdf_path, d_phantom, "25 Dec 2026")
        self.assertFalse(agrees2)
        self.assertIn("does not appear in source PDF text", msg2)

    def test_17_production_database_untouched(self):
        """17. Verify production database remains completely untouched during test run."""
        self.assertTrue(os.path.exists(PROD_DB_PATH))
        self.assertEqual(os.path.getsize(PROD_DB_PATH), self.initial_prod_db_size, "Production DB size changed during test run!")
        with open(PROD_DB_PATH, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(h, self.initial_prod_db_sha256, "Production DB SHA-256 changed during test run!")
        conn = sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()


if __name__ == '__main__':
    unittest.main()
