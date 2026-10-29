import os
import unittest
from document_processor import simple_pdf_extract, process_document, parse_passport_text

class TestPhase5Extraction(unittest.TestCase):

    def test_benchmark_neha_kapoor_hotel_voucher(self):
        """A. Known PDF Benchmark 1: Neha Kapoor Hotel Voucher"""
        path = os.path.join('documents', 'trip_upload_1a2ef0da9c684f9cbc676f3a47605c0b.pdf')
        self.assertTrue(os.path.exists(path), f"File {path} does not exist")
        data = open(path, 'rb').read()
        res = process_document('04_Neha_Kapoor_DEMO_Hotel_Voucher.pdf', data)
        
        self.assertEqual(res['document_type'], 'Hotel Voucher')
        self.assertEqual(res['type_confidence'], 'high')
        fields = res['extracted_fields']
        
        self.assertEqual(fields.get('Hotel Name'), 'Marina Garden Hotel - DEMO')
        self.assertEqual(fields.get('Guest Name'), 'Neha Kapoor')
        self.assertEqual(fields.get('Check-in Date'), '20 Jan 2027')
        self.assertEqual(fields.get('Check-out Date'), '26 Jan 2027')
        self.assertEqual(fields.get('Booking Confirmation Number'), 'KT-DEMO-HTL-3002')
        self.assertEqual(fields.get('Room Type'), 'Deluxe Room - DEMO')
        self.assertEqual(fields.get('Hotel Address'), '')  # Genuinely absent

    def test_benchmark_dubai_flight_ticket_pdf(self):
        """A. Known PDF Benchmark 2: Dubai Flight Ticket with ET in TICKET operator bug fixed"""
        path = os.path.join('documents', '03_Dubai_Flight_Ticket.pdf')
        self.assertTrue(os.path.exists(path), f"File {path} does not exist")
        data = open(path, 'rb').read()
        res = process_document('03_Dubai_Flight_Ticket.pdf', data)
        
        self.assertEqual(res['document_type'], 'Flight Ticket')
        self.assertEqual(res['type_confidence'], 'high')
        self.assertEqual(res['source_type'], 'pdf_text')
        fields = res['extracted_fields']
        
        self.assertEqual(fields.get('Passenger Name'), 'Amit Mehta')
        self.assertEqual(fields.get('PNR/Booking Reference'), 'KTDEMO-DXB-4812')
        self.assertEqual(fields.get('Route'), 'Mumbai - Dubai - Mumbai')
        self.assertEqual(fields.get('Departure Date/Time'), '12 Dec 2026')
        self.assertEqual(fields.get('Arrival Date/Time'), '18 Dec 2026')
        self.assertEqual(fields.get('Cabin Class'), 'Economy - Demo')

    def test_all_existing_document_fixtures(self):
        """D. Verify existing document fixtures continue to extract successfully"""
        expected_fixtures = {
            '01_Amit_Mehta_Demo_Passport.pdf': ('Passport', 'Amit Mehta'),
            '01_Neha_Kapoor_DEMO_Passport.pdf': ('Passport', 'Neha Kapoor'),
            '02_Amit_Mehta_Demo_Visa_Entry.pdf': ('Visa / Entry Document', 'Amit Mehta'),
            '03_Dubai_Flight_Ticket.pdf': ('Flight Ticket', 'Amit Mehta'),
            '04_Dubai_Hotel_Voucher.pdf': ('Hotel Voucher', 'Amit Mehta'),
            '05_Travel_Insurance.pdf': ('Travel Insurance', 'Amit Mehta'),
            '06_Transfer_Voucher.pdf': ('Transfer Voucher', 'Amit Mehta'),
            '07_Sightseeing_Voucher.pdf': ('Sightseeing Voucher', 'Amit Mehta'),
            '08_Arrival_Entry_Document.pdf': ('Arrival / Entry Document', 'Amit Mehta'),
            '09_Dubai_Itinerary.pdf': ('Itinerary', None)
        }
        for fname, (expected_type, expected_name) in expected_fixtures.items():
            path = os.path.join('documents', fname)
            self.assertTrue(os.path.exists(path), f"Fixture {fname} missing")
            data = open(path, 'rb').read()
            res = process_document(fname, data)
            self.assertEqual(res['document_type'], expected_type, f"Mismatch in {fname}")
            self.assertEqual(res['type_confidence'], 'high', f"Confidence not high in {fname}")
            if expected_name:
                name_fields = ['Full Name', 'Passenger Name', 'Traveller Name', 'Guest Name', 'Insured Name']
                extracted_name = next((res['extracted_fields'][k] for k in name_fields if k in res['extracted_fields'] and res['extracted_fields'][k]), None)
                self.assertEqual(extracted_name, expected_name, f"Name mismatch in {fname}")

    def test_nine_types_single_line_and_table_layouts(self):
        """B. All 9 Document Types: Test single-line (Label: Value) and multi-line table (Label\nValue)"""
        cases = {
            'Passport': {
                'single': 'PASSPORT\nFull Name: Rohan Varma\nPassport Number: Z1234567\nDate of Birth: 15 May 1988\nNationality: Indian\nIssue Date: 10 Jan 2021\nExpiry Date: 09 Jan 2031\nPlace of Issue: Delhi',
                'table': 'PASSPORT\nFull Name\nRohan Varma\nPassport Number\nZ1234567\nDate of Birth\n15 May 1988\nNationality\nIndian\nIssue Date\n10 Jan 2021\nExpiry Date\n09 Jan 2031\nPlace of Issue\nDelhi',
                'expected': {'Full Name': 'Rohan Varma', 'Passport Number': 'Z1234567', 'Date of Birth': '15 May 1988', 'Nationality': 'Indian', 'Place of Issue': 'Delhi'}
            },
            'Visa / Entry Document': {
                'single': 'VISA / ENTRY DOCUMENT\nTraveller: Sunita Rao\nReference: SGP-VISA-9910\nDestination: Singapore\nPurpose: Tourism\nTravel Dates: 01 Feb 2027 - 10 Feb 2027\nIssue Date: 15 Jan 2027\nExpiry Date: 10 Feb 2027',
                'table': 'VISA / ENTRY DOCUMENT\nTraveller\nSunita Rao\nReference\nSGP-VISA-9910\nDestination\nSingapore\nPurpose\nTourism\nTravel Dates\n01 Feb 2027 - 10 Feb 2027\nIssue Date\n15 Jan 2027\nExpiry Date\n10 Feb 2027',
                'expected': {'Traveller Name': 'Sunita Rao', 'Visa Number / Reference': 'SGP-VISA-9910', 'Destination': 'Singapore', 'Purpose': 'Tourism', 'Expiry Date / Valid Until': '10 Feb 2027'}
            },
            'Flight Ticket': {
                'single': 'FLIGHT TICKET\nPassenger: Sunita Rao\nRoute: Mumbai - Singapore\nAirline: Singapore Airlines\nFlight Number: SQ421\nBooking Reference: SQ-BK-7788\nOrigin: Mumbai\nDestination: Singapore\nOutbound: 01 Feb 2027\nReturn: 10 Feb 2027\nCabin: Business',
                'table': 'FLIGHT TICKET\nPassenger\nSunita Rao\nRoute\nMumbai - Singapore\nAirline\nSingapore Airlines\nFlight Number\nSQ421\nBooking Reference\nSQ-BK-7788\nOrigin\nMumbai\nDestination\nSingapore\nOutbound\n01 Feb 2027\nReturn\n10 Feb 2027\nCabin\nBusiness',
                'expected': {'Passenger Name': 'Sunita Rao', 'PNR/Booking Reference': 'SQ-BK-7788', 'Departure Date/Time': '01 Feb 2027', 'Arrival Date/Time': '10 Feb 2027', 'Cabin Class': 'Business'}
            },
            'Hotel Voucher': {
                'single': 'HOTEL VOUCHER\nHotel: The Fullerton Hotel\nGuest: Sunita Rao\nCheck-in: 01 Feb 2027\nCheck-out: 10 Feb 2027\nBooking Reference: HTL-FUL-445\nRoom: Premier Quay\nAddress: 1 Fullerton Square',
                'table': 'HOTEL VOUCHER\nHotel\nThe Fullerton Hotel\nGuest\nSunita Rao\nCheck-in\n01 Feb 2027\nCheck-out\n10 Feb 2027\nVoucher Reference\nHTL-FUL-445\nRoom\nPremier Quay\nHotel Address\n1 Fullerton Square',
                'expected': {'Hotel Name': 'The Fullerton Hotel', 'Guest Name': 'Sunita Rao', 'Check-in Date': '01 Feb 2027', 'Check-out Date': '10 Feb 2027', 'Booking Confirmation Number': 'HTL-FUL-445', 'Room Type': 'Premier Quay', 'Hotel Address': '1 Fullerton Square'}
            },
            'Travel Insurance': {
                'single': 'TRAVEL INSURANCE\nInsured: Sunita Rao\nPolicy Number: POL-998877\nInsurance Provider: Bajaj Allianz\nValid From: 01 Feb 2027\nValid Until: 10 Feb 2027\nDestination: Singapore',
                'table': 'TRAVEL INSURANCE\nInsured\nSunita Rao\nPolicy Number\nPOL-998877\nInsurance Provider\nBajaj Allianz\nValid From\n01 Feb 2027\nValid Until\n10 Feb 2027\nDestination\nSingapore',
                'expected': {'Insured Name': 'Sunita Rao', 'Policy Number': 'POL-998877', 'Insurance Provider': 'Bajaj Allianz', 'Valid From': '01 Feb 2027', 'Valid Until': '10 Feb 2027', 'Destination / Coverage Area': 'Singapore'}
            },
            'Transfer Voucher': {
                'single': 'TRANSFER VOUCHER\nPassenger: Sunita Rao\nBooking Reference: TRF-SIN-101\nPickup: Changi Airport\nDropoff: The Fullerton Hotel\nDate: 01 Feb 2027\nTime: 09:30 AM',
                'table': 'TRANSFER VOUCHER\nPassenger\nSunita Rao\nBooking Reference\nTRF-SIN-101\nPickup\nChangi Airport\nDropoff\nThe Fullerton Hotel\nDate\n01 Feb 2027\nTime\n09:30 AM',
                'expected': {'Passenger Name': 'Sunita Rao', 'Booking Reference': 'TRF-SIN-101', 'Pickup Location': 'Changi Airport', 'Dropoff Location': 'The Fullerton Hotel', 'Transfer Date': '01 Feb 2027', 'Transfer Time': '09:30 AM'}
            },
            'Sightseeing Voucher': {
                'single': 'SIGHTSEEING VOUCHER\nGuest: Sunita Rao\nBooking Reference: SGT-SS-552\nActivity: Universal Studios Singapore\nActivity Date: 03 Feb 2027\nNumber of Guests: 2 Adults',
                'table': 'SIGHTSEEING VOUCHER\nGuest\nSunita Rao\nBooking Reference\nSGT-SS-552\nActivity\nUniversal Studios Singapore\nActivity Date\n03 Feb 2027\nGuests\n2 Adults',
                'expected': {'Guest Name': 'Sunita Rao', 'Booking Reference': 'SGT-SS-552', 'Tour / Activity Name': 'Universal Studios Singapore', 'Activity Date': '03 Feb 2027', 'Number of Guests': '2 Adults'}
            },
            'Arrival / Entry Document': {
                'single': 'ARRIVAL / ENTRY DOCUMENT\nTraveller: Sunita Rao\nTrip: Singapore Leisure Tour\nDestination: Singapore\nArrival Date: 01 Feb 2027\nDeparture Date: 10 Feb 2027\nReference Number: SG-ARR-8831',
                'table': 'ARRIVAL / ENTRY DOCUMENT\nTraveller\nSunita Rao\nTrip\nSingapore Leisure Tour\nDestination\nSingapore\nArrival Date\n01 Feb 2027\nDeparture Date\n10 Feb 2027\nReference\nSG-ARR-8831',
                'expected': {'Traveller Name': 'Sunita Rao', 'Trip Name': 'Singapore Leisure Tour', 'Destination': 'Singapore', 'Arrival Date': '01 Feb 2027', 'Departure Date': '10 Feb 2027', 'Reference Number': 'SG-ARR-8831'}
            },
            'Itinerary': {
                'single': 'TOUR ITINERARY\nDestination: Singapore\n01 Feb 2027: Arrival and Check-in\n05 Feb 2027: City Tour\n10 Feb 2027: Departure flight',
                'table': 'TOUR ITINERARY\nDestination\nSingapore\n01 Feb 2027: Arrival and Check-in\n05 Feb 2027: City Tour\n10 Feb 2027: Departure flight',
                'expected': {'Trip Destination': 'Singapore', 'Start Date': '01 Feb 2027', 'End Date': '10 Feb 2027'}
            }
        }

        for dtype, cinfo in cases.items():
            for layout in ['single', 'table']:
                text = cinfo[layout]
                data, conf, det_type, det_conf = parse_passport_text(text)
                self.assertEqual(det_type, dtype, f"Classification failed for {dtype} [{layout}]")
                for exp_k, exp_v in cinfo['expected'].items():
                    act_v = data.get(exp_k)
                    self.assertEqual(act_v, exp_v, f"Field '{exp_k}' failed in {dtype} [{layout}]: expected '{exp_v}', got '{act_v}'")

    def test_edge_cases(self):
        """C. Edge Cases: Missing fields, repeated labels, blank values, value containing keyword, disclaimers"""
        # 1. Missing field remains blank
        partial_hotel = 'HOTEL VOUCHER\nHotel: Grand Hyatt\nGuest: Rajesh Khanna\nCheck-in: 15 Mar 2027'
        data, conf, det_type, _ = parse_passport_text(partial_hotel)
        self.assertEqual(data.get('Guest Name'), 'Rajesh Khanna')
        self.assertEqual(data.get('Check-in Date'), '15 Mar 2027')
        self.assertEqual(data.get('Check-out Date'), '')  # Absent
        self.assertEqual(data.get('Booking Confirmation Number'), '')  # Absent
        self.assertEqual(data.get('Room Type'), '')  # Absent

        # 2. Value containing a field keyword (e.g. Hotel with 'Room' or 'Hotel' in the name)
        hotel_with_kw = 'HOTEL VOUCHER\nHotel: The Room & Suite Grand Hotel\nGuest: Alice Wonderland\nCheck-in: 01 Apr 2027\nCheck-out: 05 Apr 2027\nRoom: Superior Suite'
        data, _, _, _ = parse_passport_text(hotel_with_kw)
        self.assertEqual(data.get('Hotel Name'), 'The Room & Suite Grand Hotel')
        self.assertEqual(data.get('Room Type'), 'Superior Suite')

        # 3. Repeated label (first valid should be kept)
        repeated_label = 'HOTEL VOUCHER\nHotel: First Hotel\nHotel: Second Hotel\nGuest: John Doe\nCheck-in: 10 May 2027\nCheck-out: 12 May 2027'
        data, _, _, _ = parse_passport_text(repeated_label)
        self.assertEqual(data.get('Hotel Name'), 'First Hotel')

        # 4. Document disclaimer stripping
        text_with_disclaimer = 'HOTEL VOUCHER\nHotel: Safe Haven\nGuest: Bruce Wayne\nCheck-in: 01 Jun 2027\nCheck-out: 02 Jun 2027\nPrototype notice:\n This is synthetic.\n!No real reservation.'
        data, _, _, _ = parse_passport_text(text_with_disclaimer)
        self.assertEqual(data.get('Hotel Name'), 'Safe Haven')
        self.assertEqual(data.get('Guest Name'), 'Bruce Wayne')
        self.assertNotIn('Prototype', ' '.join(data.values()))

        # 5. Unsupported document text returns Needs Review
        unsupported = 'SOME RANDOM MEMO\nTitle: Office supplies memo\nDate: 01 Jan 2027\nAuthor: John'
        data, conf, det_type, det_conf = parse_passport_text(unsupported)
        self.assertEqual(det_type, 'Needs Review')
        self.assertEqual(det_conf, 'low')

if __name__ == '__main__':
    unittest.main()
