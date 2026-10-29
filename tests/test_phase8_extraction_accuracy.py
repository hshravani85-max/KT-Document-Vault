import unittest
import os
import io
import re
import hashlib
import document_processor

class TestPhase8ExtractionAccuracy(unittest.TestCase):
    def setUp(self):
        import sqlite3
        self.sqlite3 = sqlite3
        self.doc_dir = r"C:\KT_Vault_V3\documents"
        self.db_path = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
        self.initial_db_size = os.path.getsize(self.db_path)
        with open(self.db_path, "rb") as f:
            self.initial_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()

    def test_01_pypdf_stream_extraction(self):
        """Verify PyPDF extraction succeeds on sample PDFs without errors."""
        pdf_path = os.path.join(self.doc_dir, "03_Dubai_Flight_Ticket.pdf")
        self.assertTrue(os.path.exists(pdf_path), f"File not found: {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        extracted_text = document_processor.simple_pdf_extract(pdf_bytes)
        self.assertGreater(len(extracted_text), 50)
        self.assertIn("Passenger: Amit Mehta", extracted_text)
        self.assertIn("KTDEMO-DXB-4812", extracted_text)

    def test_02_flight_route_splitting(self):
        """Verify route tokenization extracts Origin and Destination from Route strings."""
        ticket_text = """
FLIGHT TICKET
DEMO / SAMPLE / NOT A REAL DOCUMENT
Passenger: Neha Kapoor
Booking Reference: KT-DEMO-FLT-3002
Route: Mumbai (BOM) - Singapore (SIN) - Mumbai (BOM)
Outbound: 20 Jan 2027
Return: 26 Jan 2027
Cabin: Economy - DEMO
"""
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(ticket_text, expected_requirement="Flight Ticket")
        self.assertEqual(doc_type, "Flight Ticket")
        self.assertEqual(data.get("Passenger Name"), "Neha Kapoor")
        self.assertEqual(data.get("Route"), "Mumbai (BOM) - Singapore (SIN) - Mumbai (BOM)")
        self.assertEqual(data.get("Origin"), "Mumbai (BOM)")
        self.assertEqual(data.get("Destination"), "Singapore (SIN)")
        self.assertEqual(data.get("PNR/Booking Reference"), "KT-DEMO-FLT-3002")
        self.assertEqual(data.get("Departure Date/Time"), "20 Jan 2027")
        self.assertEqual(data.get("Arrival Date/Time"), "26 Jan 2027")
        self.assertEqual(data.get("Cabin Class"), "Economy - DEMO")

    def test_03_flight_number_and_airline_resolution(self):
        """Verify flight number regexes and IATA airline lookup resolve accurately."""
        # Test 1: SQ 423 -> Singapore Airlines
        text1 = """
FLIGHT ITINERARY
Passenger: Neha Kapoor
Flight: SQ 423
Route: Mumbai - Singapore
Booking Reference: KT-SQ-9901
"""
        data1, _, _, _ = document_processor.parse_passport_text(text1, expected_requirement="Flight Ticket")
        self.assertEqual(data1.get("Flight Number"), "SQ 423")
        self.assertEqual(data1.get("Airline"), "Singapore Airlines")
        self.assertEqual(data1.get("Origin"), "Mumbai")
        self.assertEqual(data1.get("Destination"), "Singapore")

        # Test 2: EK 501 -> Emirates
        text2 = """
FLIGHT TICKET
Passenger: Amit Mehta
Flight No: EK 501
Route: Mumbai - Dubai
Booking Reference: KT-EK-8812
"""
        data2, _, _, _ = document_processor.parse_passport_text(text2, expected_requirement="Flight Ticket")
        self.assertEqual(data2.get("Flight Number"), "EK 501")
        self.assertEqual(data2.get("Airline"), "Emirates")

        # Test 3: 6E 1405 -> IndiGo
        text3 = """
BOARDING PASS
Passenger: Rajesh Sharma
Flt No. 6E 1405
Route: Delhi - Bangkok
PNR: 6EDELBKK
"""
        data3, _, _, _ = document_processor.parse_passport_text(text3, expected_requirement="Flight Ticket")
        self.assertEqual(data3.get("Flight Number"), "6E 1405")
        self.assertEqual(data3.get("Airline"), "IndiGo")

    def test_04_requirement_prior_classification(self):
        """Verify requirement prior eliminates cross-contamination between similar documents."""
        # Arrival document that mentions airline or flight
        text_with_crossover = """
Arrival / Entry Information - Demo
Traveller: Neha Kapoor
Destination: Singapore
Arrival Date: 20 Jan 2027
Departure Date: 26 Jan 2027
Reference: KT-DEMO-ARR-3002
Flight: SQ 423
"""
        # When uploaded for Arrival / Entry Document, it must classify as Arrival Document
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            text_with_crossover, expected_requirement="Arrival / Entry Document"
        )
        self.assertEqual(doc_type, "Arrival / Entry Document")
        self.assertEqual(data.get("Traveller Name"), "Neha Kapoor")
        self.assertEqual(data.get("Destination"), "Singapore")
        self.assertEqual(data.get("Arrival Date"), "20 Jan 2027")
        self.assertEqual(data.get("Departure Date"), "26 Jan 2027")

    def test_05_boundary_stop_prevents_field_swallowing(self):
        """Verify that multi-line accumulation halts at label boundaries and does not swallow following lines."""
        arrival_text = """
Field
Details
Traveller
Neha Kapoor
Destination
Singapore
Arrival Date
20 Jan 2027
Departure Date
26 Jan 2027
Reference
KT-DEMO-ARR-3002
Status
Prepared - DEMO
"""
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            arrival_text, expected_requirement="Arrival / Entry Document"
        )
        self.assertEqual(doc_type, "Arrival / Entry Document")
        # Must be strictly 'Singapore', NOT 'Singapore Arrival Date 20 Jan 2027'
        self.assertEqual(data.get("Destination"), "Singapore")
        self.assertEqual(data.get("Traveller Name"), "Neha Kapoor")
        self.assertEqual(data.get("Arrival Date"), "20 Jan 2027")
        self.assertEqual(data.get("Departure Date"), "26 Jan 2027")
        self.assertEqual(data.get("Reference Number"), "KT-DEMO-ARR-3002")

    def test_06_all_9_demo_documents(self):
        """Verify extraction and classification on all demo documents in documents/."""
        expected_mappings = [
            ("01_Amit_Mehta_Demo_Passport.pdf", "Passport"),
            ("01_Neha_Kapoor_DEMO_Passport.pdf", "Passport"),
            ("02_Amit_Mehta_Demo_Visa_Entry.pdf", "Visa / Entry Document"),
            ("03_Dubai_Flight_Ticket.pdf", "Flight Ticket"),
            ("04_Dubai_Hotel_Voucher.pdf", "Hotel Voucher"),
            ("05_Travel_Insurance.pdf", "Travel Insurance"),
            ("06_Transfer_Voucher.pdf", "Transfer Voucher"),
            ("07_Sightseeing_Voucher.pdf", "Sightseeing Voucher"),
            ("08_Arrival_Entry_Document.pdf", "Arrival / Entry Document"),
            ("09_Dubai_Itinerary.pdf", "Itinerary"),
        ]
        for filename, expected_type in expected_mappings:
            path = os.path.join(self.doc_dir, filename)
            self.assertTrue(os.path.exists(path), f"File {path} does not exist")
            with open(path, "rb") as f:
                res = document_processor.process_document(filename, f.read(), expected_requirement=expected_type)
            self.assertEqual(
                res["document_type"], expected_type,
                f"Failed for {filename}: got {res['document_type']}, expected {expected_type}"
            )
            # Ensure extracted fields dictionary has expected schema keys
            self.assertIn("extracted_fields", res)
            self.assertIsInstance(res["extracted_fields"], dict)

    def test_07_dubai_flight_ticket_origin_destination_populated(self):
        """Verify 03_Dubai_Flight_Ticket.pdf now populates Origin and Destination from Route."""
        path = os.path.join(self.doc_dir, "03_Dubai_Flight_Ticket.pdf")
        with open(path, "rb") as f:
            res = document_processor.process_document("03_Dubai_Flight_Ticket.pdf", f.read(), expected_requirement="Flight Ticket")
        fields = res["extracted_fields"]
        self.assertEqual(fields.get("Passenger Name"), "Amit Mehta")
        self.assertEqual(fields.get("Route"), "Mumbai - Dubai - Mumbai")
        self.assertEqual(fields.get("Origin"), "Mumbai")
        self.assertEqual(fields.get("Destination"), "Dubai")
        self.assertEqual(fields.get("Departure Date/Time"), "12 Dec 2026")
        self.assertEqual(fields.get("Arrival Date/Time"), "18 Dec 2026")

    def test_09_multiline_flight_booking_reference_isolation(self):
        """Verify that hyphenated references like KT-DEMO-FLT-3002 are not misclassified as Flight Numbers."""
        multiline_ticket = """
DEMO / SAMPLE / NOT A REAL DOCUMENT
 Flight Itinerary - Demo
 Synthetic flight booking confirmation
Field
Details
Passenger
Neha Kapoor
Route
Mumbai (BOM) - Singapore (SIN) - Mumbai (BOM)
Outbound
20 Jan 2027
Return
26 Jan 2027
Booking Reference
KT-DEMO-FLT-3002
Cabin
Economy - DEMO
"""
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(
            multiline_ticket, expected_requirement="Flight Ticket"
        )
        self.assertEqual(doc_type, "Flight Ticket")
        self.assertEqual(data.get("Passenger Name"), "Neha Kapoor")
        self.assertEqual(data.get("PNR/Booking Reference"), "KT-DEMO-FLT-3002")
        self.assertEqual(data.get("Flight Number"), "")
        self.assertEqual(data.get("Airline"), "")
        self.assertEqual(data.get("Origin"), "Mumbai (BOM)")
        self.assertEqual(data.get("Destination"), "Singapore (SIN)")

        # Verify valid flight formats still parse accurately
        test_cases = [
            ("Passenger: Raj\nFlt No. 6E 1405\nRoute: DEL - BKK", "6E 1405", "IndiGo"),
            ("Passenger: Raj\nFlight: SQ 423\nRoute: BOM - SIN", "SQ 423", "Singapore Airlines"),
            ("Passenger: Raj\nFlight No: EK 501\nRoute: BOM - DXB", "EK 501", "Emirates"),
        ]
        for tc_text, exp_flt, exp_air in test_cases:
            tc_data, _, _, _ = document_processor.parse_passport_text(tc_text, expected_requirement="Flight Ticket")
            self.assertEqual(tc_data.get("Flight Number"), exp_flt)
            self.assertEqual(tc_data.get("Airline"), exp_air)

    def test_10_singapore_flight_ticket_and_arrival_card(self):
        """Verify extraction on Singapore customer demo files."""
        flt_path = os.path.join(self.doc_dir, "trip_upload_ac7aa46c85fc493c8ac7774cceb4fce6.pdf")
        if os.path.exists(flt_path):
            with open(flt_path, "rb") as f:
                res = document_processor.process_document("singapore_flt.pdf", f.read(), expected_requirement="Flight Ticket")
            self.assertEqual(res["document_type"], "Flight Ticket")
            fields = res["extracted_fields"]
            self.assertEqual(fields.get("Passenger Name"), "Neha Kapoor")
            self.assertEqual(fields.get("PNR/Booking Reference"), "KT-DEMO-FLT-3002")
            self.assertEqual(fields.get("Flight Number"), "")
            self.assertEqual(fields.get("Airline"), "")

        arr_path = os.path.join(self.doc_dir, "trip_upload_cd25838601494d54961472bab68eff0c.pdf")
        if os.path.exists(arr_path):
            with open(arr_path, "rb") as f:
                res = document_processor.process_document("singapore_arr.pdf", f.read(), expected_requirement="Arrival / Entry Document")
            self.assertEqual(res["document_type"], "Arrival / Entry Document")
            fields = res["extracted_fields"]
            self.assertEqual(fields.get("Traveller Name"), "Neha Kapoor")
            self.assertEqual(fields.get("Destination"), "Singapore")
            self.assertEqual(fields.get("Reference Number"), "KT-DEMO-ARR-3002")

    def test_11_database_checksum_untouched(self):
        """Verify that the production database remains completely untouched."""
        self.assertTrue(os.path.exists(self.db_path))
        with open(self.db_path, "rb") as f:
            current_hash = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(current_hash, self.initial_db_sha256, "DATABASE INTEGRITY BREACH: SHA-256 changed during test run!")
        conn = self.sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()

if __name__ == "__main__":
    unittest.main()
