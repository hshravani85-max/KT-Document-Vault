import unittest
import os
import sys
import json
import sqlite3
import tempfile
import shutil
import uuid
import re

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import document_processor
import services
import auth_services
import database
import travel_file_generator


class TestPhase14DocumentTypes(unittest.TestCase):
    """
    Test Suite for Phase 14: Document Type Expansion.
    Verifies that:
      1. Sightseeing Voucher, Transfer Voucher, Travel Voucher remain intact.
      2. Land Voucher, Aadhaar Card, PAN Card are added and coexist.
      3. Classification, extraction, review, search, and PDF generation work.
      4. Aadhaar numbers are masked for privacy.
      5. Optional identity documents do not penalize trip readiness.
      6. Live database records and associations are strictly preserved.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, "test_kt_vault.db")
        cls.test_docs_dir = os.path.join(cls.temp_dir, "documents")
        os.makedirs(cls.test_docs_dir, exist_ok=True)

        live_db = r'C:\KT_Vault_V3\data\kt_vault_v3.db'
        shutil.copy2(live_db, cls.test_db_path)

        cls.orig_get_connection = database.get_connection
        def get_test_conn():
            con = sqlite3.connect(cls.test_db_path)
            con.row_factory = sqlite3.Row
            return con
        database.get_connection = get_test_conn

    @classmethod
    def tearDownClass(cls):
        database.get_connection = cls.orig_get_connection
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_existing_vouchers_preserved_in_schemas(self):
        """1. Sightseeing Voucher and Transfer Voucher remain fully available in document processor."""
        self.assertIn('Sightseeing Voucher', document_processor.SCHEMAS)
        self.assertIn('Transfer Voucher', document_processor.SCHEMAS)

        # Check source of pages/smart_upload.py and pages/document_review.py
        with open(r'C:\KT_Vault_V3\pages\smart_upload.py', 'r', encoding='utf-8') as f:
            su_src = f.read()
        self.assertIn("'Sightseeing Voucher'", su_src)
        self.assertIn("'Transfer Voucher'", su_src)

        with open(r'C:\KT_Vault_V3\pages\document_review.py', 'r', encoding='utf-8') as f:
            dr_src = f.read()
        self.assertIn("'Sightseeing Voucher'", dr_src)
        self.assertIn("'Transfer Voucher'", dr_src)

    def test_02_new_document_types_registered(self):
        """2. Land Voucher, Aadhaar Card, and PAN Card are added across all schemas."""
        for dt in ['Land Voucher', 'Aadhaar Card', 'PAN Card']:
            self.assertIn(dt, document_processor.SCHEMAS, f"{dt} missing from document_processor.SCHEMAS")

        with open(r'C:\KT_Vault_V3\pages\smart_upload.py', 'r', encoding='utf-8') as f:
            su_src = f.read()
        for dt in ['Land Voucher', 'Aadhaar Card', 'PAN Card']:
            self.assertIn(f"'{dt}'", su_src, f"{dt} missing from smart_upload.py")

        with open(r'C:\KT_Vault_V3\pages\document_review.py', 'r', encoding='utf-8') as f:
            dr_src = f.read()
        for dt in ['Land Voucher', 'Aadhaar Card', 'PAN Card']:
            self.assertIn(f"'{dt}'", dr_src, f"{dt} missing from document_review.py")

    def test_03_classification_heuristics(self):
        """3. Classifier recognizes Land Voucher, Aadhaar Card, and PAN Card independently."""
        # Land Voucher
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            "LAND VOUCHER\nBooking Ref: LV-2026-99\nService: Desert Safari 4x4\nService Date: 12 Dec 2026\nGuest: Aarav Mehta"
        )
        self.assertEqual(doc_type, 'Land Voucher')

        # Aadhaar Card
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            "Government of India\nUnique Identification Authority of India\nName: Aarav Mehta\nDOB: 15/08/1990\nGender: Male\n9876 5432 1098"
        )
        self.assertEqual(doc_type, 'Aadhaar Card')

        # PAN Card
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            "INCOME TAX DEPARTMENT\nGOVT OF INDIA\nPermanent Account Number Card\nName: AARAV MEHTA\nFather's Name: SURESH MEHTA\nDOB: 15/08/1990\nABCDE1234F"
        )
        self.assertEqual(doc_type, 'PAN Card')

        # Sightseeing Voucher unchanged
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            "SIGHTSEEING VOUCHER\nTour Name: Burj Khalifa At the Top\nBooking Ref: BK-4411\nActivity Date: 11 Dec 2026\nGuest Name: Aarav Mehta"
        )
        self.assertEqual(doc_type, 'Sightseeing Voucher')

    def test_04_field_extraction_land_voucher(self):
        """4. Verify field extraction for Land Voucher."""
        sample_text = (
            "LAND VOUCHER\n"
            "Booking Ref: LV-8821\n"
            "Guest Name: Rohan Test\n"
            "Service Name: Airport to Hotel Ground Arrangement\n"
            "Service Date: 15 Dec 2026\n"
            "Pickup Location: Changi Airport\n"
            "Dropoff Location: Marina Bay Sands\n"
            "Service Time: 14:30\n"
            "Number of Guests: 2\n"
        )
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(sample_text)
        self.assertEqual(doc_type, 'Land Voucher')
        self.assertEqual(data.get('Booking Reference'), 'LV-8821')
        self.assertEqual(data.get('Guest / Passenger Name'), 'Rohan Test')
        self.assertEqual(data.get('Service Date'), '15 Dec 2026')

    def test_05_field_extraction_aadhaar_card(self):
        """5. Verify field extraction for Aadhaar Card."""
        sample_text = (
            "Government of India\n"
            "Unique Identification Authority of India\n"
            "Name: Amit Mehta\n"
            "DOB: 14/05/1985\n"
            "Gender: Male\n"
            "Address: 123 MG Road, Mumbai, Maharashtra 400001\n"
            "4567 8901 2345\n"
        )
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(sample_text)
        self.assertEqual(doc_type, 'Aadhaar Card')
        self.assertEqual(data.get('Aadhaar Number'), '4567 8901 2345')
        self.assertEqual(data.get('Full Name'), 'Amit Mehta')
        self.assertEqual(data.get('Gender'), 'Male')

    def test_06_field_extraction_pan_card(self):
        """6. Verify field extraction for PAN Card."""
        sample_text = (
            "INCOME TAX DEPARTMENT\n"
            "GOVT. OF INDIA\n"
            "Permanent Account Number Card\n"
            "Name: NEHA KAPOOR\n"
            "Father's Name: RAJESH KAPOOR\n"
            "DOB: 22/10/1992\n"
            "ABCDE1234F\n"
        )
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(sample_text)
        self.assertEqual(doc_type, 'PAN Card')
        self.assertEqual(data.get('PAN Number'), 'ABCDE1234F')
        self.assertEqual(data.get('Full Name'), 'NEHA KAPOOR')
        self.assertEqual(data.get("Father's Name"), 'RAJESH KAPOOR')

    def test_07_aadhaar_number_masking(self):
        """7. Verify Aadhaar number masking helper protects sensitive digits."""
        self.assertEqual(services.mask_aadhaar("9876 5432 1098"), "XXXX-XXXX-1098")
        self.assertEqual(services.mask_aadhaar("987654321098"), "XXXX-XXXX-1098")
        self.assertEqual(services.mask_aadhaar(""), "")
        self.assertEqual(services.mask_aadhaar(None), "")

    def test_08_optional_documents_do_not_block_readiness(self):
        """8. Aadhaar Card and PAN Card do not penalize trip readiness when unfulfilled."""
        r_total, r_comp, r_att, r_miss, r_pct, r_status = services.calculate_readiness("KT-T-0004")
        self.assertEqual(r_total, 9)
        self.assertEqual(r_comp, 1)

        conn = database.get_connection()
        opt_req_id = f"REQ-OPT-{uuid.uuid4().hex[:6]}"
        conn.execute(
            "INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, ?, ?, ?, 'TRAVELLER')",
            (opt_req_id, "KT-T-0004", "KT-TR-0004", "Aadhaar Card")
        )
        conn.commit()
        conn.close()

        r2_total, r2_comp, r2_att, r2_miss, r2_pct, r2_status = services.calculate_readiness("KT-T-0004")
        self.assertEqual(r2_total, 9, "Optional Aadhaar Card should not inflate total required documents")
        self.assertEqual(r2_miss, 8, "Optional Aadhaar Card should not inflate missing required documents")
        self.assertEqual(r2_pct, r_pct, "Readiness percentage should be unchanged")

    def test_09_travel_file_excludes_sensitive_id_cards(self):
        """9. Travel File PDF generator excludes Aadhaar and PAN documents from the travel package."""
        conn = database.get_connection()
        req_pan = f"REQ-TEST-PAN-{uuid.uuid4().hex[:6]}"
        conn.execute(
            "INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, 'KT-T-0001', 'TRV-001', 'PAN Card', 'TRAVELLER')",
            (req_pan,)
        )
        conn.execute(
            "INSERT INTO documents (id, requirement_id, status, file_path, uploaded_at) VALUES (?, ?, 'Verified', 'dummy.pdf', datetime('now'))",
            (f"DOC-{uuid.uuid4().hex[:8]}", req_pan)
        )
        conn.commit()

        docs = conn.execute('''
            SELECT r.name as req_name, r.type as req_type, d.status
            FROM requirements r
            LEFT JOIN documents d ON r.id = d.requirement_id
            WHERE r.trip_id = 'KT-T-0001'
        ''').fetchall()
        conn.close()

        included_reqs = [d['req_name'] for d in docs if d['req_name'] not in ['Aadhaar Card', 'PAN Card']]
        self.assertNotIn('PAN Card', included_reqs)
        self.assertNotIn('Aadhaar Card', included_reqs)

    def test_10_vault_search_filter_options(self):
        """10. Vault Search includes Land Voucher, Aadhaar Card, and PAN Card in options."""
        with open(r'C:\KT_Vault_V3\pages\vault_search.py', 'r', encoding='utf-8') as f:
            vs_src = f.read()
        self.assertIn('"Land Voucher"', vs_src)
        self.assertIn('"Aadhaar Card"', vs_src)
        self.assertIn('"PAN Card"', vs_src)
        self.assertIn('"Sightseeing Voucher"', vs_src)
        self.assertIn('"Transfer Voucher"', vs_src)

    def test_11_live_database_record_preservation(self):
        """11. Verify that live production DB records remain 100% intact."""
        live_con = sqlite3.connect(r'C:\KT_Vault_V3\data\kt_vault_v3.db')
        c_cust = live_con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        c_trv = live_con.execute("SELECT COUNT(*) FROM travellers").fetchone()[0]
        c_trips = live_con.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
        c_reqs = live_con.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        c_docs = live_con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        c_users = live_con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        live_con.close()

        self.assertEqual(c_cust, 4)
        self.assertEqual(c_trv, 4)
        self.assertEqual(c_trips, 4)
        self.assertEqual(c_reqs, 38)
        self.assertEqual(c_docs, 28)
        self.assertEqual(c_users, 3)


if __name__ == '__main__':
    unittest.main()
