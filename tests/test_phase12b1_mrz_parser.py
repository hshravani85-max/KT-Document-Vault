"""
Khanna Travels Vault V3 - Phase 12B-1
Unit Test Suite for Standalone TD3 Passport MRZ Parser (mrz_parser.py)
"""

import os
import sys
import hashlib
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import mrz_parser

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

EXPECTED_PROD_DB_SIZE = 167936
EXPECTED_PROD_DB_SHA256 = "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d"
EXPECTED_DOC_COUNT = 74


class TestPhase12b1MrzParser(unittest.TestCase):
    """Test suite for ICAO Doc 9303 TD3 MRZ parser and check-digit validator."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if not f.startswith(".")])

    def test_01_check_digit_calculation(self):
        """01. Verify 7-3-1 weighting algorithm on known characters and filler."""
        # 'A' = 10 -> 10 * 7 = 70 % 10 = 0
        self.assertEqual(mrz_parser.calculate_check_digit("A"), "0")
        # '9' = 9 -> 9 * 7 = 63 % 10 = 3
        self.assertEqual(mrz_parser.calculate_check_digit("9"), "3")
        # '<' = 0
        self.assertEqual(mrz_parser.calculate_check_digit("<"), "0")
        # Empty or non-string
        self.assertEqual(mrz_parser.calculate_check_digit(""), "")
        self.assertEqual(mrz_parser.calculate_check_digit(None), "")

        # Official ICAO Doc 9303 test vector: doc number 'L898902C3' -> 6
        self.assertEqual(mrz_parser.calculate_check_digit("L898902C3"), "6")
        self.assertTrue(mrz_parser.validate_check_digit("L898902C3", "6"))
        self.assertFalse(mrz_parser.validate_check_digit("L898902C3", "7"))

    def test_02_icao_official_sample_anna_maria_eriksson(self):
        """02. Verify official ICAO Doc 9303 Part 4 reference sample."""
        l1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
        l2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
        mrz_text = f"{l1}\n{l2}"

        res = mrz_parser.parse_td3_mrz(mrz_text)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "VALIDATED")
        self.assertEqual(len(res["errors"]), 0)
        self.assertEqual(len(res["warnings"]), 0)

        fields = res["fields"]
        self.assertEqual(fields["document_code"], "P")
        self.assertEqual(fields["issuing_state"], "UTO")
        self.assertEqual(fields["surname"], "ERIKSSON")
        self.assertEqual(fields["given_names"], "ANNA MARIA")
        self.assertEqual(fields["full_name"], "ANNA MARIA ERIKSSON")
        self.assertEqual(fields["document_number"], "L898902C3")
        self.assertEqual(fields["nationality"], "UTO")
        self.assertEqual(fields["dob_raw"], "740812")
        self.assertEqual(fields["dob_iso"], "1974-08-12")
        self.assertEqual(fields["dob_formatted"], "12 Aug 1974")
        self.assertEqual(fields["sex"], "F")
        self.assertEqual(fields["expiry_raw"], "120415")
        self.assertEqual(fields["expiry_iso"], "2012-04-15")
        self.assertEqual(fields["expiry_formatted"], "15 Apr 2012")
        self.assertEqual(fields["optional_data"], "ZE184226B")

        # Verify all check digits reported valid
        cd = res["check_digits"]
        self.assertTrue(cd["document_number"]["valid"])
        self.assertTrue(cd["date_of_birth"]["valid"])
        self.assertTrue(cd["expiry_date"]["valid"])
        self.assertTrue(cd["optional_data"]["valid"])
        self.assertTrue(cd["composite"]["valid"])

    def test_03_fully_valid_indian_passport(self):
        """03. Verify mathematically verified Indian passport MRZ."""
        doc_raw = "V9876543<"
        doc_chk = mrz_parser.calculate_check_digit(doc_raw)  # '1'
        dob_raw = "880814"
        dob_chk = mrz_parser.calculate_check_digit(dob_raw)  # '3'
        exp_raw = "310109"
        exp_chk = mrz_parser.calculate_check_digit(exp_raw)  # '0'
        opt_raw = "<<<<<<<<<<<<<<"
        opt_chk = "0"
        comp_payload = f"{doc_raw}{doc_chk}{dob_raw}{dob_chk}{exp_raw}{exp_chk}{opt_raw}{opt_chk}"
        comp_chk = mrz_parser.calculate_check_digit(comp_payload)  # '0'

        l1 = "P<INDMALHOTRA<<VIKRAM" + ("<" * 23)
        l2 = f"{doc_raw}{doc_chk}IND{dob_raw}{dob_chk}M{exp_raw}{exp_chk}{opt_raw}{opt_chk}{comp_chk}"

        res = mrz_parser.parse_td3_mrz(f"{l1}\n{l2}")
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "VALIDATED")
        self.assertEqual(res["fields"]["full_name"], "VIKRAM MALHOTRA")
        self.assertEqual(res["fields"]["document_number"], "V9876543")
        self.assertEqual(res["fields"]["nationality"], "IND")
        self.assertEqual(res["fields"]["dob_formatted"], "14 Aug 1988")
        self.assertEqual(res["fields"]["expiry_formatted"], "09 Jan 2031")

    def test_04_partially_valid_synthetic_mrz(self):
        """04. Verify handling of synthetic MRZ where composite check is valid but individual check digit is off."""
        l1 = "P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<"
        l2 = "V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04"
        res = mrz_parser.parse_td3_mrz(f"{l1}\n{l2}")

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "PARTIALLY_VALIDATED")
        self.assertGreater(len(res["warnings"]), 0)
        self.assertEqual(res["fields"]["full_name"], "VIKRAM MALHOTRA")
        self.assertEqual(res["fields"]["document_number"], "V9876543")
        self.assertEqual(res["fields"]["dob_formatted"], "14 Aug 1988")
        self.assertEqual(res["fields"]["expiry_formatted"], "09 Jan 2031")

    def test_05_invalid_mrz_corrupted_characters(self):
        """05. Verify that MRZ with completely invalid checksums is classified as INVALID."""
        l1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
        # Alter all check digits and characters including composite check
        l2 = "L898902C39UTO7408129F1204158ZE184226B<<<<<90"
        res = mrz_parser.parse_td3_mrz(f"{l1}\n{l2}")

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "INVALID")
        self.assertGreater(len(res["warnings"]), 0)

    def test_06_mrz_not_found(self):
        """06. Verify handling of documents without MRZ."""
        plain_text = "This is a flight ticket for Vikram Malhotra with no MRZ lines."
        res = mrz_parser.parse_td3_mrz(plain_text)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "NOT_FOUND")
        self.assertIn("No valid TD3 44-character MRZ lines detected.", res["errors"])

    def test_07_century_resolution_logic(self):
        """07. Verify century resolution for dates."""
        # Reference year 2026:
        # DOB: 88 -> 1988 (> 26), 15 -> 2015 (<= 26)
        iso_dob1, fmt_dob1, _ = mrz_parser.parse_mrz_date("880814", is_dob=True, reference_year=2026)
        self.assertEqual(iso_dob1, "1988-08-14")
        self.assertEqual(fmt_dob1, "14 Aug 1988")

        iso_dob2, fmt_dob2, _ = mrz_parser.parse_mrz_date("150320", is_dob=True, reference_year=2026)
        self.assertEqual(iso_dob2, "2015-03-20")
        self.assertEqual(fmt_dob2, "20 Mar 2015")

        # Expiry: 31 -> 2031 (< 80), 85 -> 1985 (>= 80)
        iso_exp1, fmt_exp1, _ = mrz_parser.parse_mrz_date("310109", is_dob=False, reference_year=2026)
        self.assertEqual(iso_exp1, "2031-01-09")
        self.assertEqual(fmt_exp1, "09 Jan 2031")

        iso_exp2, fmt_exp2, _ = mrz_parser.parse_mrz_date("850510", is_dob=False, reference_year=2026)
        self.assertEqual(iso_exp2, "1985-05-10")
        self.assertEqual(fmt_exp2, "10 May 1985")

    def test_08_name_handling_variations(self):
        """08. Verify name handling for single surname, multiple given names, and fillers."""
        # Single surname only (no given name)
        l1_single = "P<INDKAPOOR" + ("<" * 33)
        l2_dummy = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
        res_single = mrz_parser.parse_td3_mrz(f"{l1_single}\n{l2_dummy}")
        self.assertEqual(res_single["fields"]["surname"], "KAPOOR")
        self.assertEqual(res_single["fields"]["given_names"], "")
        self.assertEqual(res_single["fields"]["full_name"], "KAPOOR")

        # Multiple given names: "MALHOTRA<<VIKRAM<KUMAR"
        l1_multi = "P<INDMALHOTRA<<VIKRAM<KUMAR" + ("<" * 17)
        res_multi = mrz_parser.parse_td3_mrz(f"{l1_multi}\n{l2_dummy}")
        self.assertEqual(res_multi["fields"]["surname"], "MALHOTRA")
        self.assertEqual(res_multi["fields"]["given_names"], "VIKRAM KUMAR")
        self.assertEqual(res_multi["fields"]["full_name"], "VIKRAM KUMAR MALHOTRA")

    def test_09_embedded_mrz_in_noisy_page(self):
        """09. Verify extraction of MRZ from multiline noisy passport page text."""
        doc_text = """
        GOVERNMENT OF INDIA / PASSPORT
        Type: P  Country Code: IND  Passport No: V9876543
        Surname: MALHOTRA
        Given Name: VIKRAM
        Nationality: INDIAN  Sex: M  Date of Birth: 14/08/1988
        Place of Issue: DELHI  Date of Expiry: 09/01/2031
        
        P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<
        V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04
        
        End of Document. All Rights Reserved.
        """
        res = mrz_parser.parse_td3_mrz(doc_text)
        self.assertTrue(res["success"])
        self.assertEqual(res["fields"]["full_name"], "VIKRAM MALHOTRA")
        self.assertEqual(res["fields"]["document_number"], "V9876543")

    def test_10_production_database_and_documents_untouched(self):
        """10. Verify production database and document store remain completely bit-for-bit unchanged."""
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
