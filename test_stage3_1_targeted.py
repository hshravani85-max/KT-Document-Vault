import unittest
import os
from document_processor import parse_passport_text, process_document

class TestStage3Point1Targeted(unittest.TestCase):
    def test_itinerary_dates_with_year(self):
        text = """ITINERARY
12 Dec 2026: Arrival in Dubai
14 Dec 2026: Highlights tour
18 Dec 2026: Checkout and departure
"""
        data, _, dt, _ = parse_passport_text(text)
        self.assertEqual(dt, "Itinerary")
        self.assertEqual(data["Start Date"], "12 Dec 2026")
        self.assertEqual(data["End Date"], "18 Dec 2026")

    def test_itinerary_dates_without_year(self):
        text = """ITINERARY
12 Dec: Arrival
18 Dec: Departure
"""
        data, _, dt, _ = parse_passport_text(text)
        self.assertEqual(dt, "Itinerary")
        self.assertEqual(data["Start Date"], "12 Dec")
        self.assertEqual(data["End Date"], "18 Dec")

    def test_flight_ticket_departure_arrival_separation(self):
        text = """FLIGHT TICKET
Passenger Name: Neha Kapoor
Booking Reference: KT-DEMO-FLT-3002
Airline: Emirates
Flight Number: EK 501
From: Mumbai (BOM)
To: Dubai (DXB)
Departure: 12 Dec 2026 09:30
Arrival: 12 Dec 2026 11:30
Cabin: Economy
"""
        data, _, dt, _ = parse_passport_text(text)
        self.assertEqual(dt, "Flight Ticket")
        self.assertEqual(data["Passenger Name"], "Neha Kapoor")
        self.assertEqual(data["PNR/Booking Reference"], "KT-DEMO-FLT-3002")
        self.assertEqual(data["Airline"], "Emirates")
        self.assertEqual(data["Flight Number"], "EK 501")
        self.assertEqual(data["Origin"], "Mumbai (BOM)")
        self.assertEqual(data["Destination"], "Dubai (DXB)")
        self.assertEqual(data["Departure Date/Time"], "12 Dec 2026 09:30")
        self.assertEqual(data["Arrival Date/Time"], "12 Dec 2026 11:30")
        self.assertEqual(data["Cabin Class"], "Economy")

    def test_transfer_time_handling(self):
        # Present
        text_with_time = """TRANSFER VOUCHER
Passenger: Amit Mehta
Reference: KT-TRF-DXB-1201
Pickup: Dubai Airport
Dropoff: Hotel
Date: 12 Dec 2026
Time: 14:00
"""
        data, _, _, _ = parse_passport_text(text_with_time)
        self.assertEqual(data["Transfer Time"], "14:00")

        # Missing
        text_without_time = """TRANSFER VOUCHER
Passenger: Amit Mehta
Reference: KT-TRF-DXB-1201
Pickup: Dubai Airport
Dropoff: Hotel
Date: 12 Dec 2026
"""
        data_no, _, _, _ = parse_passport_text(text_without_time)
        self.assertEqual(data_no["Transfer Time"], "")

    def test_arrival_departure_date_handling(self):
        # Present
        text_with_dep = """ARRIVAL / ENTRY DOCUMENT
Traveller: Amit Mehta
Trip: Dubai Holiday
Destination: Dubai, UAE
Arrival Date: 12 Dec 2026
Departure Date: 18 Dec 2026
Reference: KT-ARRIVAL-DEMO-001
"""
        data, _, _, _ = parse_passport_text(text_with_dep)
        self.assertEqual(data["Departure Date"], "18 Dec 2026")

        # Missing
        text_without_dep = """ARRIVAL / ENTRY DOCUMENT
Traveller: Amit Mehta
Trip: Dubai Holiday
Destination: Dubai, UAE
Arrival Date: 12 Dec 2026
Reference: KT-ARRIVAL-DEMO-001
"""
        data_no, _, _, _ = parse_passport_text(text_without_dep)
        self.assertEqual(data_no["Departure Date"], "")

    def test_itinerary_destination_handling(self):
        # Explicit label
        text_with_dest = """ITINERARY
Destination: Dubai, UAE
12 Dec 2026: Day 1
18 Dec 2026: Day 7
"""
        data, _, _, _ = parse_passport_text(text_with_dest)
        self.assertEqual(data["Trip Destination"], "Dubai, UAE")

        # Title pattern
        text_title = """Dubai Itinerary
12 Dec 2026: Day 1
18 Dec 2026: Day 7
"""
        data_title, _, _, _ = parse_passport_text(text_title)
        self.assertEqual(data_title["Trip Destination"], "Dubai")

        # Missing destination
        text_no_dest = """ITINERARY
12 Dec: Day 1
18 Dec: Day 7
"""
        data_no, _, _, _ = parse_passport_text(text_no_dest)
        self.assertEqual(data_no["Trip Destination"], "")

    def test_passport_and_synthetic_fixtures_regression(self):
        docs = [
            ("01_Amit_Mehta_Demo_Passport.pdf", "Passport"),
            ("01_Neha_Kapoor_DEMO_Passport.pdf", "Passport"),
            ("02_Amit_Mehta_Demo_Visa_Entry.pdf", "Visa / Entry Document"),
            ("trip_upload_ac7aa46c85fc493c8ac7774cceb4fce6.pdf", "Flight Ticket"),
            ("04_Dubai_Hotel_Voucher.pdf", "Hotel Voucher"),
            ("05_Travel_Insurance.pdf", "Travel Insurance"),
            ("06_Transfer_Voucher.pdf", "Transfer Voucher"),
            ("07_Sightseeing_Voucher.pdf", "Sightseeing Voucher"),
            ("08_Arrival_Entry_Document.pdf", "Arrival / Entry Document"),
            ("09_Dubai_Itinerary.pdf", "Itinerary")
        ]
        for fname, expected_type in docs:
            p = os.path.join("documents", fname)
            with open(p, "rb") as f:
                res = process_document(fname, f.read())
            self.assertEqual(res["document_type"], expected_type, f"Mismatch for {fname}")

if __name__ == "__main__":
    unittest.main()
