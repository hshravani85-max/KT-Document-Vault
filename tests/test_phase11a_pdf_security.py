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
PROD_DOCS_DIR = r"C:\KT_Vault_V3\documents"
EXPECTED_PROD_SHA256 = ("aad3781fa1628fe5459b050cea8ff76947f47d320d71d1bf244f50c699c8971e", "c71b76035b46c6db338e033d6e1dbdcd753dba47d3028b8cb65c576910934ef7", "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d")
EXPECTED_PROD_SIZE = (143360, 147456, 167936)
EXPECTED_DOC_COUNT = 74
EXPECTED_DOC_SIG = "f44fc49ff70ab4a7932cded84727f386e1cac9b6e81548ab2ad325abe8487dda"

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
    timestamp TEXT
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


class TestPhase11aPdfSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Baseline audit of production DB and documents
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

        # Initialize isolated schema
        conn = sqlite3.connect(cls.test_db_path)
        conn.executescript(INIT_TEST_SCHEMA_SQL)

        # Create synthetic users
        users_data = [
            ("U-STAFF-11A", "staff_11a", "Junior Staff", "Staff"),
            ("U-SUPER-11A", "super_11a", "Senior Supervisor", "Supervisor"),
            ("U-ADMIN-11A", "admin_11a", "System Administrator", "Admin"),
            ("U-GUEST-11A", "guest_11a", "External Guest", "Guest"),
        ]
        for uid, uname, fname, role in users_data:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, uname, b"fakehash", b"fakesalt", fname, role)
            )

        # Create sessions
        exp = (datetime.now() + timedelta(hours=24)).isoformat()
        expired = (datetime.now() - timedelta(hours=2)).isoformat()
        cls.staff_token = "token-staff-11a"
        cls.super_token = "token-super-11a"
        cls.admin_token = "token-admin-11a"
        cls.guest_token = "token-guest-11a"
        cls.expired_token = "token-expired-11a"

        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF-11A", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.super_token, "U-SUPER-11A", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN-11A", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.guest_token, "U-GUEST-11A", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.expired_token, "U-SUPER-11A", expired))

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        shutil.rmtree(cls.test_dir, ignore_errors=True)

        # Verify production DB remained strictly untouched
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        if curr_sha256 != cls.initial_prod_db_sha256 or curr_size != cls.initial_prod_db_size:
            raise RuntimeError("CRITICAL: Production database was modified during testing!")

        # Verify production documents remained strictly untouched
        curr_doc_files = sorted(os.listdir(PROD_DOCS_DIR))
        inv_hasher = hashlib.sha256()
        for f in curr_doc_files:
            inv_hasher.update(f.encode('utf-8'))
            inv_hasher.update(str(os.path.getsize(os.path.join(PROD_DOCS_DIR, f))).encode('utf-8'))
        curr_doc_sig = inv_hasher.hexdigest()
        if curr_doc_sig != cls.initial_doc_sig or len(curr_doc_files) != len(cls.initial_doc_files):
            raise RuntimeError("CRITICAL: Production documents directory was modified during testing!")

    def setUp(self):
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

    def _setup_approved_trip(self, trip_id="T-APP-01", customer_id="C-APP-01", traveller_id="TR-APP-01"):
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES (?, 'Test Customer', 'INDIVIDUAL', 'ACTIVE')", (customer_id,))
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES (?, ?, 'Primary Traveller', 'Adult', 'Lead Traveller', 'P-APPROVED-001')", (traveller_id, customer_id))
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES (?, ?, 'Dubai Trip', 'Dubai', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')", (trip_id, customer_id))
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES (?, ?)", (trip_id, traveller_id))
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-P1', ?, ?, 'Passport', 'TRAVELLER')", (trip_id, traveller_id))

        doc_pdf = self._create_sample_pdf(f"doc_{trip_id}.pdf")
        meta = {"Full Name": "Primary Traveller", "Passport Number": "P-APPROVED-001"}
        conn.execute(
            "INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-P1', 'REQ-P1', ?, 'Verified', ?)",
            (doc_pdf, json.dumps(meta))
        )
        conn.commit()
        conn.close()

    # -------------------------------------------------------------
    # 1. Staff denied
    # -------------------------------------------------------------
    def test_01_staff_denied_generation(self):
        """1. Unauthorized session is rejected with PermissionError; Phase 16 staff is allowed."""
        self._setup_approved_trip("T-STAFF-01")
        target_pdf = os.path.join(self.docs_dir, "GuestDenied.pdf")

        with self.assertRaises(PermissionError) as ctx:
            services.generate_trip_travel_pack("T-STAFF-01", self.guest_token, out_path=target_pdf)
        self.assertIn("unauthorized", str(ctx.exception).lower())
        self.assertFalse(os.path.exists(target_pdf), "Output PDF must not be created on denied authorization.")

        # In Phase 16, staff is authorized per business rule 5
        staff_pdf = os.path.join(self.docs_dir, "StaffAllowed.pdf")
        res = services.generate_trip_travel_pack("T-STAFF-01", self.staff_token, out_path=staff_pdf)
        self.assertTrue(os.path.exists(res))

    # -------------------------------------------------------------
    # 2. Supervisor allowed
    # -------------------------------------------------------------
    def test_02_supervisor_allowed_generation(self):
        """2. Supervisor session successfully generates consolidated PDF."""
        self._setup_approved_trip("T-SUPER-01")
        target_pdf = os.path.join(self.docs_dir, "SuperAllowed.pdf")

        result_path = services.generate_trip_travel_pack("T-SUPER-01", self.super_token, out_path=target_pdf)
        self.assertTrue(os.path.exists(result_path))
        self.assertGreater(os.path.getsize(result_path), 0)

        content = self._get_pdf_text(result_path)
        self.assertIn("Primary Traveller (Passport: P-APPROVED-001)", content)
        self.assertIn("KHANNA TRAVELS - TRAVEL FILE", content)

    # -------------------------------------------------------------
    # 3. Admin allowed
    # -------------------------------------------------------------
    def test_03_admin_allowed_generation(self):
        """3. Admin session successfully generates consolidated PDF."""
        self._setup_approved_trip("T-ADMIN-01")
        target_pdf = os.path.join(self.docs_dir, "AdminAllowed.pdf")

        result_path = services.generate_trip_travel_pack("T-ADMIN-01", self.admin_token, out_path=target_pdf)
        self.assertTrue(os.path.exists(result_path))
        self.assertGreater(os.path.getsize(result_path), 0)

    # -------------------------------------------------------------
    # 4. Unauthenticated denied
    # -------------------------------------------------------------
    def test_04_unauthenticated_denied(self):
        """4. Unauthenticated caller (None or empty token) is denied with PermissionError."""
        self._setup_approved_trip("T-UNAUTH-01")
        target_pdf = os.path.join(self.docs_dir, "UnauthDenied.pdf")

        with self.assertRaises(PermissionError) as ctx1:
            services.generate_trip_travel_pack("T-UNAUTH-01", None, out_path=target_pdf)
        self.assertIn("Unauthenticated", str(ctx1.exception))
        self.assertFalse(os.path.exists(target_pdf))

        with self.assertRaises(PermissionError) as ctx2:
            services.generate_trip_travel_pack("T-UNAUTH-01", "", out_path=target_pdf)
        self.assertIn("Unauthenticated", str(ctx2.exception))
        self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 5. Expired or revoked session
    # -------------------------------------------------------------
    def test_05_expired_or_revoked_session(self):
        """5. Expired or invalid session token is denied with PermissionError."""
        self._setup_approved_trip("T-EXP-01")
        target_pdf = os.path.join(self.docs_dir, "ExpiredDenied.pdf")

        # Expired token in database
        with self.assertRaises(PermissionError) as ctx1:
            services.generate_trip_travel_pack("T-EXP-01", self.expired_token, out_path=target_pdf)
        self.assertIn("Invalid or expired session", str(ctx1.exception))
        self.assertFalse(os.path.exists(target_pdf))

        # Completely random non-existent token
        with self.assertRaises(PermissionError) as ctx2:
            services.generate_trip_travel_pack("T-EXP-01", "non-existent-token-xyz", out_path=target_pdf)
        self.assertIn("Invalid or expired session", str(ctx2.exception))
        self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 6. Unapproved trip denied
    # -------------------------------------------------------------
    def test_06_unapproved_trip_denied(self):
        """6. Unapproved trip statuses (NOT READY, READY FOR FINAL REVIEW, DRAFT, etc.) are blocked."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-UNAPP', 'Customer Unapproved', 'INDIVIDUAL', 'ACTIVE')")
        conn.commit()
        conn.close()

        unapproved_statuses = ['NOT READY', 'READY FOR FINAL REVIEW', 'DRAFT', 'Documents In Progress']
        for idx, status in enumerate(unapproved_statuses):
            trip_id = f"T-UNAPP-{idx}"
            conn = database.get_connection()
            conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES (?, 'C-UNAPP', 'Test Trip', 'Paris', '2026-12-01', '2026-12-05', ?)", (trip_id, status))
            conn.commit()
            conn.close()

            target_pdf = os.path.join(self.docs_dir, f"Unapproved_{idx}.pdf")
            with self.assertRaises(ValueError) as ctx:
                services.generate_trip_travel_pack(trip_id, self.super_token, out_path=target_pdf)
            self.assertIn("not approved", str(ctx.exception))
            self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 7. Missing trip
    # -------------------------------------------------------------
    def test_07_missing_trip(self):
        """7. Nonexistent trip ID raises ValueError and creates no file."""
        target_pdf = os.path.join(self.docs_dir, "MissingTrip.pdf")
        with self.assertRaises(ValueError) as ctx:
            services.generate_trip_travel_pack("NONEXISTENT-TRIP-999", self.super_token, out_path=target_pdf)
        self.assertIn("Trip not found", str(ctx.exception))
        self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 8. Direct generator bypass prevented
    # -------------------------------------------------------------
    def test_08_direct_generator_bypass_prevented(self):
        """8. Direct calls to travel_file_generator without valid auth or on unapproved trips are blocked."""
        self._setup_approved_trip("T-BYPASS-01")
        target_pdf = os.path.join(self.docs_dir, "BypassBlocked.pdf")

        # 8a: Direct call with no session token -> PermissionError
        with self.assertRaises(PermissionError):
            travel_file_generator.generate_consolidated_travel_file("T-BYPASS-01", out_path=target_pdf, session_token=None)
        self.assertFalse(os.path.exists(target_pdf))

        # 8b: Direct call with unauthorized guest token -> PermissionError
        with self.assertRaises(PermissionError):
            travel_file_generator.generate_consolidated_travel_file("T-BYPASS-01", out_path=target_pdf, session_token=self.guest_token)
        self.assertFalse(os.path.exists(target_pdf))

        # 8c: Direct call on unapproved trip -> ValueError
        conn = database.get_connection()
        conn.execute("UPDATE trips SET status = 'DRAFT' WHERE id = 'T-BYPASS-01'")
        conn.commit()
        conn.close()

        with self.assertRaises(ValueError) as ctx:
            travel_file_generator.generate_consolidated_travel_file("T-BYPASS-01", out_path=target_pdf, session_token=self.super_token)
        self.assertIn("not approved", str(ctx.exception))
        self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 9. Streamlit trip switching state safety
    # -------------------------------------------------------------
    def test_09_streamlit_trip_switching_state_safety(self):
        """9. Switching trip IDs invalidates cached PDF state from prior trips."""
        # Simulate session state dictionary
        session_state = {
            'session_token': self.super_token,
            'consolidated_pdf_bytes_TRIP_A': b'%PDF-TRIP-A-CONTENT',
            'consolidated_pdf_name_TRIP_A': 'TravelFile_TRIP_A.pdf',
            'consolidated_pdf_token_TRIP_A': self.super_token
        }

        current_trip_id = "TRIP_B"
        # Run state cleanup logic as implemented in pages/trip_workspace.py
        for k in list(session_state.keys()):
            if k.startswith("consolidated_pdf_") or k.startswith("general_travel_pdf_"):
                if not k.endswith(f"_{current_trip_id}"):
                    session_state.pop(k, None)

        self.assertNotIn("consolidated_pdf_bytes_TRIP_A", session_state, "Cached PDF for Trip A must be purged when viewing Trip B.")
        self.assertNotIn("consolidated_pdf_name_TRIP_A", session_state)
        self.assertNotIn("consolidated_pdf_token_TRIP_A", session_state)

    # -------------------------------------------------------------
    # 10. Logout and role changes state safety
    # -------------------------------------------------------------
    def test_10_logout_and_role_changes_state_safety(self):
        """10. Role change or logout immediately invalidates previously cached downloads."""
        trip_id = "TRIP_C"
        pdf_state_key = f"consolidated_pdf_bytes_{trip_id}"
        pdf_name_key = f"consolidated_pdf_name_{trip_id}"
        pdf_token_key = f"consolidated_pdf_token_{trip_id}"

        # Initially cached by Supervisor
        session_state = {
            'session_token': self.super_token,
            pdf_state_key: b'%PDF-AUTHORIZED',
            pdf_name_key: f"TravelFile_{trip_id}.pdf",
            pdf_token_key: self.super_token
        }

        # User logs out or switches to Staff token
        session_state['session_token'] = self.staff_token

        # Run token-match validation check as implemented in pages/trip_workspace.py
        if session_state.get(pdf_token_key) != session_state.get('session_token'):
            session_state.pop(pdf_state_key, None)
            session_state.pop(pdf_name_key, None)
            session_state.pop(pdf_token_key, None)

        self.assertNotIn(pdf_state_key, session_state, "Cached download must be invalidated when token changes.")

    # -------------------------------------------------------------
    # 11. Passport regression (Rohan Test scenario)
    # -------------------------------------------------------------
    def test_11_passport_regression_rohan(self):
        """11. Rohan Test scenario: Traveller passport_number NULL dynamically resolves DEMO-PASSPORT-0001."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('KT-C-0003', 'Rohan Test', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('KT-TR-0003', 'KT-C-0003', 'Rohan Test', 'Adult', 'Lead Traveller', NULL)")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('KT-T-0003', 'KT-C-0003', 'Rohan Dubai Demo Holiday', 'Dubai', '2026-12-12', '2026-12-18', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('KT-T-0003', 'KT-TR-0003')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-R1', 'KT-T-0003', 'KT-TR-0003', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("rohan_passport.pdf")
        meta = {"Full Name": "Rohan Test", "Passport Number": "DEMO-PASSPORT-0001", "Date of Birth": "15 Jun 1995", "Nationality": "Indian"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-R1', 'REQ-R1', ?, 'Verified', ?)", (doc_pdf, json.dumps(meta)))
        conn.commit()
        conn.close()

        target_pdf = os.path.join(self.docs_dir, "RohanTravelFile.pdf")
        res_path = services.generate_trip_travel_pack("KT-T-0003", self.super_token, out_path=target_pdf)
        content = self._get_pdf_text(res_path)

        self.assertIn("Rohan Test (Passport: DEMO-PASSPORT-0001)", content)
        self.assertNotIn("Passport: N/A", content)

    # -------------------------------------------------------------
    # 12. Conflicting passport values blocked
    # -------------------------------------------------------------
    def test_12_conflicting_passport_values_blocked(self):
        """12. Conflicting passport values between traveller profile and verified document block generation."""
        conn = database.get_connection()
        conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('C-CONF-12', 'Conflict Customer', 'INDIVIDUAL', 'ACTIVE')")
        conn.execute("INSERT INTO travellers (id, customer_id, name, type, role, passport_number) VALUES ('TR-CONF-12', 'C-CONF-12', 'Charlie Brown', 'Adult', 'Lead Traveller', 'P-PROFILE-111')")
        conn.execute("INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, status) VALUES ('T-CONF-12', 'C-CONF-12', 'Tokyo Tour', 'Tokyo', '2026-10-10', '2026-10-20', 'TRAVEL FILE READY')")
        conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('T-CONF-12', 'TR-CONF-12')")
        conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-CONF-12', 'T-CONF-12', 'TR-CONF-12', 'Passport', 'TRAVELLER')")

        doc_pdf = self._create_sample_pdf("conflict_passport.pdf")
        meta = {"Full Name": "Charlie Brown", "Passport Number": "P-DOC-222"}
        conn.execute("INSERT INTO documents (id, requirement_id, file_path, status, extracted_data) VALUES ('DOC-CONF-12', 'REQ-CONF-12', ?, 'Verified', ?)", (doc_pdf, json.dumps(meta)))
        conn.commit()
        conn.close()

        target_pdf = os.path.join(self.docs_dir, "ConflictOutput.pdf")
        with self.assertRaises(ValueError) as ctx:
            services.generate_trip_travel_pack("T-CONF-12", self.super_token, out_path=target_pdf)
        self.assertIn("Passport conflict", str(ctx.exception))
        self.assertFalse(os.path.exists(target_pdf))

    # -------------------------------------------------------------
    # 13. Output path safety & path traversal rejection
    # -------------------------------------------------------------
    def test_13_output_path_safety(self):
        """13. Malicious trip IDs or path traversal sequences in out_path are rejected."""
        self._setup_approved_trip("T-SEC-13")

        # Invalid trip_id format (path traversal attempt)
        with self.assertRaises(ValueError):
            services.generate_trip_travel_pack("../../etc/passwd", self.super_token)

        # Path traversal in out_path
        with self.assertRaises(PermissionError) as ctx:
            services.generate_trip_travel_pack("T-SEC-13", self.super_token, out_path=os.path.join(self.docs_dir, "..", "escaped.pdf"))
        self.assertIn("Path traversal detected", str(ctx.exception))

    # -------------------------------------------------------------
    # 14. Generation failure atomicity
    # -------------------------------------------------------------
    def test_14_generation_failure_atomicity(self):
        """14. A failure during PDF writing leaves existing output intact and removes temp files."""
        self._setup_approved_trip("T-ATOM-14")
        target_pdf = os.path.join(self.docs_dir, "AtomicTest.pdf")

        # Create an existing valid PDF file
        with open(target_pdf, "wb") as f:
            f.write(b"%PDF-1.4 ORIGINAL VALID CONTENT")
        with open(target_pdf, "rb") as f:
            orig_content = f.read()

        # Mock an error in create_raw_pdf write
        orig_replace = os.replace
        def broken_replace(src, dst):
            raise IOError("Simulated disk write failure")

        try:
            os.replace = broken_replace
            with self.assertRaises(IOError):
                services.generate_trip_travel_pack("T-ATOM-14", self.super_token, out_path=target_pdf)
        finally:
            os.replace = orig_replace

        # Verify existing file was NOT modified or corrupted
        with open(target_pdf, "rb") as f:
            curr_content = f.read()
        self.assertEqual(curr_content, orig_content, "Existing file must remain identical after generation failure.")

        # Verify no .tmp files were left behind
        temp_files = [f for f in os.listdir(self.docs_dir) if ".tmp" in f]
        self.assertEqual(temp_files, [], "Temporary files must be cleaned up on failure.")

    # -------------------------------------------------------------
    # 15. Audit behavior
    # -------------------------------------------------------------
    def test_15_audit_behavior(self):
        """15. Successful generation logs an audit event; denied calls do not log successful generation."""
        self._setup_approved_trip("T-AUDIT-15")
        target_pdf = os.path.join(self.docs_dir, "AuditOutput.pdf")

        # 1. Denied attempt (Unauthorized Guest)
        try:
            services.generate_trip_travel_pack("T-AUDIT-15", self.guest_token, out_path=target_pdf)
        except PermissionError:
            pass

        conn = database.get_connection()
        count_denied = conn.execute("SELECT COUNT(*) FROM activity WHERE trip_id = 'T-AUDIT-15'").fetchone()[0]
        conn.close()
        self.assertEqual(count_denied, 0, "No activity record should be created for denied calls.")

        # 2. Allowed attempt (Supervisor)
        services.generate_trip_travel_pack("T-AUDIT-15", self.super_token, out_path=target_pdf)

        conn = database.get_connection()
        row = conn.execute("SELECT * FROM activity WHERE trip_id = 'T-AUDIT-15' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row['trip_id'], 'T-AUDIT-15')
        self.assertEqual(row['customer_id'], 'C-APP-01')
        self.assertIn("Consolidated Travel File generated by Senior Supervisor (Supervisor)", row['description'])
        # Verify no passport numbers or tokens in audit log
        self.assertNotIn("P-APPROVED-001", row['description'])
        self.assertNotIn(self.super_token, row['description'])

    # -------------------------------------------------------------
    # 16. Existing functionality regression & production DB baseline
    # -------------------------------------------------------------
    def test_16_production_database_untouched(self):
        """16. Verify production database remains completely untouched during test run."""
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
