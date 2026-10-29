"""
Khanna Travels Vault V3 - Phase 12B-1
Unit Test Suite for Document Parser Corrections & MRZ Reconciliation
"""

import os
import sys
import hashlib
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import document_processor

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

EXPECTED_PROD_DB_SIZE = 167936
EXPECTED_PROD_DB_SHA256 = "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d"
EXPECTED_DOC_COUNT = 74


class TestPhase12b1ParserFixes(unittest.TestCase):
    """Test suite for parser corrections in document_processor.py."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if not f.startswith(".")])

    def test_01_passport_split_surname_given_names_combination(self):
        """01. Verify separate Surname and Given Names are combined into Full Name."""
        text = """
        DEMO PASSPORT
        Surname: MALHOTRA
        Given Names: VIKRAM
        Passport Number: V9876543
        Date of Birth: 14 Aug 1988
        Nationality: INDIAN
        Date of Expiry: 09 Jan 2031
        """
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            text, expected_requirement="Passport"
        )
        self.assertEqual(doc_type, "Passport")
        self.assertEqual(data["Full Name"], "VIKRAM MALHOTRA")
        self.assertEqual(conf["Full Name"], "high")
        self.assertEqual(data["Passport Number"], "V9876543")

    def test_02_passport_parent_and_spouse_names_ignored(self):
        """02. Verify Father/Mother/Spouse lines are ignored and do not pollute traveller name."""
        text = """
        PASSPORT
        Surname: MALHOTRA
        Given Names: VIKRAM
        Father's Name: HARISH MALHOTRA
        Mother's Name: SUNITA MALHOTRA
        Spouse's Name: PRIYA MALHOTRA
        Passport Number: V9876543
        """
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Passport"
        )
        self.assertEqual(data["Full Name"], "VIKRAM MALHOTRA")
        self.assertNotIn("HARISH", data["Full Name"])
        self.assertNotIn("PRIYA", data["Full Name"])

    def test_03_visa_compound_labels_cleaning(self):
        """03. Verify Visa compound slash labels are cleanly stripped."""
        text = """
        DEMO VISA / ENTRY DOCUMENT
        Traveller Name: Vikram Malhotra
        Visa Number / Reference: DXB-VISA-2026-991
        Destination: Dubai, UAE
        Purpose of Visit: Tourist
        Issue Date: 01 Nov 2026
        Expiry Date / Valid Until: 31 Dec 2026
        """
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Visa / Entry Document"
        )
        self.assertEqual(doc_type, "Visa / Entry Document")
        self.assertEqual(data["Traveller Name"], "Vikram Malhotra")
        self.assertEqual(data["Visa Number / Reference"], "DXB-VISA-2026-991")
        self.assertEqual(data["Expiry Date / Valid Until"], "31 Dec 2026")
        self.assertEqual(conf["Visa Number / Reference"], "high")
        self.assertEqual(conf["Expiry Date / Valid Until"], "high")

    def test_04_visa_alternate_compound_labels(self):
        """04. Verify alternate compound label variations (Valid Until / Expiry Date)."""
        text = """
        VISA / ENTRY DOCUMENT
        Traveller Name: Amit Mehta
        Visa No. / Ref: SING-VISA-8821
        Valid Until / Expiry Date: 20 Jan 2027
        """
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Visa / Entry Document"
        )
        self.assertEqual(data["Visa Number / Reference"], "SING-VISA-8821")
        self.assertEqual(data["Expiry Date / Valid Until"], "20 Jan 2027")

    def test_05_insurance_certificate_heading_collision_prevented(self):
        """05. Verify 'CERTIFICATE OF TRAVEL INSURANCE' title does not pollute Policy Number."""
        text = """
        CERTIFICATE OF TRAVEL INSURANCE
        Insured Name: Vikram Malhotra
        Policy Number: POL-TRAVEL-2026-774
        Insurance Provider: Tata AIG General Insurance
        Valid From: 12 Dec 2026
        Valid Until: 19 Dec 2026
        """
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Travel Insurance"
        )
        self.assertEqual(doc_type, "Travel Insurance")
        self.assertEqual(data["Insured Name"], "Vikram Malhotra")
        self.assertEqual(data["Policy Number"], "POL-TRAVEL-2026-774")
        self.assertNotEqual(data["Policy Number"], "TRAVEL")
        self.assertEqual(conf["Policy Number"], "high")

    def test_06_passport_mrz_reconciliation_agreement(self):
        """06. Verify VIZ and MRZ agreement yields high confidence."""
        text = """
        PASSPORT
        Surname: MALHOTRA
        Given Names: VIKRAM
        Passport Number: V9876543
        Date of Birth: 14 Aug 1988
        Nationality: INDIAN
        Date of Expiry: 09 Jan 2031
        P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<
        V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04
        """
        warnings = []
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Passport", warnings_list=warnings
        )
        self.assertEqual(data["Full Name"], "VIKRAM MALHOTRA")
        self.assertEqual(data["Passport Number"], "V9876543")
        self.assertEqual(conf["Full Name"], "high")
        self.assertEqual(conf["Passport Number"], "high")

    def test_07_passport_mrz_populates_missing_viz_field(self):
        """07. Verify MRZ populates fields missing in the VIZ."""
        # VIZ only has name and country, no passport number or DOB
        text = """
        PASSPORT
        Full Name: ANNA MARIA ERIKSSON
        Country: UTOPIA
        P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<
        L898902C36UTO7408122F1204159ZE184226B<<<<<10
        """
        warnings = []
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Passport", warnings_list=warnings
        )
        self.assertEqual(data["Full Name"], "ANNA MARIA ERIKSSON")
        # Populated from MRZ
        self.assertEqual(data["Passport Number"], "L898902C3")
        self.assertEqual(data["Date of Birth"], "12 Aug 1974")
        self.assertEqual(data["Expiry Date"], "15 Apr 2012")
        self.assertEqual(data["Nationality"], "UTO")

    def test_08_passport_mrz_conflict_preserves_viz_and_logs_warning(self):
        """08. Verify VIZ/MRZ conflict never silently overwrites; logs warning for human review."""
        text = """
        PASSPORT
        Surname: SHARMA
        Given Names: RAHUL
        Passport Number: S1122334
        P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<
        V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04
        """
        warnings = []
        data, conf, doc_type, _ = document_processor.parse_passport_text(
            text, expected_requirement="Passport", warnings_list=warnings
        )
        # VIZ value must be strictly preserved
        self.assertEqual(data["Full Name"], "RAHUL SHARMA")
        self.assertEqual(data["Passport Number"], "S1122334")
        # Warnings must flag the conflict
        self.assertTrue(any("Passport name conflict" in w for w in warnings))
        self.assertTrue(any("Passport number conflict" in w for w in warnings))

    def test_09_production_database_and_documents_untouched(self):
        """09. Verify production database and document store remain completely bit-for-bit unchanged."""
        self.assertTrue(os.path.exists(PROD_DB_PATH), "Production DB not found!")
        self.assertEqual(os.path.getsize(PROD_DB_PATH), self.initial_prod_db_size, "Production DB size changed during test run!")
        with open(PROD_DB_PATH, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(h, self.initial_prod_db_sha256, "Production DB SHA-256 changed during test run!")

        files = [f for f in os.listdir(PROD_DOCS_DIR) if not f.startswith(".")]
        self.assertEqual(len(files), self.initial_doc_count, "Document store count changed during test run!")
        conn = self.sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
