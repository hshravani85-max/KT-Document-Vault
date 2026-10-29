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

PROD_DB_PATH = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
PROD_DOCS_DIR = r"C:\KT_Vault_V3\documents"

# Minimal authentic binary headers
SAMPLE_PDF_BYTES = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 12 Tf 72 712 Td (Khanna Travels Vault PDF) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"0000000115 00000 n \n0000000206 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n302\n%%EOF\n"
)
SAMPLE_JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"

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
    nationality TEXT
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
    status TEXT
);
CREATE TABLE IF NOT EXISTS trip_travellers (
    trip_id TEXT,
    traveller_id TEXT,
    PRIMARY KEY(trip_id, traveller_id)
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
    uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT,
    customer_id TEXT,
    description TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_profile (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT,
    dob TEXT,
    nationality TEXT,
    passport_number TEXT,
    passport_expiry TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT,
    password_hash BLOB,
    salt BLOB,
    full_name TEXT,
    role TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT,
    expires_at TEXT
);
"""

class TestPhase11cAdvancedSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Preflight baseline audit of production DB and documents
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()

        cls.initial_doc_files = sorted(os.listdir(PROD_DOCS_DIR))
        cls.initial_doc_count = len(cls.initial_doc_files)
        cls.initial_doc_total_size = sum(os.path.getsize(os.path.join(PROD_DOCS_DIR, f)) for f in cls.initial_doc_files)
        inv_hasher = hashlib.sha256()
        for f in cls.initial_doc_files:
            with open(os.path.join(PROD_DOCS_DIR, f), 'rb') as fp:
                inv_hasher.update(fp.read())
        cls.initial_doc_sig = inv_hasher.hexdigest()

        # 2. Setup isolated temporary directory and test database
        cls.test_dir = tempfile.mkdtemp()
        cls.data_dir = os.path.join(cls.test_dir, "data")
        cls.docs_dir = os.path.join(cls.test_dir, "documents")
        os.makedirs(cls.data_dir, exist_ok=True)
        os.makedirs(cls.docs_dir, exist_ok=True)

        cls.test_db_path = os.path.join(cls.data_dir, "kt_vault_v3.db")
        cls.orig_db_path = database.DB_PATH
        cls.orig_docs_dir = getattr(services, 'DOCUMENTS_DIR', PROD_DOCS_DIR)

        database.DB_PATH = cls.test_db_path
        services.DOCUMENTS_DIR = cls.docs_dir

        # Initialize schema
        conn = sqlite3.connect(cls.test_db_path)
        conn.executescript(INIT_TEST_SCHEMA_SQL)

        # Create users & sessions
        users = [
            ("U-STAFF-11C", "staff_11c", "Junior Staff", "Staff"),
            ("U-SUPER-11C", "super_11c", "Senior Supervisor", "Supervisor"),
            ("U-ADMIN-11C", "admin_11c", "System Administrator", "Admin"),
            ("U-CLIENT-11C", "client_11c", "Customer Client", "Client"),
        ]
        for uid, uname, fname, role in users:
            conn.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                         (uid, uname, b"fake", b"salt", fname, role))

        exp = (datetime.now() + timedelta(hours=24)).isoformat()
        expired = (datetime.now() - timedelta(hours=2)).isoformat()
        cls.staff_token = "token-staff-11c"
        cls.super_token = "token-super-11c"
        cls.admin_token = "token-admin-11c"
        cls.client_token = "token-client-11c"
        cls.expired_token = "token-expired-11c"

        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF-11C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.super_token, "U-SUPER-11C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN-11C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.client_token, "U-CLIENT-11C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.expired_token, "U-SUPER-11C", expired))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        services.DOCUMENTS_DIR = cls.orig_docs_dir
        shutil.rmtree(cls.test_dir, ignore_errors=True)

        # Strict production database immutability check
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()

        assert curr_size == cls.initial_prod_db_size, f"Production DB size changed! {cls.initial_prod_db_size} -> {curr_size}"
        assert curr_sha256 == cls.initial_prod_db_sha256, f"Production DB hash changed! {cls.initial_prod_db_sha256} -> {curr_sha256}"

        # Production document inventory immutability check
        curr_docs = sorted(os.listdir(PROD_DOCS_DIR))
        assert len(curr_docs) == cls.initial_doc_count, "Production doc count changed!"
        curr_total_size = sum(os.path.getsize(os.path.join(PROD_DOCS_DIR, f)) for f in curr_docs)
        assert curr_total_size == cls.initial_doc_total_size, "Production total doc bytes changed!"
        curr_hasher = hashlib.sha256()
        for f in curr_docs:
            with open(os.path.join(PROD_DOCS_DIR, f), 'rb') as fp:
                curr_hasher.update(fp.read())
        assert curr_hasher.hexdigest() == cls.initial_doc_sig, "Production doc signature changed!"

    def setUp(self):
        # Reset test DB data
        conn = sqlite3.connect(self.test_db_path)
        conn.execute("DELETE FROM activity;")
        conn.execute("DELETE FROM documents;")
        conn.execute("DELETE FROM requirements;")
        conn.execute("DELETE FROM trip_travellers;")
        conn.execute("DELETE FROM trips;")
        conn.execute("DELETE FROM travellers;")
        conn.execute("DELETE FROM customers;")
        conn.execute("DELETE FROM user_profile;")
        conn.commit()
        conn.close()

    def _setup_rich_test_data(self):
        """Populates rich multi-customer, multi-traveller, multi-trip test data."""
        # Create test document files on disk
        doc1_path = os.path.join(self.docs_dir, "doc1_amit_pass.pdf")
        doc2_path = os.path.join(self.docs_dir, "doc2_amit_visa.pdf")
        doc3_path = os.path.join(self.docs_dir, "doc3_flight.pdf")
        doc4_path = os.path.join(self.docs_dir, "doc4_amit_sing_pass.pdf")
        doc5_path = os.path.join(self.docs_dir, "doc5_amit_vault_pass.pdf")
        doc6_path = os.path.join(self.docs_dir, "doc6_rohan_pass.pdf")
        doc7_path = os.path.join(self.docs_dir, "doc7_priya_pass.pdf")
        doc8_path = os.path.join(self.docs_dir, "doc8_hotel.jpg")
        doc9_path = os.path.join(self.docs_dir, "doc9_sneha_flight.pdf")

        with open(doc1_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc2_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc3_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc4_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc5_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc6_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc7_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)
        with open(doc8_path, 'wb') as f: f.write(SAMPLE_JPG_BYTES)
        with open(doc9_path, 'wb') as f: f.write(SAMPLE_PDF_BYTES)

        conn = sqlite3.connect(self.test_db_path)
        # Customers
        conn.execute("INSERT INTO customers (id, name, customer_type, status, mobile, email) VALUES ('C-01', 'Amit Mehta', 'Individual', 'Active', '9876543210', 'amit@demo.com')")
        conn.execute("INSERT INTO customers (id, name, customer_type, status, mobile, email) VALUES ('C-02', 'Rohan Sharma', 'Family', 'Active', '9876543211', 'rohan@demo.com')")
        conn.execute("INSERT INTO customers (id, name, customer_type, status, mobile, email) VALUES ('C-03', 'Sneha Patel', 'Corporate', 'Active', '9876543212', 'sneha@demo.com')")

        # Travellers
        # TR-01: Amit Mehta (has passport_number directly in table)
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-01', 'C-01', 'Amit Mehta', 'Adult', 'Lead', 'P9002001-DEMO')")
        # TR-02: Rohan Sharma (passport_number is NULL, stored only in verified doc extracted_data)
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-02', 'C-02', 'Rohan Sharma', 'Adult', 'Lead', NULL)")
        # TR-03: Priya Sharma (has passport_number PRIYA-PASS-9999)
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-03', 'C-02', 'Priya Sharma', 'Adult', 'Spouse', 'PRIYA-PASS-9999')")
        # TR-04: Aarav Sharma (has no passport number, no verified doc)
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-04', 'C-02', 'Aarav Sharma', 'Child', 'Son', NULL)")
        # TR-05: Sneha Patel
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-05', 'C-03', 'Sneha Patel', 'Adult', 'Lead', NULL)")

        # Trips
        # T-01: Dubai Holiday for Amit
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-01', 'C-01', 'Amit Dubai Holiday', 'Dubai, UAE', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')")
        # T-02: Singapore Tour for Amit
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-02', 'C-01', 'Amit Singapore Tour', 'Singapore', '2027-02-10', '2027-02-16', 'Planning')")
        # T-03: Dubai Family Vacation for Sharma Family
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-03', 'C-02', 'Sharma Dubai Family Vacation', 'Dubai, UAE', '2026-12-15', '2026-12-22', 'Under Review')")
        # T-04: London Business for Sneha
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-04', 'C-03', 'Sneha London Business', 'London, UK', '2026-11-01', '2026-11-10', 'Planning')")

        # Trip Travellers
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-01', 'TR-01')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-02', 'TR-01')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-03', 'TR-02')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-03', 'TR-03')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-03', 'TR-04')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-04', 'TR-05')")

        # Customer 2 user_profile (with customer-level passport that MUST NOT be used as fallback for travellers)
        conn.execute("INSERT INTO user_profile (customer_id, full_name, passport_number) VALUES ('C-02', 'Rohan Sharma', 'CUSTOMER-FALLBACK-PASS-888')")

        # Requirements & Documents
        # DOC-01: Amit Passport (T-01)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-01', 'T-01', 'TR-01', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-01', 'R-01', 'Verified', ?, '2026-10-01 10:00:00')", (doc1_path,))

        # DOC-02: Amit Visa (T-01)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-02', 'T-01', 'TR-01', 'Visa / Entry Document', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-02', 'R-02', 'Verified', ?, '2026-10-01 10:05:00')", (doc2_path,))

        # DOC-03: Amit Trip Flight Ticket (T-01)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-03', 'T-01', NULL, 'Flight Ticket', 'TRIP')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-03', 'R-03', 'Verified', ?, '2026-10-01 10:10:00')", (doc3_path,))

        # DOC-04: Amit Singapore Passport (T-02)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-04', 'T-02', 'TR-01', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-04', 'R-04', 'Verified', ?, '2026-10-02 11:00:00')", (doc4_path,))

        # DOC-05: Amit Reusable Vault Passport (trip_id IS NULL)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-05', NULL, 'TR-01', 'Passport', 'TRAVELLER_VAULT')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-05', 'R-05', 'Verified', ?, '2026-10-03 09:00:00')", (doc5_path,))

        # DOC-06: Rohan Passport (T-03) — Verified document with extracted passport number
        rohan_ext = json.dumps({"Passport Number": "DEMO-PASSPORT-0001", "Full Name": "Rohan Sharma"})
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-06', 'T-03', 'TR-02', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-06', 'R-06', 'Verified', ?, ?, '2026-10-04 14:00:00')", (rohan_ext, doc6_path))

        # DOC-07: Priya Passport (T-03) — Verified document
        priya_ext = json.dumps({"Passport Number": "PRIYA-PASS-9999", "Full Name": "Priya Sharma"})
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-07', 'T-03', 'TR-03', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-07', 'R-07', 'Verified', ?, ?, '2026-10-04 14:05:00')", (priya_ext, doc7_path))

        # DOC-08: Sneha Hotel Voucher (T-04) — Under Review (JPG image)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-08', 'T-04', 'TR-05', 'Hotel Voucher', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-08', 'R-08', 'Under Review', ?, '2026-10-05 16:00:00')", (doc8_path,))

        # DOC-09: Sneha Flight Ticket (T-04) — Malformed extracted_data JSON
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('R-09', 'T-04', NULL, 'Flight Ticket', 'TRIP')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-09', 'R-09', 'Verified', '{corrupt_json: true, no_quotes}', ?, '2026-10-05 16:30:00')", (doc9_path,))

        conn.commit()
        conn.close()

    # -------------------------------------------------------------
    # 1. Search customer by full name
    # -------------------------------------------------------------
    def test_01_search_customer_full_name(self):
        """1. Search customer by full name returns matching customer and documents."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Amit Mehta")
        cust_names = [c['name'] for c in res['customers']]
        self.assertIn("Amit Mehta", cust_names)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids)

    # -------------------------------------------------------------
    # 2. Search customer by partial name
    # -------------------------------------------------------------
    def test_02_search_customer_partial_name(self):
        """2. Search customer by partial name matches case-insensitively."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="amit")
        cust_ids = [c['id'] for c in res['customers']]
        self.assertIn("C-01", cust_ids)

    # -------------------------------------------------------------
    # 3. Search customer by customer ID
    # -------------------------------------------------------------
    def test_03_search_customer_by_id(self):
        """3. Search customer by exact customer ID."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="C-02")
        cust_ids = [c['id'] for c in res['customers']]
        self.assertIn("C-02", cust_ids)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-06", doc_ids)

    # -------------------------------------------------------------
    # 4. Search traveller by name
    # -------------------------------------------------------------
    def test_04_search_traveller_by_name(self):
        """4. Search traveller by name."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Priya Sharma")
        trav_names = [t['name'] for t in res['travellers']]
        self.assertIn("Priya Sharma", trav_names)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-07", doc_ids)

    # -------------------------------------------------------------
    # 5. Search traveller by traveller ID
    # -------------------------------------------------------------
    def test_05_search_traveller_by_id(self):
        """5. Search traveller by traveller ID."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="TR-02")
        trav_ids = [t['id'] for t in res['travellers']]
        self.assertIn("TR-02", trav_ids)

    # -------------------------------------------------------------
    # 6. Search trip by trip ID
    # -------------------------------------------------------------
    def test_06_search_trip_by_id(self):
        """6. Search trip by trip ID."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="T-01")
        trip_ids = [t['id'] for t in res['trips']]
        self.assertIn("T-01", trip_ids)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids)
        self.assertIn("DOC-02", doc_ids)

    # -------------------------------------------------------------
    # 7. Search trip by name
    # -------------------------------------------------------------
    def test_07_search_trip_by_name(self):
        """7. Search trip by partial trip name."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Singapore Tour")
        trip_ids = [t['id'] for t in res['trips']]
        self.assertIn("T-02", trip_ids)

    # -------------------------------------------------------------
    # 8. Search destination
    # -------------------------------------------------------------
    def test_08_search_destination(self):
        """8. Search trips and documents by destination."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, destination="Dubai")
        trip_destinations = [t['destination'] for t in res['trips']]
        self.assertTrue(all("Dubai" in d for d in trip_destinations))
        # Documents from T-01 and T-03 should match
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids)
        self.assertIn("DOC-06", doc_ids)
        self.assertNotIn("DOC-08", doc_ids) # London

    # -------------------------------------------------------------
    # 9. Search exact passport number from traveller record
    # -------------------------------------------------------------
    def test_09_search_passport_from_traveller_record(self):
        """9. Search exact passport number stored in travellers.passport_number."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="P9002001-DEMO")
        trav_names = [t['name'] for t in res['travellers']]
        self.assertIn("Amit Mehta", trav_names)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids)
        # Should not return documents for other travellers
        self.assertNotIn("DOC-06", doc_ids)
        self.assertNotIn("DOC-07", doc_ids)

    # -------------------------------------------------------------
    # 10. Search exact passport number from matching Verified Passport extracted_data
    # -------------------------------------------------------------
    def test_10_search_passport_from_verified_extracted_data(self):
        """10. Search exact passport number from Verified Passport extracted_data when traveller record has NULL."""
        self._setup_rich_test_data()
        # Rohan Sharma's passport_number is NULL, but DOC-06 extracted_data has DEMO-PASSPORT-0001
        res = services.advanced_vault_search(self.staff_token, query="DEMO-PASSPORT-0001")
        trav_names = [t['name'] for t in res['travellers']]
        self.assertIn("Rohan Sharma", trav_names)
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-06", doc_ids)

    # -------------------------------------------------------------
    # 11. Reject passport match from another traveller
    # -------------------------------------------------------------
    def test_11_reject_passport_match_from_another_traveller(self):
        """11. Searching Rohan's passport must NOT return Priya's documents on the same trip."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="DEMO-PASSPORT-0001")
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-06", doc_ids) # Rohan's passport
        self.assertNotIn("DOC-07", doc_ids) # Priya's passport must be rejected!
        trav_names = [t['name'] for t in res['travellers']]
        self.assertNotIn("Priya Sharma", trav_names)

    # -------------------------------------------------------------
    # 12. Reject ambiguous customer-level passport fallback
    # -------------------------------------------------------------
    def test_12_reject_ambiguous_customer_level_passport_fallback(self):
        """12. Searching customer-level profile passport must NOT attribute to child/unverified travellers."""
        self._setup_rich_test_data()
        # user_profile has CUSTOMER-FALLBACK-PASS-888 for C-02. Aarav Sharma (TR-04) has NULL.
        res = services.advanced_vault_search(self.staff_token, query="CUSTOMER-FALLBACK-PASS-888")
        # Must return 0 travellers and 0 documents because no traveller record or verified doc has this passport
        self.assertEqual(len(res['travellers']), 0)
        self.assertEqual(len(res['documents']), 0)

    # -------------------------------------------------------------
    # 13. Search by document type
    # -------------------------------------------------------------
    def test_13_search_by_document_type(self):
        """13. Filter documents by requirement document type."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, document_type="Visa / Entry Document")
        doc_names = [d['req_name'] for d in res['documents']]
        self.assertTrue(all("Visa" in n for n in doc_names))
        self.assertIn("DOC-02", [d['doc_id'] for d in res['documents']])

    # -------------------------------------------------------------
    # 14. Search by verification status
    # -------------------------------------------------------------
    def test_14_search_by_verification_status(self):
        """14. Filter documents by verification status."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, verification_status="Under Review")
        statuses = [d['status'] for d in res['documents']]
        self.assertTrue(all(s == "Under Review" for s in statuses))
        self.assertEqual([d['doc_id'] for d in res['documents']], ["DOC-08"])

    # -------------------------------------------------------------
    # 15. Combine document type and status filters
    # -------------------------------------------------------------
    def test_15_combine_document_type_and_status(self):
        """15. Combine document type and status with logical AND."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(
            self.staff_token,
            document_type="Hotel Voucher",
            verification_status="Under Review"
        )
        self.assertEqual(len(res['documents']), 1)
        self.assertEqual(res['documents'][0]['doc_id'], "DOC-08")

    # -------------------------------------------------------------
    # 16. Combine destination, type, and status
    # -------------------------------------------------------------
    def test_16_combine_destination_type_status(self):
        """16. Combine destination, document type, and verification status."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(
            self.staff_token,
            destination="Dubai",
            document_type="Visa",
            verification_status="Verified"
        )
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertEqual(doc_ids, ["DOC-02"])

    # -------------------------------------------------------------
    # 17. Filter by overlapping trip dates
    # -------------------------------------------------------------
    def test_17_filter_by_overlapping_trip_dates(self):
        """17. Filter documents by overlapping trip dates."""
        self._setup_rich_test_data()
        # Trips in December 2026: T-01 (Dec 12-18) and T-03 (Dec 15-22).
        # Querying Dec 01 to Dec 31 should return docs for T-01 and T-03, but not T-02 (Feb 2027) or T-04 (Nov 2026).
        res = services.advanced_vault_search(
            self.staff_token,
            trip_start="2026-12-01",
            trip_end="2026-12-31"
        )
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids) # T-01
        self.assertIn("DOC-06", doc_ids) # T-03
        self.assertNotIn("DOC-04", doc_ids) # T-02 (Feb 2027)
        self.assertNotIn("DOC-08", doc_ids) # T-04 (Nov 2026)

    # -------------------------------------------------------------
    # 18. Handle invalid date ranges
    # -------------------------------------------------------------
    def test_18_handle_invalid_date_ranges(self):
        """18. Invalid date formats or inverted ranges raise ValueError cleanly."""
        self._setup_rich_test_data()
        with self.assertRaises(ValueError):
            services.advanced_vault_search(self.staff_token, trip_start="2026-12-31", trip_end="2026-12-01")

        with self.assertRaises(ValueError):
            services.advanced_vault_search(self.staff_token, trip_start="invalid-date")

    # -------------------------------------------------------------
    # 19. Handle missing passport values
    # -------------------------------------------------------------
    def test_19_handle_missing_passport_values(self):
        """19. Travellers with NULL or missing passport values do not crash search."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Aarav Sharma")
        self.assertEqual(len(res['travellers']), 1)
        self.assertIsNone(res['travellers'][0]['masked_passport'])

    # -------------------------------------------------------------
    # 20. Handle malformed extracted_data
    # -------------------------------------------------------------
    def test_20_handle_malformed_extracted_data(self):
        """20. Documents with corrupt/invalid JSON in extracted_data do not crash search."""
        self._setup_rich_test_data()
        # DOC-09 has corrupt JSON
        res = services.advanced_vault_search(self.staff_token, query="Sneha")
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-09", doc_ids)

    # -------------------------------------------------------------
    # 21. Prevent duplicate document results
    # -------------------------------------------------------------
    def test_21_prevent_duplicate_document_results(self):
        """21. Joins across multiple travellers or trips do not create duplicate document entries."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Dubai")
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertEqual(len(doc_ids), len(set(doc_ids)), "Document list must contain zero duplicate IDs.")

    # -------------------------------------------------------------
    # 22. Verify pagination
    # -------------------------------------------------------------
    def test_22_verify_pagination(self):
        """22. Server-side pagination with limit and offset."""
        self._setup_rich_test_data()
        page1 = services.advanced_vault_search(self.staff_token, limit=3, offset=0)
        page2 = services.advanced_vault_search(self.staff_token, limit=3, offset=3)

        self.assertEqual(len(page1['documents']), 3)
        self.assertEqual(len(page2['documents']), 3)
        p1_ids = [d['doc_id'] for d in page1['documents']]
        p2_ids = [d['doc_id'] for d in page2['documents']]
        # Sets must not overlap
        self.assertEqual(len(set(p1_ids).intersection(set(p2_ids))), 0)

    # -------------------------------------------------------------
    # 23. Verify deterministic ordering
    # -------------------------------------------------------------
    def test_23_verify_deterministic_ordering(self):
        """23. Search results return in identical deterministic order across repeat calls."""
        self._setup_rich_test_data()
        call1 = services.advanced_vault_search(self.staff_token, destination="Dubai")
        call2 = services.advanced_vault_search(self.staff_token, destination="Dubai")
        c1_ids = [d['doc_id'] for d in call1['documents']]
        c2_ids = [d['doc_id'] for d in call2['documents']]
        self.assertEqual(c1_ids, c2_ids)

    # -------------------------------------------------------------
    # 24. Verify unauthenticated access rejection
    # -------------------------------------------------------------
    def test_24_verify_unauthenticated_rejection(self):
        """24. Missing or empty session_token raises PermissionError."""
        self._setup_rich_test_data()
        with self.assertRaises(PermissionError):
            services.advanced_vault_search(None, query="Amit")

        with self.assertRaises(PermissionError):
            services.advanced_vault_search("", query="Amit")

    # -------------------------------------------------------------
    # 25. Verify session expiry behavior
    # -------------------------------------------------------------
    def test_25_verify_session_expiry(self):
        """25. Expired session token raises PermissionError."""
        self._setup_rich_test_data()
        with self.assertRaises(PermissionError):
            services.advanced_vault_search(self.expired_token, query="Amit")

    # -------------------------------------------------------------
    # 26. Verify SQL injection resistance
    # -------------------------------------------------------------
    def test_26_verify_sql_injection_resistance(self):
        """26. Malicious SQL payloads in query or filters are safely parameterized."""
        self._setup_rich_test_data()
        sqli_payload = "' OR 1=1; --"
        res = services.advanced_vault_search(self.staff_token, query=sqli_payload)
        # Should return 0 matching documents because no entity is named literally "' OR 1=1; --"
        self.assertEqual(len(res['documents']), 0)
        self.assertEqual(len(res['customers']), 0)

    # -------------------------------------------------------------
    # 27. Verify search results do not expose full OCR content
    # -------------------------------------------------------------
    def test_27_no_ocr_or_extracted_data_exposure(self):
        """27. Search result documents do not expose raw OCR text or extracted_data JSON."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Rohan")
        for doc in res['documents']:
            self.assertNotIn("extracted_data", doc)
            self.assertNotIn("ocr_text", doc)
            self.assertNotIn("file_path", doc) # Internal filesystem path must not be leaked

    # -------------------------------------------------------------
    # 28. Verify result Preview uses existing secure service
    # -------------------------------------------------------------
    def test_28_preview_uses_secure_service(self):
        """28. Previewing a search result invokes get_document_for_download_or_preview."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="Amit Mehta")
        doc_item = res['documents'][0]
        preview = services.get_document_for_download_or_preview(
            doc_id=doc_item['doc_id'],
            customer_id=doc_item['customer_id'],
            session_token=self.staff_token,
            action='preview'
        )
        self.assertEqual(preview['mime_type'], 'application/pdf')
        self.assertEqual(preview['file_bytes'], SAMPLE_PDF_BYTES)

    # -------------------------------------------------------------
    # 29. Verify result Download returns original bytes
    # -------------------------------------------------------------
    def test_29_download_returns_original_bytes(self):
        """29. Downloading a search result returns exact byte-identical content."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, document_type="Hotel Voucher")
        doc_item = res['documents'][0]
        dl = services.get_document_for_download_or_preview(
            doc_id=doc_item['doc_id'],
            customer_id=doc_item['customer_id'],
            session_token=self.staff_token,
            action='download'
        )
        self.assertEqual(dl['mime_type'], 'image/jpeg')
        self.assertEqual(dl['file_bytes'], SAMPLE_JPG_BYTES)

    # -------------------------------------------------------------
    # 30. Verify cross-customer ownership checks
    # -------------------------------------------------------------
    def test_30_cross_customer_ownership_checks(self):
        """30. Downloading a document with a mismatched customer ID raises PermissionError."""
        self._setup_rich_test_data()
        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview(
                doc_id="DOC-01", # Belongs to C-01
                customer_id="C-02", # Wrong customer!
                session_token=self.staff_token,
                action='download'
            )

    # -------------------------------------------------------------
    # 31. Verify multiple travellers on the same trip
    # -------------------------------------------------------------
    def test_31_multiple_travellers_on_same_trip(self):
        """31. Searching trip T-03 returns documents for both Rohan and Priya."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="T-03")
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-06", doc_ids) # Rohan's doc
        self.assertIn("DOC-07", doc_ids) # Priya's doc

    # -------------------------------------------------------------
    # 32. Verify multiple trips for one customer
    # -------------------------------------------------------------
    def test_32_multiple_trips_one_customer(self):
        """32. Searching customer C-01 returns documents across both T-01 and T-02."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="C-01")
        doc_ids = [d['doc_id'] for d in res['documents']]
        self.assertIn("DOC-01", doc_ids) # From T-01
        self.assertIn("DOC-04", doc_ids) # From T-02
        self.assertIn("DOC-05", doc_ids) # From Reusable Vault

    # -------------------------------------------------------------
    # 33. Verify no matching results
    # -------------------------------------------------------------
    def test_33_no_matching_results(self):
        """33. Nonexistent search term returns empty lists cleanly without exception."""
        self._setup_rich_test_data()
        res = services.advanced_vault_search(self.staff_token, query="NonexistentTerm99999")
        self.assertEqual(len(res['documents']), 0)
        self.assertEqual(len(res['customers']), 0)
        self.assertEqual(len(res['travellers']), 0)
        self.assertEqual(len(res['trips']), 0)
        self.assertEqual(res['total_documents'], 0)

    # -------------------------------------------------------------
    # 34. Verify production database remains unchanged
    # -------------------------------------------------------------
    def test_34_production_database_untouched(self):
        """34. Production database hash and byte size match preflight baseline."""
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(curr_size, self.initial_prod_db_size)
        self.assertEqual(curr_sha256, self.initial_prod_db_sha256)

    # -------------------------------------------------------------
    # 35. Verify stored documents remain unchanged
    # -------------------------------------------------------------
    def test_35_stored_documents_untouched(self):
        """35. Production documents count, total size, and sha256 signature remain identical."""
        curr_files = sorted(os.listdir(PROD_DOCS_DIR))
        self.assertEqual(len(curr_files), self.initial_doc_count)
        curr_total_size = sum(os.path.getsize(os.path.join(PROD_DOCS_DIR, f)) for f in curr_files)
        self.assertEqual(curr_total_size, self.initial_doc_total_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
