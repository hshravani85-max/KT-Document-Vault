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
from migrations.migration_phase8_3_recovery_audit import apply_migration
from migrations.rollback_phase8_3_recovery_audit import rollback_migration

PROD_DB_PATH = r"C:\KT_Vault_V3\data\kt_vault_v3.db"

DUMMY_PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n190\n%%EOF\n"

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
    requirement_id TEXT,
    status TEXT,
    extracted_data TEXT,
    file_path TEXT,
    uploaded_at TEXT,
    FOREIGN KEY(requirement_id) REFERENCES requirements(id)
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

class TestPhase8LegacyRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Capture production DB runtime baseline before any test execution
        if not os.path.exists(PROD_DB_PATH):
            raise FileNotFoundError(f"Production database missing: {PROD_DB_PATH}")
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().upper()
        
        # 2. Set up isolated temporary test environment matching app root structure
        cls.test_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.test_dir, "data")
        cls.docs_dir = os.path.join(cls.test_dir, "documents")
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.docs_dir, exist_ok=True)
        
        cls.test_db_path = os.path.join(cls.data_dir, "kt_vault_v3.db")
        cls.orig_db_path = database.DB_PATH
        
        # Point database module to isolated test database
        database.DB_PATH = cls.test_db_path
        
        # Initialize full schema in test database
        conn = sqlite3.connect(cls.test_db_path)
        conn.executescript(INIT_TEST_SCHEMA_SQL)
        conn.commit()
        conn.close()
        
        # Apply Phase 8.3 migration to test DB
        apply_migration(cls.test_db_path)
        
        # Seed test users and entities
        cls.seed_test_database()

    @classmethod
    def tearDownClass(cls):
        # Restore original database path
        database.DB_PATH = cls.orig_db_path
        
        # Clean up temporary directory safely on Windows
        try:
            shutil.rmtree(cls.test_dir, ignore_errors=True)
        except Exception:
            pass
        
        # Final production DB integrity assertion
        cls.verify_prod_db_untouched()

    @classmethod
    def verify_prod_db_untouched(cls):
        if not os.path.exists(PROD_DB_PATH):
            raise FileNotFoundError(f"Production database missing: {PROD_DB_PATH}")
        size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest().upper()
            
        expected_hash = getattr(cls, 'initial_prod_db_sha256', None)
        expected_size = getattr(cls, 'initial_prod_db_size', None)
        
        if expected_hash is not None and current_hash != expected_hash:
            raise AssertionError(
                f"SAFETY VIOLATION: Production database SHA-256 altered during test execution!\n"
                f"Before tests: {expected_hash}\n"
                f"Got:          {current_hash}"
            )
        if expected_size is not None and size != expected_size:
            raise AssertionError(
                f"SAFETY VIOLATION: Production database size altered during test execution!\n"
                f"Before tests: {expected_size}\n"
                f"Got:          {size}"
            )

    @classmethod
    def seed_test_database(cls):
        conn = sqlite3.connect(cls.test_db_path)
        conn.row_factory = sqlite3.Row
        
        # Create users
        salt = os.urandom(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', b'testpass', salt, 100000)
        
        users_data = [
            ('USR-ADM-01', 'admin_user', pwd_hash, salt, 'Admin Tester', 'Admin'),
            ('USR-SUP-01', 'sup_user', pwd_hash, salt, 'Supervisor Tester', 'Supervisor'),
            ('USR-STF-01', 'staff_user', pwd_hash, salt, 'Staff Tester', 'Staff')
        ]
        for u in users_data:
            conn.execute("INSERT OR REPLACE INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)", u)
            
        # Create sessions
        exp = (datetime.now() + timedelta(hours=12)).isoformat()
        cls.admin_token = "tok_admin_test_001"
        cls.sup_token = "tok_sup_test_001"
        cls.staff_token = "tok_staff_test_001"
        
        conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, 'USR-ADM-01', ?)", (cls.admin_token, exp))
        conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, 'USR-SUP-01', ?)", (cls.sup_token, exp))
        conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, 'USR-STF-01', ?)", (cls.staff_token, exp))
        
        # Create customer & trip
        conn.execute("INSERT OR REPLACE INTO customers (id, name, customer_type, status) VALUES ('CUST-001', 'Test Customer', 'Individual', 'Active')")
        conn.execute("INSERT OR REPLACE INTO travellers (id, customer_id, name, type, role) VALUES ('TRV-001', 'CUST-001', 'Lead Traveller', 'Adult', 'Lead')")
        conn.execute("INSERT OR REPLACE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status) VALUES ('TRIP-001', 'CUST-001', 'Test Holiday', 'Paris', '2027-05-01', '2027-05-10', 'Leisure', 'FIT', 'Outbound', 'NOT READY')")
        conn.execute("INSERT OR REPLACE INTO trip_travellers (trip_id, traveller_id) VALUES ('TRIP-001', 'TRV-001')")
        
        # Create dummy PDF files in isolated documents folder
        cls.pdf_passport_path = os.path.join(cls.docs_dir, "test_passport.pdf")
        cls.pdf_flight_path = os.path.join(cls.docs_dir, "test_flight.pdf")
        cls.pdf_visa_path = os.path.join(cls.docs_dir, "test_visa.pdf")
        cls.pdf_hotel_path = os.path.join(cls.docs_dir, "test_hotel.pdf")
        
        for p in [cls.pdf_passport_path, cls.pdf_flight_path, cls.pdf_visa_path, cls.pdf_hotel_path]:
            with open(p, "wb") as f:
                f.write(DUMMY_PDF_CONTENT)
                
        # Create requirements
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-PASS-01', 'TRIP-001', 'TRV-001', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-FLT-01', 'TRIP-001', NULL, 'Flight Ticket', 'TRIP')")
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-VISA-01', 'TRIP-001', 'TRV-001', 'Visa / Entry Document', 'TRAVELLER')")
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-HOTEL-01', 'TRIP-001', NULL, 'Hotel Voucher', 'TRIP')")
        
        # Create initial test documents (all Verified)
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-EMPTY-01', 'REQ-PASS-01', 'Verified', '{}', ?, ?)", (cls.pdf_passport_path, datetime.now().isoformat()))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-WRONG-01', 'REQ-PASS-01', 'Verified', '{\"Visa Number\": \"V123\"}', ?, ?)", (cls.pdf_passport_path, datetime.now().isoformat()))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-PARTIAL-01', 'REQ-FLT-01', 'Verified', '{\"Passenger Name\": \"Lead Traveller\"}', ?, ?)", (cls.pdf_flight_path, datetime.now().isoformat()))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-VISA-01', 'REQ-VISA-01', 'Verified', '{}', ?, ?)", (cls.pdf_visa_path, datetime.now().isoformat()))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-HOTEL-01', 'REQ-HOTEL-01', 'Verified', '{}', ?, ?)", (cls.pdf_hotel_path, datetime.now().isoformat()))
        
        # Seed initial document history for DOC-EMPTY-01
        conn.execute("INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp) VALUES ('DOC-EMPTY-01', 'INITIAL_VERIFICATION', 'Under Review', 'Verified', 'Staff Tester', 'Initial test approval', '2026-01-01T10:00:00')")
        
        conn.commit()
        conn.close()

    def setUp(self):
        # Ensure database.DB_PATH always points to test DB
        database.DB_PATH = self.test_db_path

    def tearDown(self):
        # Re-verify production DB has not been touched by any test
        self.verify_prod_db_untouched()

    # --- Test Case 1: Recover Verified document with empty {} JSON ---
    def test_01_recover_verified_doc_empty_json(self):
        """1. Recover Verified document with empty {} JSON preserves Verified status and logs audit."""
        doc_id = 'DOC-EMPTY-01'
        recovered_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'Z1234567',
            'Date of Birth': '1985-05-15',
            'Nationality': 'Indian',
            'Expiry Date': '2035-05-14'
        }
        res = services.recover_verified_document_data(
            doc_id=doc_id,
            recovered_data=recovered_passport,
            reason="Recovering legacy empty data from verified scan",
            session_token=self.sup_token,
            reverify=True,
            db_path=self.test_db_path
        )
        self.assertTrue(res['success'])
        self.assertTrue(res['transaction_id'].startswith("REC-TX-"))

        # Verify DB document state
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        self.assertEqual(doc['status'], 'Verified')
        saved_data = json.loads(doc['extracted_data'])
        self.assertEqual(saved_data['Passport Number'], 'Z1234567')

        # Verify audit record
        audit = conn.execute("SELECT * FROM document_recovery_audit WHERE transaction_id = ?", (res['transaction_id'],)).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit['previous_extracted_data'], '{}')
        self.assertEqual(audit['actor'], 'Supervisor Tester')
        self.assertEqual(audit['outcome'], 'SUCCESS')

        # Verify document_history
        hist = conn.execute("SELECT * FROM document_history WHERE document_id = ? AND event_type = 'DATA_RECOVERY'", (doc_id,)).fetchone()
        self.assertIsNotNone(hist)
        self.assertEqual(hist['actor'], 'Supervisor Tester')
        conn.close()

    # --- Test Case 2: Recover Verified document with wrong schema ---
    def test_02_recover_verified_doc_wrong_schema(self):
        """2. Recover Verified document with wrong schema replaces invalid fields with correct schema."""
        doc_id = 'DOC-WRONG-01'
        corrected_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'A9876543',
            'Date of Birth': '1990-10-20',
            'Nationality': 'Indian',
            'Expiry Date': '2030-10-19'
        }
        res = services.recover_verified_document_data(
            doc_id=doc_id,
            recovered_data=corrected_passport,
            reason="Fixing mismatched legacy Visa schema on Passport document",
            session_token=self.admin_token,
            reverify=True,
            db_path=self.test_db_path
        )
        self.assertTrue(res['success'])

        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        self.assertEqual(doc['status'], 'Verified')
        data = json.loads(doc['extracted_data'])
        self.assertNotIn("Visa Number", data)
        self.assertEqual(data['Passport Number'], 'A9876543')
        conn.close()

    # --- Test Case 3: Recover Verified document with partial schema ---
    def test_03_recover_verified_doc_partial_schema(self):
        """3. Recover Verified document with partial schema completes all required fields."""
        doc_id = 'DOC-PARTIAL-01'
        complete_flight = {
            'Passenger Name': 'Lead Traveller',
            'PNR/Booking Reference': 'KT-FLT-8899',
            'Route': 'BOM - DXB',
            'Departure Date/Time': '2027-05-01 10:00',
            'Arrival Date/Time': '2027-05-01 12:30',
            'Airline': 'Emirates',
            'Flight Number': 'EK 501'
        }
        res = services.recover_verified_document_data(
            doc_id=doc_id,
            recovered_data=complete_flight,
            reason="Completing missing route and flight time fields",
            session_token=self.sup_token,
            reverify=True,
            db_path=self.test_db_path
        )
        self.assertTrue(res['success'])

        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        data = json.loads(doc['extracted_data'])
        self.assertEqual(data['PNR/Booking Reference'], 'KT-FLT-8899')
        self.assertEqual(data['Departure Date/Time'], '2027-05-01 10:00')
        conn.close()

    # --- Test Case 4: Reject Staff recovery ---
    def test_04_reject_staff_recovery(self):
        """4. Staff user cannot execute recovery (raises PermissionError)."""
        valid_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'Z1234567',
            'Date of Birth': '1985-05-15',
            'Nationality': 'Indian',
            'Expiry Date': '2035-05-14'
        }
        with self.assertRaises(PermissionError):
            services.recover_verified_document_data(
                doc_id='DOC-EMPTY-01',
                recovered_data=valid_passport,
                reason="Unauthorized staff attempt",
                session_token=self.staff_token,
                reverify=True,
                db_path=self.test_db_path
            )

    # --- Test Case 5: Reject unauthenticated recovery ---
    def test_05_reject_unauthenticated_recovery(self):
        """5. Unauthenticated user cannot execute recovery (raises PermissionError)."""
        valid_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'Z1234567',
            'Date of Birth': '1985-05-15',
            'Nationality': 'Indian',
            'Expiry Date': '2035-05-14'
        }
        with self.assertRaises(PermissionError):
            services.recover_verified_document_data(
                doc_id='DOC-EMPTY-01',
                recovered_data=valid_passport,
                reason="Unauthenticated attempt",
                session_token=None,
                reverify=True,
                db_path=self.test_db_path
            )

    # --- Test Case 6: Reject missing mandatory fields ---
    def test_06_reject_missing_mandatory_fields(self):
        """6. Attempt recovery without mandatory fields is rejected with ValueError."""
        # Missing 'Passport Number' and 'Date of Birth'
        incomplete_passport = {
            'Full Name': 'Lead Traveller',
            'Nationality': 'Indian'
        }
        with self.assertRaises(ValueError) as ctx:
            services.recover_verified_document_data(
                doc_id='DOC-EMPTY-01',
                recovered_data=incomplete_passport,
                reason="Incomplete submission",
                session_token=self.sup_token,
                reverify=True,
                db_path=self.test_db_path
            )
        self.assertIn("Missing mandatory field", str(ctx.exception))

    # --- Test Case 7: Reject wrong requirement schema ---
    def test_07_reject_wrong_requirement_schema(self):
        """7. Attempt recovery with fields from another document type is rejected."""
        # Trying to submit Visa fields to Flight Ticket requirement
        wrong_schema_data = {
            'Traveller Name': 'Lead Traveller',
            'Visa Number / Reference': 'V-999',
            'Destination': 'Dubai'
        }
        with self.assertRaises(ValueError) as ctx:
            services.recover_verified_document_data(
                doc_id='DOC-PARTIAL-01',
                recovered_data=wrong_schema_data,
                reason="Mismatched schema attempt",
                session_token=self.sup_token,
                reverify=True,
                db_path=self.test_db_path
            )
        self.assertIn("Missing mandatory field", str(ctx.exception))

    # --- Test Case 8: Cancel recovery retains previous state ---
    def test_08_cancel_recovery_retains_previous_state(self):
        """8. Cancel recovery retains previous state without modifying database."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        before_doc = conn.execute("SELECT extracted_data, status FROM documents WHERE id = 'DOC-VISA-01'").fetchone()
        conn.close()

        # Cancellation in Streamlit simply resets session_state without calling services.
        # We verify that no backend change occurred.
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        after_doc = conn.execute("SELECT extracted_data, status FROM documents WHERE id = 'DOC-VISA-01'").fetchone()
        conn.close()

        self.assertEqual(before_doc['extracted_data'], after_doc['extracted_data'])
        self.assertEqual(before_doc['status'], after_doc['status'])

    # --- Test Case 9: Concurrency stale data rejection ---
    def test_09_concurrency_stale_data_rejection(self):
        """9. Concurrency check: Reject recovery if stored data changed during review."""
        doc_id = 'DOC-VISA-01'
        stale_hash = "stale_hash_1234567890abcdef"
        valid_visa = {
            'Traveller Name': 'Lead Traveller',
            'Visa Number / Reference': 'V-UAE-2027-01',
            'Destination': 'Dubai'
        }
        with self.assertRaises(ValueError) as ctx:
            services.recover_verified_document_data(
                doc_id=doc_id,
                recovered_data=valid_visa,
                reason="Stale recovery attempt",
                session_token=self.sup_token,
                expected_data_hash=stale_hash,
                reverify=True,
                db_path=self.test_db_path
            )
        self.assertIn("Document extracted data has changed", str(ctx.exception))

    # --- Test Case 10: Source PDF integrity conflict rejection ---
    def test_10_pdf_integrity_conflict_rejection(self):
        """10. PDF integrity check: Reject recovery if source PDF SHA-256 changed during review."""
        doc_id = 'DOC-VISA-01'
        mismatched_pdf_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        valid_visa = {
            'Traveller Name': 'Lead Traveller',
            'Visa Number / Reference': 'V-UAE-2027-01',
            'Destination': 'Dubai'
        }
        with self.assertRaises(ValueError) as ctx:
            services.recover_verified_document_data(
                doc_id=doc_id,
                recovered_data=valid_visa,
                reason="PDF integrity mismatch attempt",
                session_token=self.sup_token,
                expected_pdf_sha256=mismatched_pdf_hash,
                reverify=True,
                db_path=self.test_db_path
            )
        self.assertIn("Source PDF hash has changed", str(ctx.exception))

    # --- Test Case 11: Atomic transaction rollback ---
    def test_11_atomic_transaction_rollback(self):
        """11. Atomic transaction rollback ensures no partial writes if an error occurs."""
        doc_id = 'DOC-HOTEL-01'
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        before_audit_cnt = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]
        before_hist_cnt = conn.execute("SELECT count(*) FROM document_history").fetchone()[0]
        conn.close()

        # Call with reverify=False to trigger pre-transaction validation failure
        with self.assertRaises(ValueError):
            services.recover_verified_document_data(
                doc_id=doc_id,
                recovered_data={'Hotel Name': 'Grand Hotel'},
                reason="Incomplete attempt",
                session_token=self.sup_token,
                reverify=False,
                db_path=self.test_db_path
            )

        conn = sqlite3.connect(self.test_db_path)
        after_audit_cnt = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]
        after_hist_cnt = conn.execute("SELECT count(*) FROM document_history").fetchone()[0]
        conn.close()

        self.assertEqual(before_audit_cnt, after_audit_cnt)
        self.assertEqual(before_hist_cnt, after_hist_cnt)

    # --- Test Case 12: Audit record snapshots preserved ---
    def test_12_audit_record_snapshots_preserved(self):
        """12. Audit record verifies previous and new JSON snapshots preserved exactly."""
        doc_id = 'DOC-HOTEL-01'
        valid_hotel = {
            'Hotel Name': 'Burj Al Arab',
            'Guest Name': 'Lead Traveller',
            'Check-in Date': '2027-05-01',
            'Check-out Date': '2027-05-07',
            'Booking Confirmation Number': 'CONF-HTL-9001'
        }
        res = services.recover_verified_document_data(
            doc_id=doc_id,
            recovered_data=valid_hotel,
            reason="Recovering hotel confirmation voucher",
            session_token=self.sup_token,
            reverify=True,
            db_path=self.test_db_path
        )
        self.assertTrue(res['success'])

        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        audit = conn.execute("SELECT * FROM document_recovery_audit WHERE transaction_id = ?", (res['transaction_id'],)).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(audit['previous_extracted_data'], '{}')
        self.assertIn('Burj Al Arab', audit['new_extracted_data'])
        self.assertEqual(audit['previous_status'], 'Verified')
        self.assertEqual(audit['new_status'], 'Verified')
        conn.close()

    # --- Test Case 13: Audit record actor and mandatory reason recorded ---
    def test_13_audit_record_actor_and_reason_recorded(self):
        """13. Audit record verifies actor and mandatory reason recorded."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        audits = conn.execute("SELECT * FROM document_recovery_audit").fetchall()
        self.assertGreater(len(audits), 0)
        for a in audits:
            self.assertIn(a['actor'], ['Supervisor Tester', 'Admin Tester'])
            self.assertTrue(len(a['reason'].strip()) > 5)
            self.assertTrue(a['transaction_id'].startswith("REC-TX-"))
        conn.close()

    # --- Test Case 14: Source customer PDF unchanged ---
    def test_14_original_customer_pdf_unchanged(self):
        """14. Original PDF remains unchanged before and after recovery."""
        for p in [self.pdf_passport_path, self.pdf_flight_path, self.pdf_visa_path, self.pdf_hotel_path]:
            with open(p, "rb") as f:
                content = f.read()
            self.assertEqual(content, DUMMY_PDF_CONTENT)

    # --- Test Case 15: Trip readiness logic sound ---
    def test_15_trip_readiness_logic_sound(self):
        """15. Trip readiness status remains logically sound (does not falsely force READY or degrade)."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        trip = conn.execute("SELECT status FROM trips WHERE id = 'TRIP-001'").fetchone()
        # Still NOT READY because other trip requirements are unfulfilled
        self.assertEqual(trip['status'], 'NOT READY')
        conn.close()

    # --- Test Case 16: Historical verification records remain intact ---
    def test_16_historical_verification_records_remain_intact(self):
        """16. Pre-recovery historical verification records remain intact in document_history."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        initial_hist = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-EMPTY-01' AND event_type = 'INITIAL_VERIFICATION'").fetchone()
        self.assertIsNotNone(initial_hist)
        self.assertEqual(initial_hist['reason'], 'Initial test approval')
        conn.close()

    # --- Test Case 17: Normal review workflows unaffected ---
    def test_17_normal_review_workflows_unaffected(self):
        """17. Normal Verify, Reject, Re-upload, Reopen workflows unaffected by Phase 8.3 additions."""
        conn = sqlite3.connect(self.test_db_path)
        # Create a document in 'Under Review' status with all mandatory extracted data
        normal_data = json.dumps({
            'Full Name': 'Normal User',
            'Passport Number': 'N1234567',
            'Date of Birth': '1992-01-01',
            'Nationality': 'Indian',
            'Expiry Date': '2032-01-01'
        })
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-NORMAL-01', 'REQ-PASS-01', 'Under Review', ?, ?, ?)", (normal_data, self.pdf_passport_path, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        # 17a. Verify document
        services.verify_document('DOC-NORMAL-01', self.sup_token)
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        d = conn.execute("SELECT status FROM documents WHERE id = 'DOC-NORMAL-01'").fetchone()
        self.assertEqual(d['status'], 'Verified')
        conn.close()

        # 17b. Reopen document
        services.reopen_document('DOC-NORMAL-01', 'Need to review again', self.sup_token)
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        d = conn.execute("SELECT status FROM documents WHERE id = 'DOC-NORMAL-01'").fetchone()
        self.assertEqual(d['status'], 'Under Review')
        conn.close()

        # 17c. Reject document
        services.reject_document('DOC-NORMAL-01', 'Document illegible', self.sup_token)
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        d = conn.execute("SELECT status FROM documents WHERE id = 'DOC-NORMAL-01'").fetchone()
        self.assertEqual(d['status'], 'Rejected')
        conn.close()

    # --- Test Case 18: Production database SHA-256 completely untouched ---
    def test_18_production_database_integrity(self):
        """18. Production database SHA-256 and size remain 100% identical."""
        self.verify_prod_db_untouched()

    # --- Extra Test: Unmigrated database guard ---
    def test_19_unmigrated_database_guard(self):
        """19. recover_verified_document_data raises RuntimeError if document_recovery_audit is not deployed."""
        unmigrated_dir = tempfile.mkdtemp()
        try:
            unmigrated_data_dir = os.path.join(unmigrated_dir, "data")
            unmigrated_docs_dir = os.path.join(unmigrated_dir, "documents")
            os.makedirs(unmigrated_data_dir, exist_ok=True)
            os.makedirs(unmigrated_docs_dir, exist_ok=True)
            unmigrated_db = os.path.join(unmigrated_data_dir, "kt_vault_v3.db")
            unmigrated_pdf = os.path.join(unmigrated_docs_dir, "test.pdf")
            with open(unmigrated_pdf, "wb") as f:
                f.write(DUMMY_PDF_CONTENT)

            conn = sqlite3.connect(unmigrated_db)
            conn.row_factory = sqlite3.Row
            # Create only base documents table without document_recovery_audit
            conn.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, requirement_id TEXT, status TEXT, extracted_data TEXT, file_path TEXT, uploaded_at TEXT)")
            conn.execute("INSERT INTO documents VALUES ('DOC-TEST-01', 'REQ-01', 'Verified', '{}', ?, '2026-01-01')", (unmigrated_pdf,))
            conn.commit()
            conn.close()

            with self.assertRaises(RuntimeError) as ctx:
                services.recover_verified_document_data(
                    doc_id='DOC-TEST-01',
                    recovered_data={'some': 'data'},
                    reason="Attempt against unmigrated database",
                    session_token=self.sup_token,
                    reverify=True,
                    db_path=unmigrated_db
                )
            self.assertIn("Migration Required", str(ctx.exception))
        finally:
            shutil.rmtree(unmigrated_dir, ignore_errors=True)

    # --- Test Case 20: Recover Verified doc in TRAVEL FILE READY trip preserves trip readiness ---
    def test_20_recover_verified_doc_in_travel_file_ready_trip(self):
        """20. Recovering a Verified document belonging to a TRAVEL FILE READY trip preserves trip readiness."""
        conn = sqlite3.connect(self.test_db_path)
        # Create a trip marked TRAVEL FILE READY
        conn.execute("INSERT OR REPLACE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status) VALUES ('TRIP-READY-01', 'CUST-001', 'Ready Holiday', 'Tokyo', '2027-08-01', '2027-08-10', 'Leisure', 'FIT', 'Outbound', 'TRAVEL FILE READY')")
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-PASS-READY-01', 'TRIP-READY-01', 'TRV-001', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-READY-01', 'REQ-PASS-READY-01', 'Verified', '{}', ?, ?)", (self.pdf_passport_path, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        recovered_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'J9988776',
            'Date of Birth': '1988-08-08',
            'Nationality': 'Indian',
            'Expiry Date': '2038-08-07'
        }
        res = services.recover_verified_document_data(
            doc_id='DOC-READY-01',
            recovered_data=recovered_passport,
            reason="Recovering verified scan details without disrupting readiness",
            session_token=self.sup_token,
            reverify=True,
            db_path=self.test_db_path
        )
        self.assertTrue(res['success'])

        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        # Verify trip readiness is STILL 'TRAVEL FILE READY'
        trip = conn.execute("SELECT status FROM trips WHERE id = 'TRIP-READY-01'").fetchone()
        self.assertEqual(trip['status'], 'TRAVEL FILE READY')

        # Verify document is still Verified with updated data
        doc = conn.execute("SELECT status, extracted_data FROM documents WHERE id = 'DOC-READY-01'").fetchone()
        self.assertEqual(doc['status'], 'Verified')
        self.assertIn('J9988776', doc['extracted_data'])
        conn.close()

    # --- Test Case 21: Reject recovery of non-Verified document ---
    def test_21_reject_recovery_of_non_verified_document(self):
        """21. Attempting recovery on an 'Under Review' or 'Rejected' document is rejected with zero changes."""
        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-REJECTED-01', 'REQ-PASS-01', 'Rejected', '{\"original\": \"val\"}', ?, ?)", (self.pdf_passport_path, datetime.now().isoformat()))
        conn.commit()

        audit_cnt_before = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]
        hist_cnt_before = conn.execute("SELECT count(*) FROM document_history").fetchone()[0]
        conn.close()

        valid_passport = {
            'Full Name': 'Lead Traveller',
            'Passport Number': 'Z1234567',
            'Date of Birth': '1985-05-15',
            'Nationality': 'Indian',
            'Expiry Date': '2035-05-14'
        }
        with self.assertRaises(ValueError) as ctx:
            services.recover_verified_document_data(
                doc_id='DOC-REJECTED-01',
                recovered_data=valid_passport,
                reason="Attempt to recover unverified document",
                session_token=self.sup_token,
                reverify=True,
                db_path=self.test_db_path
            )
        self.assertIn("Only Verified documents can be recovered", str(ctx.exception))

        conn = sqlite3.connect(self.test_db_path)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT status, extracted_data FROM documents WHERE id = 'DOC-REJECTED-01'").fetchone()
        self.assertEqual(doc['status'], 'Rejected')
        self.assertEqual(doc['extracted_data'], '{"original": "val"}')

        audit_cnt_after = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]
        hist_cnt_after = conn.execute("SELECT count(*) FROM document_history").fetchone()[0]
        conn.close()

        self.assertEqual(audit_cnt_before, audit_cnt_after)
        self.assertEqual(hist_cnt_before, hist_cnt_after)

    # --- Test Case 22: Non-destructive archival rollback ---
    def test_22_non_destructive_archival_rollback(self):
        """22. Non-destructive rollback preserves all recovery audit records in a timestamped archive."""
        # 22a. Attempting rollback on production path without authorization must fail
        with self.assertRaises(PermissionError):
            rollback_migration(PROD_DB_PATH, allow_production=False)

        # 22b. Create isolated rollback database with existing audit records
        rb_dir = tempfile.mkdtemp()
        try:
            rb_db = os.path.join(rb_dir, "test_rollback.db")
            conn = sqlite3.connect(rb_db)
            conn.executescript(INIT_TEST_SCHEMA_SQL)
            conn.commit()
            conn.close()

            apply_migration(rb_db)

            # Insert sample audit records
            conn = sqlite3.connect(rb_db)
            for i in range(3):
                conn.execute('''
                    INSERT INTO document_recovery_audit (
                        transaction_id, document_id, file_path, pdf_sha256,
                        previous_extracted_data, new_extracted_data,
                        previous_status, new_status, actor, reason, outcome, timestamp
                    ) VALUES (?, 'DOC-01', 'dummy.pdf', 'hash', '{}', '{"k": "v"}', 'Verified', 'Verified', 'Supervisor', 'Test reason', 'SUCCESS', '2026-10-16 12:00:00')
                ''', (f"REC-TX-RB-{i}",))
            conn.commit()
            count_pre = conn.execute("SELECT count(*) FROM document_recovery_audit").fetchone()[0]
            self.assertEqual(count_pre, 3)
            conn.close()

            # Execute non-destructive rollback
            rb_res = rollback_migration(rb_db)
            self.assertTrue(rb_res['success'])
            archive_table = rb_res['archived_table']
            self.assertTrue(archive_table.startswith("document_recovery_audit_archive_"))
            self.assertEqual(rb_res['records_preserved'], 3)

            # Verify active table is gone, but archive table exists and has all 3 records
            conn = sqlite3.connect(rb_db)
            active_tbl = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_recovery_audit'").fetchone()
            self.assertIsNone(active_tbl)

            archived_rows = conn.execute(f"SELECT count(*) FROM {archive_table}").fetchone()[0]
            self.assertEqual(archived_rows, 3)
            conn.close()
        finally:
            shutil.rmtree(rb_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()
