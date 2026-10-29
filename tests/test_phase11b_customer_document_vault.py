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
EXPECTED_PROD_SHA256 = ("aad3781fa1628fe5459b050cea8ff76947f47d320d71d1bf244f50c699c8971e", "c71b76035b46c6db338e033d6e1dbdcd753dba47d3028b8cb65c576910934ef7", "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d")
EXPECTED_PROD_SIZE = (143360, 147456, 167936)
EXPECTED_DOC_COUNT = 74
EXPECTED_DOC_SIG = "f44fc49ff70ab4a7932cded84727f386e1cac9b6e81548ab2ad325abe8487dda"

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
# Valid 1x1 pixel JPEG
SAMPLE_JPG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
# Valid 1x1 pixel PNG
SAMPLE_PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\r\xef\x8f\x8e\x00\x00\x00\x00IEND\xaeB`\x82"

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


class TestPhase11bCustomerDocumentVault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Preflight baseline audit of production DB and documents
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()

        cls.initial_doc_files = sorted(os.listdir(PROD_DOCS_DIR))
        inv_hasher = hashlib.sha256()
        for f in cls.initial_doc_files:
            inv_hasher.update(f.encode('utf-8'))
            inv_hasher.update(str(os.path.getsize(os.path.join(PROD_DOCS_DIR, f))).encode('utf-8'))
        cls.initial_doc_sig = inv_hasher.hexdigest()

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
        users = [
            ("U-STAFF-11B", "staff_11b", "Junior Staff", "Staff"),
            ("U-SUPER-11B", "super_11b", "Senior Supervisor", "Supervisor"),
            ("U-ADMIN-11B", "admin_11b", "System Administrator", "Admin"),
        ]
        for uid, uname, fname, role in users:
            conn.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                         (uid, uname, b"fake", b"salt", fname, role))

        exp = (datetime.now() + timedelta(hours=24)).isoformat()
        expired = (datetime.now() - timedelta(hours=2)).isoformat()
        cls.staff_token = "token-staff-11b"
        cls.super_token = "token-super-11b"
        cls.admin_token = "token-admin-11b"
        cls.expired_token = "token-expired-11b"

        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF-11B", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.super_token, "U-SUPER-11B", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN-11B", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.expired_token, "U-SUPER-11B", expired))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        shutil.rmtree(cls.test_dir, ignore_errors=True)

        # Strict production database immutability check
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        if curr_sha256 != cls.initial_prod_db_sha256 or curr_size != cls.initial_prod_db_size:
            raise RuntimeError("CRITICAL INTEGRITY BREACH: Production database was modified during testing!")

        # Strict production document files immutability check
        curr_doc_files = sorted(os.listdir(PROD_DOCS_DIR))
        inv_hasher = hashlib.sha256()
        for f in curr_doc_files:
            inv_hasher.update(f.encode('utf-8'))
            inv_hasher.update(str(os.path.getsize(os.path.join(PROD_DOCS_DIR, f))).encode('utf-8'))
        curr_doc_sig = inv_hasher.hexdigest()
        if curr_doc_sig != cls.initial_doc_sig or len(curr_doc_files) != len(cls.initial_doc_files):
            raise RuntimeError("CRITICAL INTEGRITY BREACH: Production documents directory was modified during testing!")

    def setUp(self):
        conn = database.get_connection()
        for tbl in ['activity', 'documents', 'requirements', 'trip_travellers', 'trips', 'travellers', 'customers']:
            conn.execute(f"DELETE FROM {tbl}")
        conn.commit()
        conn.close()

    def _create_test_file(self, filename, content_bytes):
        p = os.path.join(self.docs_dir, filename)
        with open(p, "wb") as f:
            f.write(content_bytes)
        return p

    def _setup_multi_trip_customer_data(self):
        conn = database.get_connection()
        # Customer 1: Amit Mehta
        conn.execute("INSERT INTO customers (id, name, customer_type, status, mobile, email) VALUES ('C-01', 'Amit Mehta', 'Individual', 'Active', '9876543210', 'amit@example.com')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-01A', 'C-01', 'Amit Mehta', 'Adult', 'Lead Traveller', 'P-AMIT-001')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-01B', 'C-01', 'Sunita Mehta', 'Adult', 'Spouse', 'P-SUNITA-002')")

        # Trip 1: Dubai Holiday
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-01', 'C-01', 'Dubai Holiday', 'Dubai', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-01', 'TR-01A')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-01', 'TR-01B')")

        # Trip 2: London Trip
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-02', 'C-01', 'London Business', 'London', '2027-04-01', '2027-04-10', 'NOT READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-02', 'TR-01A')")

        # Requirements and documents for Customer 1
        f_pdf = self._create_test_file("amit_passport.pdf", SAMPLE_PDF_BYTES)
        f_jpg = self._create_test_file("sunita_visa.jpg", SAMPLE_JPG_BYTES)
        f_png = self._create_test_file("hotel_voucher.png", SAMPLE_PNG_BYTES)
        f_flt = self._create_test_file("london_flight.pdf", SAMPLE_PDF_BYTES)
        f_vlt = self._create_test_file("reusable_id.pdf", SAMPLE_PDF_BYTES)

        # T-01 documents
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-01', 'T-01', 'TR-01A', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-01', 'REQ-01', 'Verified', ?, '2026-10-01T10:00:00')", (f_pdf,))

        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-02', 'T-01', 'TR-01B', 'Visa / Entry Document', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-02', 'REQ-02', 'Verified', ?, '2026-10-02T11:00:00')", (f_jpg,))

        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-03', 'T-01', NULL, 'Hotel Voucher', 'TRIP')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-03', 'REQ-03', 'Verified', ?, '2026-10-03T12:00:00')", (f_png,))

        # T-02 documents
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-04', 'T-02', 'TR-01A', 'Flight Ticket', 'TRIP')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-04', 'REQ-04', 'Under Review', ?, '2026-10-04T13:00:00')", (f_flt,))

        # Reusable Traveller Vault document (trip_id IS NULL)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-05', NULL, 'TR-01A', 'National ID', 'TRAVELLER_VAULT')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-05', 'REQ-05', 'Verified', ?, '2026-10-05T14:00:00')", (f_vlt,))

        # Customer 2: Neha Kapoor
        conn.execute("INSERT INTO customers (id, name, customer_type, status, mobile, email) VALUES ('C-02', 'Neha Kapoor', 'Individual', 'Active', '9123456780', 'neha@example.com')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-02', 'C-02', 'Neha Kapoor', 'Adult', 'Lead Traveller', 'P-NEHA-003')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-03', 'C-02', 'Paris Tour', 'Paris', '2026-11-01', '2026-11-05', 'DRAFT')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-03', 'TR-02')")

        f_neha = self._create_test_file("neha_passport.pdf", SAMPLE_PDF_BYTES)
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-06', 'T-03', 'TR-02', 'Passport', 'TRAVELLER')")
        conn.execute("INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES ('DOC-06', 'REQ-06', 'Verified', ?, '2026-10-06T15:00:00')", (f_neha,))

        conn.commit()
        conn.close()

    # -------------------------------------------------------------
    # 1. Find customer by name
    # -------------------------------------------------------------
    def test_01_find_customer_by_name(self):
        """1. Search customer by exact or partial name returns correct matching customer records."""
        self._setup_multi_trip_customer_data()

        # Partial match
        results = services.search_customers("Amit", self.staff_token)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], "C-01")
        self.assertEqual(results[0]['name'], "Amit Mehta")

        # Case-insensitive match
        results_case = services.search_customers("neha", self.staff_token)
        self.assertEqual(len(results_case), 1)
        self.assertEqual(results_case[0]['id'], "C-02")

        # Empty query returns all
        results_all = services.search_customers("", self.staff_token)
        self.assertEqual(len(results_all), 2)

    # -------------------------------------------------------------
    # 2. Retrieve all documents for a customer
    # -------------------------------------------------------------
    def test_02_retrieve_all_documents_for_customer(self):
        """2. Retrieve all documents associated with a customer across all scopes."""
        self._setup_multi_trip_customer_data()

        docs_c1 = services.get_customer_documents("C-01", self.staff_token)
        # Should have 5 documents: Amit Passport, Sunita Visa, Hotel Voucher, London Flight, Reusable ID
        self.assertEqual(len(docs_c1), 5)
        doc_names = [d['req_name'] for d in docs_c1]
        self.assertIn("Passport", doc_names)
        self.assertIn("Visa / Entry Document", doc_names)
        self.assertIn("Hotel Voucher", doc_names)
        self.assertIn("Flight Ticket", doc_names)
        self.assertIn("National ID", doc_names)

        # Customer 2 should have 1 document
        docs_c2 = services.get_customer_documents("C-02", self.staff_token)
        self.assertEqual(len(docs_c2), 1)
        self.assertEqual(docs_c2[0]['doc_id'], "DOC-06")

    # -------------------------------------------------------------
    # 3. Retrieve documents across multiple trips
    # -------------------------------------------------------------
    def test_03_retrieve_documents_across_multiple_trips(self):
        """3. Customer vault includes documents from different trips belonging to that customer."""
        self._setup_multi_trip_customer_data()

        docs = services.get_customer_documents("C-01", self.staff_token)
        trip_ids = set(d['trip_id'] for d in docs if d['trip_id'])
        self.assertIn("T-01", trip_ids)
        self.assertIn("T-02", trip_ids)

    # -------------------------------------------------------------
    # 4. Retrieve documents for multiple travellers
    # -------------------------------------------------------------
    def test_04_retrieve_documents_for_multiple_travellers(self):
        """4. Customer vault partitions documents by traveller under the same customer."""
        self._setup_multi_trip_customer_data()

        docs = services.get_customer_documents("C-01", self.staff_token)
        traveller_names = set(d['traveller_name'] for d in docs if d['traveller_name'])
        self.assertIn("Amit Mehta", traveller_names)
        self.assertIn("Sunita Mehta", traveller_names)

    # -------------------------------------------------------------
    # 5. Preview an authorized PDF
    # -------------------------------------------------------------
    def test_05_preview_authorized_pdf(self):
        """5. Previewing an authorized PDF returns correct file bytes, MIME type, and safe name."""
        self._setup_multi_trip_customer_data()

        res = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token, action='preview')
        self.assertEqual(res['mime_type'], "application/pdf")
        self.assertEqual(res['file_bytes'], SAMPLE_PDF_BYTES)
        self.assertEqual(res['file_name'], "Amit_Mehta_Passport.pdf")

    # -------------------------------------------------------------
    # 6. Preview an authorized JPG
    # -------------------------------------------------------------
    def test_06_preview_authorized_jpg(self):
        """6. Previewing an authorized JPG returns intact JPEG bytes and image/jpeg MIME."""
        self._setup_multi_trip_customer_data()

        res = services.get_document_for_download_or_preview("DOC-02", "C-01", self.staff_token, action='preview')
        self.assertEqual(res['mime_type'], "image/jpeg")
        self.assertEqual(res['file_bytes'], SAMPLE_JPG_BYTES)
        self.assertEqual(res['file_name'], "Sunita_Mehta_Visa_Entry_Document.jpg")

    # -------------------------------------------------------------
    # 7. Preview an authorized PNG
    # -------------------------------------------------------------
    def test_07_preview_authorized_png(self):
        """7. Previewing an authorized PNG returns intact PNG bytes and image/png MIME."""
        self._setup_multi_trip_customer_data()

        res = services.get_document_for_download_or_preview("DOC-03", "C-01", self.staff_token, action='preview')
        self.assertEqual(res['mime_type'], "image/png")
        self.assertEqual(res['file_bytes'], SAMPLE_PNG_BYTES)
        self.assertEqual(res['file_name'], "Amit_Mehta_Hotel_Voucher.png")

    # -------------------------------------------------------------
    # 8. Download original PDF bytes unchanged
    # -------------------------------------------------------------
    def test_08_download_original_pdf_bytes_unchanged(self):
        """8. Downloading an authorized PDF returns byte-identical original content."""
        self._setup_multi_trip_customer_data()

        res = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token, action='download')
        self.assertEqual(hashlib.sha256(res['file_bytes']).hexdigest(), hashlib.sha256(SAMPLE_PDF_BYTES).hexdigest())
        self.assertEqual(len(res['file_bytes']), len(SAMPLE_PDF_BYTES))

    # -------------------------------------------------------------
    # 9. Download original image bytes unchanged
    # -------------------------------------------------------------
    def test_09_download_original_image_bytes_unchanged(self):
        """9. Downloading an authorized JPG/PNG returns byte-identical original content."""
        self._setup_multi_trip_customer_data()

        res_jpg = services.get_document_for_download_or_preview("DOC-02", "C-01", self.staff_token, action='download')
        self.assertEqual(res_jpg['file_bytes'], SAMPLE_JPG_BYTES)

        res_png = services.get_document_for_download_or_preview("DOC-03", "C-01", self.staff_token, action='download')
        self.assertEqual(res_png['file_bytes'], SAMPLE_PNG_BYTES)

    # -------------------------------------------------------------
    # 10. Reject unauthenticated access
    # -------------------------------------------------------------
    def test_10_reject_unauthenticated_access(self):
        """10. Unauthenticated access (None or empty token) is rejected with PermissionError."""
        self._setup_multi_trip_customer_data()

        with self.assertRaises(PermissionError):
            services.get_customer_documents("C-01", None)

        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview("DOC-01", "C-01", None)

        with self.assertRaises(PermissionError):
            services.search_customers("Amit", "")

    # -------------------------------------------------------------
    # 11. Reject unauthorized document access (expired token)
    # -------------------------------------------------------------
    def test_11_reject_expired_session(self):
        """11. Expired or invalid session token is rejected with PermissionError."""
        self._setup_multi_trip_customer_data()

        with self.assertRaises(PermissionError):
            services.get_customer_documents("C-01", self.expired_token)

        with self.assertRaises(PermissionError):
            services.get_document_for_download_or_preview("DOC-01", "C-01", "invalid-token-xyz")

    # -------------------------------------------------------------
    # 12. Reject cross-customer document mismatch
    # -------------------------------------------------------------
    def test_12_reject_cross_customer_document_mismatch(self):
        """12. Attempting to access Customer 2's document under Customer 1's context is rejected."""
        self._setup_multi_trip_customer_data()

        # DOC-06 belongs to Customer 2 (Neha). Attempt to retrieve under Customer 1 context.
        with self.assertRaises(PermissionError) as ctx:
            services.get_document_for_download_or_preview("DOC-06", "C-01", self.staff_token)
        self.assertIn("Security violation", str(ctx.exception))
        self.assertIn("does not belong to customer 'C-01'", str(ctx.exception))

    # -------------------------------------------------------------
    # 13. Reject cross-traveller document mismatch / verify traveller ownership
    # -------------------------------------------------------------
    def test_13_traveller_ownership_metadata_integrity(self):
        """13. Document metadata accurately links to the specific traveller without cross-contamination."""
        self._setup_multi_trip_customer_data()

        res_amit = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertEqual(res_amit['traveller_name'], "Amit Mehta")

        res_sunita = services.get_document_for_download_or_preview("DOC-02", "C-01", self.staff_token)
        self.assertEqual(res_sunita['traveller_name'], "Sunita Mehta")

    # -------------------------------------------------------------
    # 14. Reject path traversal
    # -------------------------------------------------------------
    def test_14_reject_path_traversal(self):
        """14. Document records pointing to path traversal sequences are rejected."""
        self._setup_multi_trip_customer_data()
        conn = database.get_connection()
        conn.execute("UPDATE documents SET file_path = '../../etc/passwd' WHERE id = 'DOC-01'")
        conn.commit()
        conn.close()

        with self.assertRaises(FileNotFoundError) as ctx:
            services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertIn("outside the approved document storage directory", str(ctx.exception))

    # -------------------------------------------------------------
    # 15. Reject paths outside the storage root
    # -------------------------------------------------------------
    def test_15_reject_paths_outside_storage_root(self):
        """15. Document records referencing files outside the approved directory are blocked."""
        self._setup_multi_trip_customer_data()
        conn = database.get_connection()
        conn.execute("UPDATE documents SET file_path = 'C:/Windows/System32/drivers/etc/hosts' WHERE id = 'DOC-01'")
        conn.commit()
        conn.close()

        with self.assertRaises(FileNotFoundError) as ctx:
            services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertIn("outside the approved document storage directory", str(ctx.exception))

    # -------------------------------------------------------------
    # 16. Handle missing files gracefully
    # -------------------------------------------------------------
    def test_16_handle_missing_files_gracefully(self):
        """16. When document file is missing on disk, service raises descriptive FileNotFoundError."""
        self._setup_multi_trip_customer_data()
        missing_doc_path = os.path.join(self.docs_dir, "amit_passport.pdf")
        if os.path.exists(missing_doc_path):
            os.remove(missing_doc_path)

        with self.assertRaises(FileNotFoundError) as ctx:
            services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertIn("does not exist on disk", str(ctx.exception))

    # -------------------------------------------------------------
    # 17. Handle unsupported formats gracefully
    # -------------------------------------------------------------
    def test_17_handle_unsupported_formats_gracefully(self):
        """17. Non-standard file extensions are served with application/octet-stream fallback without crash."""
        self._setup_multi_trip_customer_data()
        f_txt = self._create_test_file("notes.txt", b"Plain text travel notes")
        conn = database.get_connection()
        conn.execute("UPDATE documents SET file_path = ? WHERE id = 'DOC-01'", (f_txt,))
        conn.commit()
        conn.close()

        res = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertEqual(res['mime_type'], "application/octet-stream")
        self.assertEqual(res['file_bytes'], b"Plain text travel notes")

    # -------------------------------------------------------------
    # 18. Handle malformed files gracefully
    # -------------------------------------------------------------
    def test_18_handle_malformed_files_gracefully(self):
        """18. Malformed or zero-byte files download original bytes safely without crashing."""
        self._setup_multi_trip_customer_data()
        f_empty = self._create_test_file("empty.pdf", b"")
        conn = database.get_connection()
        conn.execute("UPDATE documents SET file_path = ? WHERE id = 'DOC-01'", (f_empty,))
        conn.commit()
        conn.close()

        res = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        self.assertEqual(res['file_bytes'], b"")
        self.assertEqual(res['file_size'], 0)

    # -------------------------------------------------------------
    # 19. Handle oversized files safely
    # -------------------------------------------------------------
    def test_19_handle_oversized_files_safely(self):
        """19. Files exceeding safety threshold (>50MB) are rejected with ValueError."""
        self._setup_multi_trip_customer_data()
        # Mock os.path.getsize to simulate a 60MB file
        orig_getsize = os.path.getsize
        try:
            os.path.getsize = lambda p: 60 * 1024 * 1024 if "amit_passport.pdf" in p else orig_getsize(p)
            with self.assertRaises(ValueError) as ctx:
                services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
            self.assertIn("exceeds maximum allowed size", str(ctx.exception))
        finally:
            os.path.getsize = orig_getsize

    # -------------------------------------------------------------
    # 20. Verify download filename safety
    # -------------------------------------------------------------
    def test_20_verify_download_filename_safety(self):
        """20. Download filename is sanitized, strips special chars, and preserves correct extension."""
        self._setup_multi_trip_customer_data()
        conn = database.get_connection()
        conn.execute("UPDATE travellers SET name = 'Dr. Amit Mehta / VIP #1' WHERE id = 'TR-01A'")
        conn.commit()
        conn.close()

        res = services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token)
        # Should sanitize slashes, hash, spaces into underscores
        self.assertEqual(res['file_name'], "Dr._Amit_Mehta_VIP_1_Passport.pdf")
        self.assertNotIn("/", res['file_name'])
        self.assertNotIn("#", res['file_name'])
        self.assertTrue(res['file_name'].endswith(".pdf"))

    # -------------------------------------------------------------
    # 21. Verify document access audit logging
    # -------------------------------------------------------------
    def test_21_verify_document_access_audit_logging(self):
        """21. Preview and download events are logged in activity table without sensitive data."""
        self._setup_multi_trip_customer_data()

        # Execute download
        services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token, action='download')

        conn = database.get_connection()
        row = conn.execute("SELECT * FROM activity WHERE customer_id = 'C-01' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertIn("Document 'Passport' (Downloaded) for customer 'C-01' accessed by Junior Staff (Staff)", row['description'])
        # Ensure no sensitive passport numbers or tokens in log
        self.assertNotIn("P-AMIT-001", row['description'])
        self.assertNotIn(self.staff_token, row['description'])

    # -------------------------------------------------------------
    # 22. Confirm original stored files remain unchanged
    # -------------------------------------------------------------
    def test_22_confirm_original_stored_files_remain_unchanged(self):
        """22. Preview and download operations do not mutate or overwrite stored files."""
        self._setup_multi_trip_customer_data()
        p = os.path.join(self.docs_dir, "amit_passport.pdf")
        with open(p, 'rb') as f:
            before_hash = hashlib.sha256(f.read()).hexdigest()

        # Perform multiple previews and downloads
        services.get_document_for_download_or_preview("DOC-01", "C-01", self.staff_token, action='preview')
        services.get_document_for_download_or_preview("DOC-01", "C-01", self.super_token, action='download')

        with open(p, 'rb') as f:
            after_hash = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(before_hash, after_hash, "Original stored file on disk must be completely unchanged.")

    # -------------------------------------------------------------
    # 23. Confirm production database remains unchanged
    # -------------------------------------------------------------
    def test_23_production_database_untouched(self):
        """23. Verify production database remains completely untouched during test run."""
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
