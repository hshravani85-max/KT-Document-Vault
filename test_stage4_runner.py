import unittest
import os
import shutil
import sqlite3
import json
import database
import services
import auth_services
from travel_file_generator import generate_consolidated_travel_file
from document_processor import simple_pdf_extract

TEST_DB_PATH = "data/kt_vault_stage4_test.db"

class TestStage4BackendAndEnforcement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated synthetic database copy
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        shutil.copy2("data/kt_vault_v3.db", TEST_DB_PATH)
        # Monkey-patch database.get_connection to route to TEST_DB_PATH
        cls.orig_get_conn = database.get_connection
        database.get_connection = lambda: sqlite3.connect(TEST_DB_PATH)
        # Ensure row factory
        def custom_conn():
            c = sqlite3.connect(TEST_DB_PATH)
            c.row_factory = sqlite3.Row
            return c
        database.get_connection = custom_conn

        # Prepare tokens
        cls.admin_token = auth_services.authenticate_user("admin", "admin123")["token"]
        cls.staff_token = auth_services.authenticate_user("staff", "staff123")["token"]

    @classmethod
    def tearDownClass(cls):
        database.get_connection = cls.orig_get_conn
        try:
            if os.path.exists(TEST_DB_PATH):
                os.remove(TEST_DB_PATH)
        except:
            pass

    def test_01_mandatory_field_enforcement_all_types(self):
        conn = database.get_connection()
        test_specs = [
            ("Passport", ["Full Name", "Passport Number", "Date of Birth", "Nationality", "Expiry Date"], {"Place of Issue": "Mumbai"}),
            ("Flight Ticket", ["Passenger Name", "PNR/Booking Reference", "Route", "Departure Date/Time", "Arrival Date/Time"], {"Airline": "EK", "Cabin Class": "Economy"}),
            ("Visa / Entry Document", ["Traveller Name", "Visa Number / Reference", "Destination"], {"Purpose": "Holiday", "Travel Dates": "12-18 Dec"}),
            ("Hotel Voucher", ["Hotel Name", "Guest Name", "Check-in Date", "Check-out Date", "Booking Confirmation Number"], {"Room Type": "Deluxe"}),
            ("Travel Insurance", ["Insured Name", "Policy Number", "Valid From", "Valid Until"], {"Insurance Provider": "Demo Care"}),
            ("Transfer Voucher", ["Passenger Name", "Booking Reference", "Pickup Location", "Dropoff Location", "Transfer Date"], {"Transfer Time": "10:00"}),
            ("Sightseeing Voucher", ["Guest Name", "Booking Reference", "Tour / Activity Name", "Activity Date"], {"Number of Guests": "2"}),
            ("Arrival / Entry Document", ["Traveller Name", "Destination", "Arrival Date", "Reference Number"], {"Departure Date": "18 Dec"}),
            ("Itinerary", ["Start Date", "End Date", "Schedule Summary"], {"Trip Destination": "Dubai"})
        ]

        # Use an existing requirement or insert dummy ones
        for idx, (doc_name, mand_list, opt_dict) in enumerate(test_specs):
            req_id = f"REQ-TEST-{idx}"
            doc_id = f"DOC-TEST-{idx}"
            conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, name, type) VALUES (?, 'KT-T-STAGE4', ?, 'TRIP')", (req_id, doc_name))

            # 1. Test missing each mandatory field blocks verification
            for m in mand_list:
                partial_data = {k: "valid_val" for k in mand_list if k != m}
                partial_data.update(opt_dict)
                conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES (?, ?, 'Under Review', ?)",
                             (doc_id, req_id, json.dumps(partial_data)))
                conn.commit()

                with self.assertRaises(ValueError) as ctx:
                    services.verify_document(doc_id, self.admin_token)
                self.assertIn(f"Missing mandatory field '{m}'", str(ctx.exception))

            # 2. Test full mandatory with optional fields omitted SUCCEEDS
            full_mand_only = {k: "valid_val" for k in mand_list}
            conn.execute("UPDATE documents SET status = 'Under Review', extracted_data = ? WHERE id = ?", (json.dumps(full_mand_only), doc_id))
            conn.commit()

            services.verify_document(doc_id, self.admin_token)
            doc_status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()["status"]
            self.assertEqual(doc_status, "Verified", f"Failed verifying {doc_name} with only mandatory fields")

            # Check history
            hist = conn.execute("SELECT * FROM document_history WHERE document_id = ? AND event_type = 'VERIFY'", (doc_id,)).fetchone()
            self.assertIsNotNone(hist)
            self.assertEqual(hist["actor"], "System Admin")

        conn.close()

    def test_02_staff_blocked_from_verifying(self):
        conn = database.get_connection()
        doc_id = "DOC-TEST-STAFF"
        req_id = "REQ-TEST-STAFF"
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, name, type) VALUES (?, 'KT-T-STAGE4', 'Passport', 'TRIP')", (req_id,))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES (?, ?, 'Under Review', ?)",
                     (doc_id, req_id, json.dumps({"Full Name": "Test", "Passport Number": "P123", "Date of Birth": "01 Jan 1990", "Nationality": "Indian", "Expiry Date": "01 Jan 2030"})))
        conn.commit()
        conn.close()

        with self.assertRaises(PermissionError):
            services.verify_document(doc_id, self.staff_token)

    def test_03_reopen_and_reverification_audit_trail(self):
        conn = database.get_connection()
        doc_id = "DOC-TEST-REOPEN"
        req_id = "REQ-TEST-REOPEN"
        conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, name, type) VALUES (?, 'KT-T-STAGE4', 'Passport', 'TRIP')", (req_id,))
        conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES (?, ?, 'Verified', ?)",
                     (doc_id, req_id, json.dumps({"Full Name": "Test", "Passport Number": "P123", "Date of Birth": "01 Jan 1990", "Nationality": "Indian", "Expiry Date": "01 Jan 2030"})))
        conn.commit()

        # Reopen with reason
        services.reopen_document(doc_id, "Typo in name", self.admin_token)
        status_after_reopen = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()["status"]
        self.assertEqual(status_after_reopen, "Under Review")

        # Verify history recorded
        hist_reopen = conn.execute("SELECT * FROM document_history WHERE document_id = ? AND event_type = 'REOPEN'", (doc_id,)).fetchone()
        self.assertEqual(hist_reopen["reason"], "Typo in name")

        # Re-verify
        services.verify_document(doc_id, self.admin_token)
        status_after_reverify = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()["status"]
        self.assertEqual(status_after_reverify, "Verified")

        hist_count = conn.execute("SELECT COUNT(*) FROM document_history WHERE document_id = ?", (doc_id,)).fetchone()[0]
        self.assertGreaterEqual(hist_count, 2)
        conn.close()

    def test_04_readiness_calculation_and_pdf_accuracy(self):
        # KT-T-0001: 9/9 Verified
        total, comp, att, miss, pct, bstatus = services.calculate_readiness("KT-T-0001")
        self.assertEqual(total, 9)
        self.assertEqual(comp, 9)
        self.assertEqual(pct, 100)

        # KT-T-0002: 9 requirements: 3 Verified, 1 Under Review, 5 Missing -> 3/9 = 33%
        total2, comp2, att2, miss2, pct2, bstatus2 = services.calculate_readiness("KT-T-0002")
        self.assertEqual(total2, 9)
        self.assertEqual(comp2, 3)
        self.assertEqual(miss2, 5)
        self.assertEqual(att2, 1)
        self.assertEqual(pct2, 33)
        self.assertEqual(bstatus2, "NOT READY")

        # Generate PDF for KT-T-0002 and ensure actual status labels appear
        pdf_path = generate_consolidated_travel_file("KT-T-0002", "documents/test_stage4_pdf.pdf")
        pdf_text = simple_pdf_extract(open(pdf_path, "rb").read())
        self.assertIn("[Verified]", pdf_text)
        self.assertIn("[Under Review]", pdf_text)
        self.assertIn("[Missing]", pdf_text)
        self.assertNotIn("[Verified] for Hotel Voucher", pdf_text)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

    def test_05_stale_field_prevention_on_type_switch(self):
        # Simulating the UI's FIELD_ALIASES mapping and stale field clearing
        SCHEMAS = {
            'Passport': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
            'Hotel Voucher': ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address'],
            'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class'],
        }
        FIELD_ALIASES = {
            'Passenger Name': ['Traveller Name', 'Guest Name', 'Insured Name', 'Full Name'],
            'Guest Name': ['Traveller Name', 'Passenger Name', 'Insured Name', 'Full Name'],
            'Full Name': ['Traveller Name', 'Passenger Name', 'Guest Name', 'Insured Name'],
            'Booking Confirmation Number': ['Booking Reference', 'PNR/Booking Reference', 'Reference Number']
        }

        # Suppose user originally uploaded Flight Ticket
        flight_data = {
            'Passenger Name': 'Amit Mehta',
            'Route': 'BOM-DXB',
            'Airline': 'Emirates',
            'Flight Number': 'EK501',
            'PNR/Booking Reference': 'KT-123',
            'Origin': 'BOM',
            'Destination': 'DXB',
            'Departure Date/Time': '12 Dec 2026',
            'Arrival Date/Time': '12 Dec 2026',
            'Cabin Class': 'Economy'
        }

        # User switches to Hotel Voucher
        target_fields = SCHEMAS['Hotel Voucher']
        new_hotel_data = {}
        for tf in target_fields:
            val = flight_data.get(tf, '')
            if not val and tf in FIELD_ALIASES:
                for alias in FIELD_ALIASES[tf]:
                    if flight_data.get(alias):
                        val = flight_data[alias]
                        break
            new_hotel_data[tf] = val

        # Assert Guest Name is mapped from Passenger Name
        self.assertEqual(new_hotel_data['Guest Name'], 'Amit Mehta')
        self.assertEqual(new_hotel_data['Booking Confirmation Number'], 'KT-123')
        # Assert flight-specific keys are NOT present in hotel data schema
        self.assertNotIn('Flight Number', new_hotel_data)
        self.assertNotIn('Cabin Class', new_hotel_data)
        self.assertNotIn('Route', new_hotel_data)

if __name__ == "__main__":
    unittest.main()
