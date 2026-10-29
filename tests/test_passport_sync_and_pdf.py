import unittest
import os
import sys
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
import travel_file_generator

PROD_DB_PATH = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
EXPECTED_PROD_SHA256 = ("aad3781fa1628fe5459b050cea8ff76947f47d320d71d1bf244f50c699c8971e", "c71b76035b46c6db338e033d6e1dbdcd753dba47d3028b8cb65c576910934ef7", "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d")
EXPECTED_PROD_SIZE = (143360, 147456, 167936)

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
    passport_number TEXT,
    nationality TEXT,
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
    file_path TEXT,
    status TEXT,
    extracted_data TEXT,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_profile (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT,
    dob TEXT,
    nationality TEXT,
    passport_number TEXT,
    passport_expiry TEXT
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

class TestPassportSyncAndPdf(unittest.TestCase):
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

        # Create users
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

        # Create sessions
        exp = (datetime.now() + timedelta(hours=24)).isoformat()
        cls.staff_token = "token-staff-sync"
        cls.super_token = "token-super-sync"
        cls.admin_token = "token-admin-sync"
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.super_token, "U-SUPER", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN", exp))

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

    def setUp(self):
        # Clean data tables between individual tests
        conn = database.get_connection()
        for tbl in ['activity', 'document_history', 'documents', 'requirements', 'trip_travellers', 'trips', 'travellers', 'customers', 'user_profile']:
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
        conn.close()

    def _create_sample_pdf(self, filename="sample.pdf"):
        p = os.path.join(self.docs_dir, filename)
        with open(p, "wb") as f:
            f.write(SAMPLE_MINIMAL_PDF)
        return p

    def _get_pdf_text(self, pdf_path):
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return "".join(page.extract_text() for page in reader.pages)

    def test_01_traveller_passport_null_with_matching_verified_passport(self):
        """1. Traveller passport number NULL with a matching Verified Passport retrieves from doc."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-01', 'Alice', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-01', 'C-01', 'Alice Smith', 'Adult', 'Lead Traveller', NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-01', 'C-01', 'Dubai Tour', 'Dubai', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-01', 'TR-01')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P1', 'T-01', 'TR-01', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc1.pdf")
        meta = {"Full Name": "Alice Smith", "Passport Number": "P-SYNTH-12345", "Date of Birth": "10 Jan 1990", "Nationality": "British", "Expiry Date": "10 Jan 2030"}
        conn.execute(
            "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P1', 'REQ-P1', ?, 'Verified', ?)",
            (doc_pdf, json.dumps(meta))
        )
        conn.commit()
        conn.close()

        out_pdf = os.path.join(self.docs_dir, "outfile_01.pdf")
        res_path = travel_file_generator.generate_consolidated_travel_file("T-01", out_pdf, session_token=self.super_token)
        self.assertTrue(os.path.exists(res_path))

        content = self._get_pdf_text(res_path)
        self.assertIn("Alice Smith (Passport: P-SYNTH-12345)", content)
        self.assertNotIn("Passport: N/A", content)

    def test_02_traveller_passport_already_populated_correctly(self):
        """2. Traveller passport number already populated correctly is preserved."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-02', 'Bob', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-02', 'C-02', 'Bob Jones', 'Adult', 'Lead Traveller', 'P-EXIST-99999')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-02', 'C-02', 'Paris Trip', 'Paris', '2026-11-01', '2026-11-05', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-02', 'TR-02')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P2', 'T-02', 'TR-02', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc2.pdf")
        meta = {"Full Name": "Bob Jones", "Passport Number": "P-EXIST-99999", "Date of Birth": "05 May 1985", "Nationality": "Canadian", "Expiry Date": "05 May 2032"}
        conn.execute(
            "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P2', 'REQ-P2', ?, 'Verified', ?)",
            (doc_pdf, json.dumps(meta))
        )
        conn.commit()
        conn.close()

        out_pdf = os.path.join(self.docs_dir, "outfile_02.pdf")
        res_path = travel_file_generator.generate_consolidated_travel_file("T-02", out_pdf, session_token=self.super_token)
        content = self._get_pdf_text(res_path)
        self.assertIn("Bob Jones (Passport: P-EXIST-99999)", content)

    def test_03_conflicting_passport_numbers(self):
        """3. Conflicting passport numbers block travel-file generation and verification."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-03', 'Charlie', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-03', 'C-03', 'Charlie Brown', 'Adult', 'Lead Traveller', 'P-PROFILE-111')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-03', 'C-03', 'Tokyo Tour', 'Tokyo', '2026-10-10', '2026-10-20', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-03', 'TR-03')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P3', 'T-03', 'TR-03', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc3.pdf")
        # Document has conflicting number "P-DOC-222"
        meta = {"Full Name": "Charlie Brown", "Passport Number": "P-DOC-222", "Date of Birth": "12 Dec 1992", "Nationality": "American", "Expiry Date": "12 Dec 2031"}
        conn.execute(
            "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P3', 'REQ-P3', ?, 'Under Review', ?)",
            (doc_pdf, json.dumps(meta))
        )
        conn.commit()
        conn.close()

        # Attempting verification must fail with conflict
        with self.assertRaises(ValueError) as ctx:
            services.verify_document("DOC-P3", self.super_token)
        self.assertIn("Synchronization conflict", str(ctx.exception))
        self.assertIn("does not match verified document passport", str(ctx.exception))

        # Even if a document was somehow marked Verified with a different number, generator must block
        conn = database.get_connection()
        conn.execute("UPDATE documents SET status = 'Verified' WHERE id = 'DOC-P3'")
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx2:
            travel_file_generator.generate_consolidated_travel_file("T-03", session_token=self.super_token)
        self.assertIn("Passport conflict", str(ctx2.exception))
        self.assertIn("P-PROFILE-111", str(ctx2.exception))
        self.assertIn("P-DOC-222", str(ctx2.exception))

    def test_04_missing_or_malformed_extracted_data(self):
        """4. Missing or malformed extracted_data handled safely without crashing."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-04', 'David', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-04', 'C-04', 'David Miller', 'Adult', 'Lead Traveller', NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-04', 'C-04', 'Berlin Trip', 'Berlin', '2026-11-10', '2026-11-15', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-04', 'TR-04')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P4', 'T-04', 'TR-04', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc4.pdf")
        # Malformed JSON
        conn.execute(
            "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P4', 'REQ-P4', ?, 'Verified', ?)",
            (doc_pdf, "{not valid json at all")
        )
        conn.commit()
        conn.close()

        out_pdf = os.path.join(self.docs_dir, "outfile_04.pdf")
        res_path = travel_file_generator.generate_consolidated_travel_file("T-04", out_pdf, session_token=self.super_token)
        content = self._get_pdf_text(res_path)
        self.assertIn("David Miller (Passport: N/A)", content)

    def test_05_unverified_passport_document_not_used(self):
        """5. Unverified Passport documents (Under Review, Rejected, etc.) are never used by generator."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-05', 'Eva', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-05', 'C-05', 'Eva Green', 'Adult', 'Lead Traveller', NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-05', 'C-05', 'Rome Holiday', 'Rome', '2026-10-15', '2026-10-22', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-05', 'TR-05')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P5', 'T-05', 'TR-05', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc5.pdf")
        meta = {"Full Name": "Eva Green", "Passport Number": "P-UNVERIFIED-777", "Date of Birth": "01 Jan 1995", "Nationality": "Italian", "Expiry Date": "01 Jan 2035"}
        for st in ['Under Review', 'Rejected', 'Needs Review']:
            conn.execute("DELETE FROM documents WHERE id = 'DOC-P5'")
            conn.execute(
                "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P5', 'REQ-P5', ?, ?, ?)",
                (doc_pdf, st, json.dumps(meta))
            )
            conn.commit()

            out_pdf = os.path.join(self.docs_dir, f"outfile_05_{st}.pdf")
            res_path = travel_file_generator.generate_consolidated_travel_file("T-05", out_pdf, session_token=self.super_token)
            content = self._get_pdf_text(res_path)
            self.assertIn("Eva Green (Passport: N/A)", content)
            self.assertNotIn("P-UNVERIFIED-777", content)
        conn.close()

    def test_06_multiple_travellers_under_same_customer(self):
        """6. Multiple travellers under same customer are matched without cross-contamination."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-06', 'Family Customer', 'FAMILY', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-06A', 'C-06', 'Parent One', 'Adult', 'Lead Traveller', NULL)")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-06B', 'C-06', 'Child One', 'Child', 'Standard', NULL)")

        # Customer-level user_profile has a passport number that must NEVER be used as a fallback
        conn.execute(
            "INSERT INTO user_profile (customer_id, full_name, dob, nationality, passport_number, passport_expiry) "
            "VALUES ('C-06', 'Parent One', '01 Jan 1980', 'Indian', 'P-CUST-PROFILE-NEVER-USE', '01 Jan 2030')"
        )

        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-06', 'C-06', 'Family Trip', 'Dubai', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-06', 'TR-06A')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-06', 'TR-06B')")

        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-06A', 'T-06', 'TR-06A', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-06B', 'T-06', 'TR-06B', 'Passport', 'TRAVELLER')")

        doc_pdfA = self._create_sample_pdf("doc6A.pdf")
        doc_pdfB = self._create_sample_pdf("doc6B.pdf")

        metaA = {"Full Name": "Parent One", "Passport Number": "PASS-PARENT-A", "Date of Birth": "01 Jan 1980", "Nationality": "Indian", "Expiry Date": "01 Jan 2030"}
        metaB = {"Full Name": "Child One", "Passport Number": "PASS-CHILD-B", "Date of Birth": "10 Jun 2012", "Nationality": "Indian", "Expiry Date": "10 Jun 2027"}

        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-06A', 'REQ-06A', ?, 'Verified', ?)", (doc_pdfA, json.dumps(metaA)))
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-06B', 'REQ-06B', ?, 'Verified', ?)", (doc_pdfB, json.dumps(metaB)))
        conn.commit()
        conn.close()

        out_pdf = os.path.join(self.docs_dir, "outfile_06.pdf")
        res_path = travel_file_generator.generate_consolidated_travel_file("T-06", out_pdf, session_token=self.super_token)
        content = self._get_pdf_text(res_path)

        self.assertIn("Parent One (Passport: PASS-PARENT-A)", content)
        self.assertIn("Child One (Passport: PASS-CHILD-B)", content)
        self.assertNotIn("P-CUST-PROFILE-NEVER-USE", content)

    def test_07_multiple_trips_for_same_traveller(self):
        """7. Multiple trips for the same traveller resolve that specific trip's document."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-07', 'Frequent Flyer', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-07', 'C-07', 'George King', 'Adult', 'Lead Traveller', NULL)")

        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-07A', 'C-07', 'Trip Summer', 'Dubai', '2026-06-01', '2026-06-10', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-07B', 'C-07', 'Trip Winter', 'Dubai', '2026-12-01', '2026-12-10', 'TRAVEL FILE READY')")

        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-07A', 'TR-07')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-07B', 'TR-07')")

        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-07A', 'T-07A', 'TR-07', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-07B', 'T-07B', 'TR-07', 'Passport', 'TRAVELLER')")

        doc_pdfA = self._create_sample_pdf("doc7A.pdf")
        doc_pdfB = self._create_sample_pdf("doc7B.pdf")

        metaA = {"Full Name": "George King", "Passport Number": "P-RENEWED-2026", "Date of Birth": "20 Aug 1988", "Nationality": "Australian", "Expiry Date": "20 Aug 2036"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-07A', 'REQ-07A', ?, 'Verified', ?)", (doc_pdfA, json.dumps(metaA)))
        # Trip B has no verified passport yet
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-07B', 'REQ-07B', ?, 'Under Review', ?)", (doc_pdfB, json.dumps(metaA)))
        conn.commit()
        conn.close()

        # Trip A resolves to P-RENEWED-2026
        out_A = travel_file_generator.generate_consolidated_travel_file("T-07A", out_path=os.path.join(self.docs_dir, "TravelFile_T-07A.pdf"), session_token=self.super_token)
        cA = self._get_pdf_text(out_A)
        self.assertIn("George King (Passport: P-RENEWED-2026)", cA)

        # Trip B has no Verified doc on Trip B, so it strictly outputs N/A (no cross-trip leakage)
        out_B = travel_file_generator.generate_consolidated_travel_file("T-07B", out_path=os.path.join(self.docs_dir, "TravelFile_T-07B.pdf"), session_token=self.super_token)
        cB = self._get_pdf_text(out_B)
        self.assertIn("George King (Passport: N/A)", cB)

    def test_08_passport_verification_synchronization(self):
        """8. Passport verification synchronizes passport number, nationality, and DOB to traveller."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-08', 'Hannah', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, dob, nationality, passport_number) VALUES ('TR-08', 'C-08', 'Hannah Abbott', 'Adult', 'Lead Traveller', NULL, NULL, NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-08', 'C-08', 'London Tour', 'London', '2026-11-01', '2026-11-10', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-08', 'TR-08')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-08', 'T-08', 'TR-08', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc8.pdf")
        meta = {"Full Name": "Hannah Abbott", "Passport Number": "GB-987654", "Date of Birth": "14 Feb 1994", "Nationality": "British", "Expiry Date": "14 Feb 2034"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-08', 'REQ-08', ?, 'Under Review', ?)", (doc_pdf, json.dumps(meta)))
        conn.commit()
        conn.close()

        # Before verification: traveller profile fields are None
        conn = database.get_connection()
        t_before = conn.execute("SELECT * FROM travellers WHERE id = 'TR-08'").fetchone()
        conn.close()
        self.assertIsNone(t_before['passport_number'])
        self.assertIsNone(t_before['nationality'])
        self.assertIsNone(t_before['dob'])

        # Verify document as Supervisor
        services.verify_document("DOC-08", self.super_token)

        # After verification: traveller profile fields are synchronized
        conn = database.get_connection()
        t_after = conn.execute("SELECT * FROM travellers WHERE id = 'TR-08'").fetchone()
        d_after = conn.execute("SELECT status FROM documents WHERE id = 'DOC-08'").fetchone()
        act = conn.execute("SELECT description FROM activity WHERE trip_id = 'T-08' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertEqual(d_after['status'], 'Verified')
        self.assertEqual(t_after['passport_number'], 'GB-987654')
        self.assertEqual(t_after['nationality'], 'British')
        self.assertEqual(t_after['dob'], '14 Feb 1994')
        self.assertIn("profile synchronized from verified Passport", act['description'])

    def test_09_dob_normalization_and_invalid_dob_handling(self):
        """9. Date of Birth normalization and invalid DOB handling in verification."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-09', 'Ian', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, dob) VALUES ('TR-09A', 'C-09', 'Ian Malcolm', 'Adult', 'Lead Traveller', '1990-05-20')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, dob) VALUES ('TR-09B', 'C-09', 'Ian Junior', 'Child', 'Standard', NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-09', 'C-09', 'Safari', 'Kenya', '2026-11-01', '2026-11-10', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-09', 'TR-09A')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-09', 'TR-09B')")

        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-09A', 'T-09', 'TR-09A', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-09B', 'T-09', 'TR-09B', 'Passport', 'TRAVELLER')")

        doc_pdfA = self._create_sample_pdf("doc9A.pdf")
        doc_pdfB = self._create_sample_pdf("doc9B.pdf")

        # TR-09A has ISO format "1990-05-20" in profile, doc has "20 May 1990" (identical calendar date)
        metaA = {"Full Name": "Ian Malcolm", "Passport Number": "P-IAN-01", "Date of Birth": "20 May 1990", "Nationality": "Kenyan", "Expiry Date": "20 May 2030"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-09A', 'REQ-09A', ?, 'Under Review', ?)", (doc_pdfA, json.dumps(metaA)))

        # TR-09B doc has completely invalid unparseable DOB
        metaB = {"Full Name": "Ian Junior", "Passport Number": "P-IAN-02", "Date of Birth": "invalid-dob-string", "Nationality": "Kenyan", "Expiry Date": "20 May 2030"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-09B', 'REQ-09B', ?, 'Under Review', ?)", (doc_pdfB, json.dumps(metaB)))
        conn.commit()
        conn.close()

        # Doc A verifies successfully and normalizes DOB to "20 May 1990"
        services.verify_document("DOC-09A", self.super_token)
        conn = database.get_connection()
        tA = conn.execute("SELECT dob, passport_number FROM travellers WHERE id = 'TR-09A'").fetchone()
        conn.close()
        self.assertEqual(tA['passport_number'], 'P-IAN-01')
        self.assertEqual(tA['dob'], '20 May 1990')

        # Doc B verification fails due to invalid DOB format
        with self.assertRaises(ValueError) as ctx:
            services.verify_document("DOC-09B", self.super_token)
        self.assertIn("Invalid Date of Birth format", str(ctx.exception))

    def test_10_atomic_rollback_when_synchronization_fails(self):
        """10. Atomic rollback when synchronization fails (database remains completely unchanged)."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-10', 'Jack', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number, nationality) VALUES ('TR-10', 'C-10', 'Jack Bauer', 'Adult', 'Lead Traveller', 'P-JACK-ORIGINAL', 'American')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-10', 'C-10', 'Mission', 'DC', '2026-11-01', '2026-11-10', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-10', 'TR-10')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-10', 'T-10', 'TR-10', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc10.pdf")
        # Conflicting nationality
        meta = {"Full Name": "Jack Bauer", "Passport Number": "P-JACK-ORIGINAL", "Date of Birth": "01 Jan 1970", "Nationality": "Russian", "Expiry Date": "01 Jan 2030"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-10', 'REQ-10', ?, 'Under Review', ?)", (doc_pdf, json.dumps(meta)))
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError):
            services.verify_document("DOC-10", self.super_token)

        # Verify rollback: document status is STILL 'Under Review', traveller still 'American'
        conn = database.get_connection()
        doc = conn.execute("SELECT status FROM documents WHERE id = 'DOC-10'").fetchone()
        trav = conn.execute("SELECT nationality FROM travellers WHERE id = 'TR-10'").fetchone()
        hist = conn.execute("SELECT COUNT(*) FROM document_history WHERE document_id = 'DOC-10'").fetchone()[0]
        conn.close()

        self.assertEqual(doc['status'], 'Under Review')
        self.assertEqual(trav['nationality'], 'American')
        self.assertEqual(hist, 0)

    def test_11_role_permissions_and_audit_behavior(self):
        """11. Staff cannot verify documents; Supervisor/Admin logs complete audit record."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-11', 'Kate', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role) VALUES ('TR-11', 'C-11', 'Kate Austen', 'Adult', 'Lead Traveller')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-11', 'C-11', 'Island Tour', 'Fiji', '2026-11-01', '2026-11-10', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-11', 'TR-11')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-11', 'T-11', 'TR-11', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("doc11.pdf")
        meta = {"Full Name": "Kate Austen", "Passport Number": "P-KATE-11", "Date of Birth": "18 Aug 1985", "Nationality": "Canadian", "Expiry Date": "18 Aug 2035"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-11', 'REQ-11', ?, 'Under Review', ?)", (doc_pdf, json.dumps(meta)))
        conn.commit()
        conn.close()

        # Staff rejected
        with self.assertRaises(PermissionError):
            services.verify_document("DOC-11", self.staff_token)

        # Supervisor succeeds
        services.verify_document("DOC-11", self.super_token)

        conn = database.get_connection()
        hist = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-11'").fetchone()
        conn.close()
        self.assertEqual(hist['actor'], 'Senior Supervisor')
        self.assertEqual(hist['new_status'], 'Verified')

    def test_12_non_passport_verification_behavior_unchanged(self):
        """12. Non-Passport documents verify normally without altering traveller records."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-12', 'Leo', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-12', 'C-12', 'Leo Fitz', 'Adult', 'Lead Traveller', 'P-EXISTING')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-12', 'C-12', 'Flight Trip', 'Paris', '2026-11-01', '2026-11-10', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-12', 'TR-12')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-12', 'T-12', 'TR-12', 'Flight Ticket', 'TRIP')")

        doc_pdf = self._create_sample_pdf("doc12.pdf")
        flt_meta = {
            "Passenger Name": "Leo Fitz", "PNR/Booking Reference": "PNR1234", "Route": "LON-PAR",
            "Departure Date/Time": "01 Nov 2026", "Arrival Date/Time": "10 Nov 2026"
        }
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-12', 'REQ-12', ?, 'Under Review', ?)", (doc_pdf, json.dumps(flt_meta)))
        conn.commit()
        conn.close()

        services.verify_document("DOC-12", self.admin_token)

        conn = database.get_connection()
        d = conn.execute("SELECT status FROM documents WHERE id = 'DOC-12'").fetchone()
        t = conn.execute("SELECT passport_number FROM travellers WHERE id = 'TR-12'").fetchone()
        conn.close()

        self.assertEqual(d['status'], 'Verified')
        self.assertEqual(t['passport_number'], 'P-EXISTING')

    def test_13_production_database_untouched(self):
        """13. Verify production database remains completely untouched during test run."""
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
