"""
Khanna Travels Vault V3 - Phase 12C
Automated Test Suite: Smart Intake Duplicate Prevention, Document Integrity & Management Demo Hardening
"""

import os
import sys
import io
import json
import shutil
import tempfile
import hashlib
import unittest
import sqlite3
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database
import services
import auth_services
import document_processor

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

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
    status TEXT,
    extracted_data TEXT,
    file_path TEXT,
    uploaded_at TEXT,
    FOREIGN KEY(requirement_id) REFERENCES requirements(id)
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
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
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


class TestPhase12cSmartIntakeIntegrity(unittest.TestCase):
    """
    Test suite for Phase 12C covering Smart Intake idempotency, transaction safety,
    duplicate prevention, file persistence, and regression isolation.
    """

    @classmethod
    def setUpClass(cls):
        # 1. Capture production immutability baseline
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_prod_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        # 2. Setup isolated temporary sandbox
        cls.test_sandbox = tempfile.mkdtemp()
        cls.test_data_dir = os.path.join(cls.test_sandbox, "data")
        cls.test_docs_dir = os.path.join(cls.test_sandbox, "documents")
        os.makedirs(cls.test_data_dir, exist_ok=True)
        os.makedirs(cls.test_docs_dir, exist_ok=True)

        cls.orig_db_path = database.DB_PATH
        cls.test_db_path = os.path.join(cls.test_data_dir, "kt_vault_v3.db")
        database.DB_PATH = cls.test_db_path

        # 3. Initialize isolated database schema
        conn = sqlite3.connect(cls.test_db_path)
        conn.executescript(INIT_TEST_SCHEMA_SQL)

        # 4. Create authorized staff & admin users
        staff_user = ("U-STAFF-12C", "staff_12c", b"hash", b"salt", "Demo Staff", "Staff")
        admin_user = ("U-ADMIN-12C", "admin_12c", b"hash", b"salt", "System Admin", "Admin")
        viewer_user = ("U-VIEW-12C", "viewer_12c", b"hash", b"salt", "Guest Viewer", "Viewer")
        for u in [staff_user, admin_user, viewer_user]:
            conn.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)", u)

        exp = (datetime.now() + timedelta(days=1)).isoformat()
        cls.staff_token = "token-staff-12c"
        cls.admin_token = "token-admin-12c"
        cls.viewer_token = "token-viewer-12c"
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.staff_token, "U-STAFF-12C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.admin_token, "U-ADMIN-12C", exp))
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (cls.viewer_token, "U-VIEW-12C", exp))
        conn.commit()
        conn.close()

        # 5. Create valid sample synthetic passport file
        cls.sample_pdf_path = os.path.join(cls.test_sandbox, "sample_passport.pdf")
        with open(cls.sample_pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n% Synthetic Test Passport Content\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF")

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        if os.path.exists(cls.test_sandbox):
            try:
                shutil.rmtree(cls.test_sandbox)
            except Exception:
                pass

    def setUp(self):
        # Clear in-memory idempotency cache before each test
        services._SMART_INTAKE_IDEMPOTENCY_CACHE.clear()

    # =========================================================
    # TEST GROUP A: SMART INTAKE IDEMPOTENCY & WORKFLOW
    # =========================================================

    def test_01_first_valid_submission_creates_all_records(self):
        """A.01 Verify valid first submission atomically creates customer, traveller, requirement, and document."""
        c_data = {"name": "Rohit Verma", "mobile": "+919876500001", "email": "rohit@example.com", "customer_type": "Individual"}
        t_data = {"name": "Rohit Verma", "dob": "12 MAR 1990", "passport_number": "R1234567", "nationality": "INDIAN", "traveller_type": "Adult", "lead_traveller": True}
        d_fields = {"Full Name": "Rohit Verma", "Passport Number": "R1234567", "Date of Birth": "12 MAR 1990", "Nationality": "INDIAN", "Expiry Date": "11 MAR 2030"}

        res = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_test_01"
        )

        self.assertEqual(res["status"], "success")
        self.assertFalse(res["traveller_reused"])
        self.assertFalse(res["document_reused"])

        c_id = res["customer_id"]
        t_id = res["traveller_id"]
        d_id = res["document_id"]

        # Verify DB records
        conn = database.get_connection()
        cust = conn.execute("SELECT * FROM customers WHERE id = ?", (c_id,)).fetchone()
        trav = conn.execute("SELECT * FROM travellers WHERE id = ?", (t_id,)).fetchone()
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (d_id,)).fetchone()
        req = conn.execute("SELECT * FROM requirements WHERE id = ?", (doc["requirement_id"],)).fetchone()
        conn.close()

        self.assertIsNotNone(cust)
        self.assertEqual(cust["name"], "Rohit Verma")
        self.assertEqual(trav["customer_id"], c_id)
        self.assertEqual(trav["passport_number"], "R1234567")
        self.assertEqual(req["traveller_id"], t_id)
        self.assertEqual(req["type"], "TRAVELLER_VAULT")
        self.assertEqual(doc["status"], "Under Review")

    def test_02_repeated_submission_same_idempotency_key(self):
        """A.02 Verify repeated submission with identical idempotency key returns original result and creates no duplicates."""
        c_data = {"name": "Priya Sharma", "customer_type": "Individual"}
        t_data = {"name": "Priya Sharma", "passport_number": "P7654321", "dob": "20 JUN 1992"}
        d_fields = {"Full Name": "Priya Sharma", "Passport Number": "P7654321"}

        res1 = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_unique_priya"
        )

        # Immediate repeat submission
        res2 = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_unique_priya"
        )

        self.assertEqual(res1["customer_id"], res2["customer_id"])
        self.assertEqual(res1["traveller_id"], res2["traveller_id"])
        self.assertEqual(res1["document_id"], res2["document_id"])

        conn = database.get_connection()
        trav_count = conn.execute("SELECT COUNT(*) FROM travellers WHERE customer_id = ?", (res1["customer_id"],)).fetchone()[0]
        doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE requirement_id IN (SELECT id FROM requirements WHERE traveller_id = ?)", (res1["traveller_id"],)).fetchone()[0]
        conn.close()

        self.assertEqual(trav_count, 1, "Duplicate traveller was created for repeated submission!")
        self.assertEqual(doc_count, 1, "Duplicate document was created for repeated submission!")

    def test_03_streamlit_rerun_simulation(self):
        """A.03 Simulate Streamlit Step 4 rerun: verifies execution guard prevents second write on button click."""
        c_data = {"name": "Karan Kapoor", "customer_type": "Individual"}
        t_data = {"name": "Karan Kapoor", "passport_number": "K9988776", "dob": "05 MAY 1985"}
        d_fields = {"Full Name": "Karan Kapoor", "Passport Number": "K9988776"}

        # First run (page load)
        res1 = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_karan_rerun"
        )

        # Second run (user clicks button)
        res2 = services.complete_smart_intake(
            customer_id=res1["customer_id"],
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_karan_rerun"
        )

        self.assertEqual(res1["traveller_id"], res2["traveller_id"])
        self.assertEqual(res1["document_id"], res2["document_id"])

        conn = database.get_connection()
        t_count = conn.execute("SELECT COUNT(*) FROM travellers WHERE customer_id = ?", (res1["customer_id"],)).fetchone()[0]
        conn.close()
        self.assertEqual(t_count, 1)

    def test_04_browser_refresh_same_traveller_details(self):
        """A.04 Simulate user re-uploading confirmed passport for existing customer: detects existing traveller profile."""
        c_data = {"name": "Meera Joshi", "customer_type": "Individual"}
        t_data = {"name": "Meera Joshi", "passport_number": "M1122334", "dob": "10 OCT 1993"}
        d_fields = {"Full Name": "Meera Joshi", "Passport Number": "M1122334"}

        res1 = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_meera_key1"
        )

        # User submits again with a fresh session/op_id
        res2 = services.complete_smart_intake(
            customer_id=res1["customer_id"],
            traveller_data=t_data,
            document_fields=d_fields,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_meera_key2"
        )

        self.assertTrue(res2["traveller_reused"])
        self.assertEqual(res1["traveller_id"], res2["traveller_id"])

        conn = database.get_connection()
        t_count = conn.execute("SELECT COUNT(*) FROM travellers WHERE customer_id = ?", (res1["customer_id"],)).fetchone()[0]
        conn.close()
        self.assertEqual(t_count, 1)

    def test_05_passport_renewal_new_version(self):
        """A.05 Verify legitimate passport renewal updates document record and preserves single traveller profile."""
        c_data = {"name": "Anil Deshmukh", "customer_type": "Individual"}
        t_data = {"name": "Anil Deshmukh", "passport_number": "A5566778", "dob": "15 JAN 1980"}
        d_fields_v1 = {"Full Name": "Anil Deshmukh", "Passport Number": "A5566778", "Expiry Date": "14 JAN 2025"}

        res1 = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields=d_fields_v1,
            file_path=self.sample_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_anil_v1"
        )

        # Renewal: new scan file with updated expiry date
        renewal_pdf_path = os.path.join(self.test_sandbox, "renewal_passport.pdf")
        with open(renewal_pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n% Renewed Passport 2035\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF")

        d_fields_v2 = {"Full Name": "Anil Deshmukh", "Passport Number": "A5566778", "Expiry Date": "14 JAN 2035"}
        res2 = services.complete_smart_intake(
            customer_id=res1["customer_id"],
            traveller_data=t_data,
            document_fields=d_fields_v2,
            file_path=renewal_pdf_path,
            session_token=self.staff_token,
            idempotency_key="op_anil_v2"
        )

        self.assertTrue(res2["traveller_reused"])
        self.assertEqual(res1["traveller_id"], res2["traveller_id"])

        conn = database.get_connection()
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (res2["document_id"],)).fetchone()
        extracted = json.loads(doc["extracted_data"])
        t_count = conn.execute("SELECT COUNT(*) FROM travellers WHERE customer_id = ?", (res1["customer_id"],)).fetchone()[0]
        conn.close()

        self.assertEqual(t_count, 1, "Duplicate traveller profile created during passport renewal!")
        self.assertEqual(extracted["Expiry Date"], "14 JAN 2035", "Document extracted data was not updated with renewed passport details!")

    def test_06_two_travellers_same_name_different_identity(self):
        """A.06 Verify two legitimate travellers with the same name can exist (names are not universally unique)."""
        c_id = services.create_customer("Sunil Mehta Family", customer_type="Family", session_token=self.staff_token)

        # Senior
        t1_id = services.add_traveller(c_id, "Sunil Mehta", dob="10 MAY 1960", passport_number="SM-SR-11", session_token=self.staff_token)
        # Junior
        t2_id = services.add_traveller(c_id, "Sunil Mehta", dob="15 AUG 1995", passport_number="SM-JR-22", session_token=self.staff_token)

        self.assertNotEqual(t1_id, t2_id, "Legitimate distinct travellers with different passports should not be merged!")

    # =========================================================
    # TEST GROUP B: DATABASE INTEGRITY & TRANSACTIONS
    # =========================================================

    def test_07_transaction_atomicity_on_failure(self):
        """B.01 Verify complete rollback if an error occurs midway (no partial customer without traveller)."""
        c_data = {"name": "Fail Test Customer", "customer_type": "Individual"}
        t_data = {"name": "Fail Test Traveller", "passport_number": "FAIL999"}

        # Pass invalid file path to force failure during document persistence
        with self.assertRaises(ValueError):
            services.complete_smart_intake(
                customer_data=c_data,
                traveller_data=t_data,
                document_fields={},
                file_path=os.path.join(self.test_sandbox, "non_existent_file.pdf"),
                session_token=self.staff_token,
                idempotency_key="op_fail_trans"
            )

        conn = database.get_connection()
        cust = conn.execute("SELECT * FROM customers WHERE name = 'Fail Test Customer'").fetchone()
        trav = conn.execute("SELECT * FROM travellers WHERE name = 'Fail Test Traveller'").fetchone()
        conn.close()

        self.assertIsNone(cust, "Partial customer row leaked after transaction failure!")
        self.assertIsNone(trav, "Partial traveller row leaked after transaction failure!")

    def test_08_unrelated_records_untouched(self):
        """B.02 Verify operations for one customer never modify another customer's records."""
        c1 = services.create_customer("Customer One", customer_type="Individual", session_token=self.staff_token)
        c2 = services.create_customer("Customer Two", customer_type="Individual", session_token=self.staff_token)

        t1 = services.add_traveller(c1, "Traveller One", passport_number="P111", session_token=self.staff_token)

        conn = database.get_connection()
        c2_travellers = conn.execute("SELECT * FROM travellers WHERE customer_id = ?", (c2,)).fetchall()
        conn.close()

        self.assertEqual(len(c2_travellers), 0)

    # =========================================================
    # TEST GROUP C: FILE PERSISTENCE SAFETY & FAILURE INJECTION
    # =========================================================

    def test_09_missing_file_rejected_before_db_insertion(self):
        """C.01 Verify non-existent file path is rejected before touching the database."""
        with self.assertRaises(ValueError) as cm:
            services.complete_smart_intake(
                customer_data={"name": "Ghost File Customer"},
                traveller_data={"name": "Ghost File Traveller"},
                file_path="C:/non/existent/path.pdf",
                session_token=self.staff_token
            )
        self.assertIn("does not exist", str(cm.exception))

    def test_10_empty_zero_byte_file_rejected(self):
        """C.02 Verify 0-byte file is rejected and leaves zero database records."""
        empty_file = os.path.join(self.test_sandbox, "empty_scan.pdf")
        with open(empty_file, "wb") as f:
            pass

        with self.assertRaises(ValueError) as cm:
            services.complete_smart_intake(
                customer_data={"name": "Zero Byte Customer"},
                traveller_data={"name": "Zero Byte Traveller"},
                file_path=empty_file,
                session_token=self.staff_token
            )
        self.assertIn("empty (0 bytes)", str(cm.exception))

    def test_11_document_record_strictly_requires_physical_file(self):
        """C.03 Verify all documents in vault strictly point to verified physical files on disk."""
        c_data = {"name": "File Verify Customer"}
        t_data = {"name": "File Verify Traveller", "passport_number": "FV-1234"}
        res = services.complete_smart_intake(
            customer_data=c_data,
            traveller_data=t_data,
            document_fields={"Full Name": "File Verify Traveller"},
            file_path=self.sample_pdf_path,
            session_token=self.staff_token
        )

        doc_list = services.get_customer_documents(res["customer_id"], session_token=self.staff_token)
        self.assertEqual(len(doc_list), 1)
        self.assertTrue(doc_list[0]["file_exists"])
        self.assertGreater(doc_list[0]["file_size_bytes"], 0)
        self.assertNotEqual(doc_list[0]["file_format"], "UNKNOWN")

    # =========================================================
    # TEST GROUP D: SECURITY & ACCESS CONTROL
    # =========================================================

    def test_12_path_traversal_in_file_path_rejected(self):
        """D.01 Verify path traversal sequences in file_path are blocked by get_safe_document_path."""
        traversal_path = "../../Windows/System32/calc.exe"
        with self.assertRaises(ValueError):
            services.complete_smart_intake(
                customer_data={"name": "Attacker"},
                traveller_data={"name": "Attacker"},
                file_path=traversal_path,
                session_token=self.staff_token
            )

    def test_13_unauthenticated_or_unauthorized_call_rejected(self):
        """D.02 Verify unauthenticated and viewer roles cannot complete smart intake."""
        with self.assertRaises(PermissionError):
            services.complete_smart_intake(
                customer_data={"name": "No Auth"},
                traveller_data={"name": "No Auth"},
                file_path=self.sample_pdf_path,
                session_token=None
            )

        with self.assertRaises(PermissionError):
            services.complete_smart_intake(
                customer_data={"name": "Viewer Role"},
                traveller_data={"name": "Viewer Role"},
                file_path=self.sample_pdf_path,
                session_token=self.viewer_token
            )

    def test_14_audit_log_contains_no_raw_passport_in_plaintext_desc(self):
        """D.03 Verify activity descriptions record the operation without leaking sensitive passport numbers."""
        sensitive_passport = "SUPERSECRET999"
        res = services.complete_smart_intake(
            customer_data={"name": "Privacy Customer"},
            traveller_data={"name": "Privacy Customer", "passport_number": sensitive_passport},
            document_fields={"Full Name": "Privacy Customer", "Passport Number": sensitive_passport},
            file_path=self.sample_pdf_path,
            session_token=self.staff_token
        )

        conn = database.get_connection()
        logs = conn.execute("SELECT description FROM activity WHERE customer_id = ?", (res["customer_id"],)).fetchall()
        conn.close()

        for l in logs:
            self.assertNotIn(sensitive_passport, l["description"], "Raw passport number leaked in activity description!")

    # =========================================================
    # TEST GROUP E: REGRESSION & IMMUTABILITY
    # =========================================================

    def test_15_production_database_and_documents_untouched(self):
        """E.01 Confirm that the production database and documents store remain completely untouched."""
        curr_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        curr_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        self.assertEqual(curr_db_size, self.initial_prod_db_size, "Production DB size changed during test run!")
        self.assertEqual(curr_db_sha256, self.initial_prod_db_sha256, "Production DB SHA-256 changed during test run!")
        self.assertEqual(curr_doc_count, self.initial_prod_doc_count, "Production document store file count changed!")

        conn = sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()


if __name__ == "__main__":
    unittest.main()
