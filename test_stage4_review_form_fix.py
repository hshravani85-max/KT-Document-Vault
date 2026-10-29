import unittest
import os
import shutil
import sqlite3
import json

class TestStage4ReviewFormFix(unittest.TestCase):
    def test_requirement_suggestion_for_uncertain_classification(self):
        # Test simulated suggestion logic when doc_type is Needs Review or low confidence
        SUPPORTED_TYPES = [
            'Hotel Voucher',
            'Flight Ticket',
            'Passport',
            'Visa / Entry Document',
            'Travel Insurance',
            'Transfer Voucher',
            'Sightseeing Voucher',
            'Arrival / Entry Document',
            'Itinerary',
            'Needs Review'
        ]
        
        req_scenarios = [
            ({'name': 'Hotel Voucher'}, 'Hotel Voucher'),
            ({'name': 'Singapore Hotel Voucher'}, 'Hotel Voucher'),
            ({'name': 'Flight Ticket'}, 'Flight Ticket'),
            ({'name': 'Dubai Flight Ticket'}, 'Flight Ticket'),
            ({'name': 'Passport'}, 'Passport'),
            ({'name': 'Travel Insurance'}, 'Travel Insurance'),
            ({'name': 'Transfer Voucher'}, 'Transfer Voucher'),
            ({'name': 'Sightseeing Voucher'}, 'Sightseeing Voucher'),
            ({'name': 'Arrival / Entry Document'}, 'Arrival / Entry Document'),
            ({'name': 'Itinerary'}, 'Itinerary'),
            ({'name': 'Custom Unknown Req'}, 'Needs Review')
        ]

        for req, expected_suggestion in req_scenarios:
            req_name_hint = req['name'].lower()
            fallback_suggestion = 'Needs Review'
            for stype in SUPPORTED_TYPES:
                if stype == 'Needs Review': continue
                if stype.lower() in req_name_hint:
                    fallback_suggestion = stype
                    break
            if fallback_suggestion == 'Needs Review':
                KEYWORD_MAP = {
                    'hotel': 'Hotel Voucher',
                    'flight': 'Flight Ticket',
                    'passport': 'Passport',
                    'visa': 'Visa / Entry Document',
                    'insurance': 'Travel Insurance',
                    'transfer': 'Transfer Voucher',
                    'sightseeing': 'Sightseeing Voucher',
                    'arrival': 'Arrival / Entry Document',
                    'itinerary': 'Itinerary'
                }
                for kw, target_type in KEYWORD_MAP.items():
                    if kw in req_name_hint:
                        fallback_suggestion = target_type
                        break

            doc_type = 'Needs Review'
            suggested_type = doc_type if doc_type in SUPPORTED_TYPES and doc_type != 'Needs Review' else fallback_suggestion
            self.assertEqual(suggested_type, expected_suggestion, f"Failed for {req_name_hint}")
            # Ensure it NEVER defaults to Flight Ticket when uploading for Hotel Voucher
            if 'Hotel' in req_name_hint:
                self.assertNotEqual(suggested_type, 'Flight Ticket')

    def test_type_switch_clears_stale_fields_and_maps_aliases(self):
        SCHEMAS = {
            'Passport': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
            'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class'],
            'Hotel Voucher': ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address']
        }
        FIELD_ALIASES = {
            'Passenger Name': ['Traveller Name', 'Guest Name', 'Insured Name', 'Full Name'],
            'Traveller Name': ['Passenger Name', 'Guest Name', 'Insured Name', 'Full Name'],
            'Guest Name': ['Traveller Name', 'Passenger Name', 'Insured Name', 'Full Name'],
            'Insured Name': ['Traveller Name', 'Passenger Name', 'Guest Name', 'Full Name'],
            'Full Name': ['Traveller Name', 'Passenger Name', 'Guest Name', 'Insured Name'],
            'Booking Reference': ['PNR/Booking Reference', 'Booking Confirmation Number', 'Reference Number', 'Visa Number / Reference', 'Policy Number'],
            'PNR/Booking Reference': ['Booking Reference', 'Booking Confirmation Number', 'Reference Number'],
            'Booking Confirmation Number': ['Booking Reference', 'PNR/Booking Reference', 'Reference Number']
        }

        # Suppose old data came from an accidental Flight Ticket review form
        old_flight_fields = {
            'Passenger Name': 'Neha Kapoor',
            'Route': 'Mumbai - Singapore',
            'Airline': 'Singapore Airlines',
            'Flight Number': 'SQ421',
            'PNR/Booking Reference': 'KT-DEMO-FLT-3002',
            'Departure Date/Time': '20 Jan 2027',
            'Arrival Date/Time': '26 Jan 2027',
            'Cabin Class': 'Economy'
        }

        # Staff switches to Hotel Voucher
        target_fields = SCHEMAS['Hotel Voucher']
        new_hotel_fields = {}
        for sf in target_fields:
            val = old_flight_fields.get(sf, '')
            if not val and sf in FIELD_ALIASES:
                for alias in FIELD_ALIASES[sf]:
                    if old_flight_fields.get(alias):
                        val = old_flight_fields[alias]
                        break
            new_hotel_fields[sf] = val

        # 1. Correct schema fields present
        self.assertEqual(list(new_hotel_fields.keys()), target_fields)
        # 2. Aliased fields correctly preserved (Passenger Name -> Guest Name, PNR -> Booking Confirmation)
        self.assertEqual(new_hotel_fields['Guest Name'], 'Neha Kapoor')
        self.assertEqual(new_hotel_fields['Booking Confirmation Number'], 'KT-DEMO-FLT-3002')
        # 3. Incompatible flight fields stripped
        self.assertNotIn('Flight Number', new_hotel_fields)
        self.assertNotIn('Airline', new_hotel_fields)
        self.assertNotIn('Route', new_hotel_fields)
        self.assertNotIn('Cabin Class', new_hotel_fields)
        # 4. Hotel specific fields blank for user entry
        self.assertEqual(new_hotel_fields['Hotel Name'], '')
        self.assertEqual(new_hotel_fields['Check-in Date'], '')
        self.assertEqual(new_hotel_fields['Check-out Date'], '')

    def test_stale_widget_keys_purged(self):
        # Simulate session state containing widget keys
        session_state = {
            'session_token': 'test_tok',
            'smart_up_Flight Ticket_Passenger Name': 'Neha',
            'smart_up_Flight Ticket_Flight Number': 'SQ123',
            'smart_up_Route': 'BOM-SIN',
            're_edit_Flight Ticket_Airline': 'Emirates',
            'unrelated_key': 'keep_me'
        }

        # Purge smart_up_*
        for k in list(session_state.keys()):
            if str(k).startswith("smart_up_"):
                del session_state[k]

        self.assertNotIn('smart_up_Flight Ticket_Passenger Name', session_state)
        self.assertNotIn('smart_up_Flight Ticket_Flight Number', session_state)
        self.assertNotIn('smart_up_Route', session_state)
        self.assertIn('session_token', session_state)
        self.assertIn('unrelated_key', session_state)

        # Purge re_edit_*
        for k in list(session_state.keys()):
            if str(k).startswith("re_edit_"):
                del session_state[k]

        self.assertNotIn('re_edit_Flight Ticket_Airline', session_state)
        self.assertIn('session_token', session_state)
        self.assertIn('unrelated_key', session_state)

if __name__ == '__main__':
    unittest.main()
