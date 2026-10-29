"""
Phase 6 Regression Test Suite: Smart Upload Stabilization and Ownership Validation
Khanna Travels - KT Vault V3
"""

import os
import sys
import shutil
import sqlite3
import hashlib
import json
import uuid
import unittest
from datetime import datetime

# Streamlit AppTest
from streamlit.testing.v1 import AppTest

# Target modules
import database
import auth_services
import services

PROD_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase6_sandbox.db')
BASELINE_SHA256 = '000bfbe80c7e11b2e11a498a7fedafe6330c73a91721512650a0ce5b42b710c0'
BASELINE_SIZE = 102400

def get_prod_checksum():
    h = hashlib.sha256()
    with open(PROD_DB_PATH, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(PROD_DB_PATH)


class Phase6SmartUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Verify production DB baseline
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size mismatch: {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB hash mismatch: {sha} != {BASELINE_SHA256}"
        
        # 2. Create sandbox database for write tests
        shutil.copy2(PROD_DB_PATH, SANDBOX_DB_PATH)
        
        # 3. Create a dummy file for file-existence tests
        cls.dummy_file = os.path.join(os.path.dirname(__file__), 'documents', 'test_dummy_doc.pdf')
        os.makedirs(os.path.dirname(cls.dummy_file), exist_ok=True)
        with open(cls.dummy_file, 'wb') as f:
            f.write(b"%PDF-1.4 test dummy content")
            
        # 4. Generate staff token in sandbox DB
        conn = sqlite3.connect(SANDBOX_DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT id, role, full_name FROM users WHERE role = 'Staff'").fetchone()
        cls.staff_token = "test_staff_token_" + uuid.uuid4().hex
        expires = (datetime.now()).replace(year=2030).isoformat()
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (cls.staff_token, user['id'], expires))
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        # Clean up sandbox DB and dummy file
        if os.path.exists(SANDBOX_DB_PATH):
            try:
                os.remove(SANDBOX_DB_PATH)
            except Exception:
                pass
        if os.path.exists(cls.dummy_file):
            try:
                os.remove(cls.dummy_file)
            except Exception:
                pass
                
        # Final prod DB verification
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size changed! {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB SHA256 changed! {sha} != {BASELINE_SHA256}"

    def setUp(self):
        # Redirect database.DB_PATH to sandbox for safety
        self._orig_db_path = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH

    def tearDown(self):
        database.DB_PATH = self._orig_db_path

    # =========================================================================
    # BACKEND / SERVICE TESTS: Server-Side Customer/Trip Ownership Validation
    # =========================================================================

    def test_01_save_document_rejects_trip_mismatch(self):
        """Mismatched requirement and trip ID must be rejected before write."""
        # REQ-T-01 belongs to trip KT-T-0001 (Amit Mehta - Dubai)
        with self.assertRaises(ValueError) as ctx:
            services.save_document(
                requirement_id='REQ-T-01',
                file_path=self.dummy_file,
                extracted_data={'Passenger Name': 'Test'},
                session_token=self.staff_token,
                expected_trip_id='KT-T-0002', # Neha's trip
                expected_customer_id='KT-C-0001'
            )
        self.assertIn("Trip mismatch", str(ctx.exception))

    def test_02_save_document_rejects_customer_mismatch(self):
        """Mismatched requirement and customer ID must be rejected before write."""
        # REQ-T-01 belongs to customer KT-C-0001
        with self.assertRaises(ValueError) as ctx:
            services.save_document(
                requirement_id='REQ-T-01',
                file_path=self.dummy_file,
                extracted_data={'Passenger Name': 'Test'},
                session_token=self.staff_token,
                expected_trip_id='KT-T-0001',
                expected_customer_id='KT-C-0002' # Wrong customer (Neha)
            )
        self.assertIn("Customer mismatch", str(ctx.exception))

    def test_03_save_document_rejects_nonexistent_requirement(self):
        """Nonexistent requirement must be rejected."""
        with self.assertRaises(ValueError) as ctx:
            services.save_document(
                requirement_id='REQ-NONEXISTENT',
                file_path=self.dummy_file,
                extracted_data={'Passenger Name': 'Test'},
                session_token=self.staff_token,
                expected_trip_id='KT-T-0001',
                expected_customer_id='KT-C-0001'
            )
        self.assertIn("Requirement not found", str(ctx.exception))

    def test_04_save_document_rejects_missing_file_on_disk(self):
        """Nonexistent file path must be rejected safely."""
        with self.assertRaises(ValueError) as ctx:
            services.save_document(
                requirement_id='REQ-T-01',
                file_path=r'C:\KT_Vault_V3\documents\nonexistent_file_12345.pdf',
                extracted_data={'Passenger Name': 'Test'},
                session_token=self.staff_token,
                expected_trip_id='KT-T-0001',
                expected_customer_id='KT-C-0001'
            )
        self.assertIn("Document file does not exist on disk", str(ctx.exception))

    def test_05_save_document_rejects_invalid_extracted_data_type(self):
        """extracted_data must be a valid dictionary."""
        with self.assertRaises(ValueError) as ctx:
            services.save_document(
                requirement_id='REQ-T-01',
                file_path=self.dummy_file,
                extracted_data="not a dict",
                session_token=self.staff_token,
                expected_trip_id='KT-T-0001',
                expected_customer_id='KT-C-0001'
            )
        self.assertIn("extracted_data must be a valid dictionary", str(ctx.exception))

    def test_06_save_document_rejects_unauthenticated(self):
        """Unauthenticated caller must be rejected with PermissionError."""
        with self.assertRaises(PermissionError):
            services.save_document(
                requirement_id='REQ-T-01',
                file_path=self.dummy_file,
                extracted_data={'Passenger Name': 'Test'},
                session_token=None
            )

    def test_07_save_document_backward_compatibility(self):
        """Calling save_document without expected_trip_id / customer_id preserves compatibility."""
        doc_id = services.save_document(
            requirement_id='REQ-T-01',
            file_path=self.dummy_file,
            extracted_data={'Passenger Name': 'Amit Mehta', 'Flight Number': 'EK501'},
            session_token=self.staff_token
        )
        self.assertTrue(doc_id.startswith('DOC-'))
        # Verify in sandbox DB
        conn = sqlite3.connect(SANDBOX_DB_PATH)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT * FROM documents WHERE requirement_id = 'REQ-T-01'").fetchone()
        conn.close()
        self.assertIsNotNone(doc)
        self.assertEqual(doc['status'], 'Under Review')

    def test_08_save_document_success_with_ownership_validation(self):
        """Calling save_document with correct expected IDs succeeds and updates records."""
        doc_id = services.save_document(
            requirement_id='REQ-T-11a2f7', # Neha Kapoor Hotel Voucher
            file_path=self.dummy_file,
            extracted_data={'Hotel Name': 'Marina Bay Sands', 'Guest Name': 'Neha Kapoor'},
            session_token=self.staff_token,
            expected_trip_id='KT-T-0002',
            expected_customer_id='KT-C-0002'
        )
        self.assertTrue(doc_id.startswith('DOC-'))
        conn = sqlite3.connect(SANDBOX_DB_PATH)
        conn.row_factory = sqlite3.Row
        doc = conn.execute("SELECT * FROM documents WHERE requirement_id = 'REQ-T-11a2f7'").fetchone()
        conn.close()
        self.assertIsNotNone(doc)
        data = json.loads(doc['extracted_data'])
        self.assertEqual(data.get('Hotel Name'), 'Marina Bay Sands')

    # =========================================================================
    # UI & SESSION-STATE TESTS: Streamlit AppTest Workflows
    # =========================================================================

    def test_09_smart_upload_neha_hotel_voucher_fresh_screen(self):
        """Neha Kapoor Hotel Voucher opens fresh Step 1 with versioned uploader key."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at.session_state['upload_req_id'] = 'REQ-T-11a2f7' # Neha Hotel Voucher
        at.session_state['upload_trip_id'] = 'KT-T-0002'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state['upload_step'], 1)
        self.assertEqual(at.session_state['active_upload_req_id'], 'REQ-T-11a2f7')
        self.assertEqual(at.session_state['active_upload_trip_id'], 'KT-T-0002')
        self.assertEqual(at.session_state['active_upload_customer_id'], 'KT-C-0002')
        self.assertEqual(len(at.file_uploader), 1)
        self.assertTrue(at.file_uploader[0].key.startswith('file_uploader_REQ-T-11a2f7_'))

    def test_10_smart_upload_cancel_resets_and_clears_state(self):
        """Cancel button in Step 3 clears extracted results and resets upload context."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at.session_state['upload_req_id'] = 'REQ-T-11a2f7'
        at.session_state['upload_trip_id'] = 'KT-T-0002'
        at.session_state['active_upload_req_id'] = 'REQ-T-11a2f7'
        at.session_state['active_upload_trip_id'] = 'KT-T-0002'
        at.session_state['active_upload_customer_id'] = 'KT-C-0002'
        at.session_state['upload_step'] = 3
        at.session_state['upload_instance_id'] = 'test_inst_1'
        at.session_state['extracted_result'] = {
            'document_type': 'Hotel Voucher',
            'type_confidence': 'high',
            'extracted_fields': {'Hotel Name': 'Marina Bay Sands', 'Guest Name': 'Neha Kapoor'}
        }
        at.session_state['smart_upload_confirmed_type'] = 'Hotel Voucher'
        at.session_state['smart_up_test_inst_1_Hotel Voucher_Hotel Name'] = 'Marina Bay Sands'
        at.run()
        
        # Verify Review screen is rendered with Cancel button
        self.assertEqual(len(at.exception), 0)
        cancel_btn = [b for b in at.button if b.label == "Cancel"]
        self.assertEqual(len(cancel_btn), 1)
        
        # Click Cancel
        cancel_btn[0].click()
        at.run()
        
        # Check that state was completely reset and navigated to trip_workspace
        self.assertEqual(at.session_state.get('upload_step'), 1)
        self.assertIsNone(at.session_state.get('extracted_result'))
        self.assertIsNone(at.session_state.get('smart_upload_confirmed_type'))
        self.assertNotIn('upload_req_id', at.session_state)
        trip_param = at.query_params.get('trip_id')
        actual_trip_id = trip_param[0] if isinstance(trip_param, list) else trip_param
        self.assertEqual(actual_trip_id, 'KT-T-0002')

    def test_11_smart_upload_customer_switch_isolation(self):
        """Switching from Neha Kapoor to Amit Mehta invalidates stale upload state."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        # Simulate active state belonged to Neha Kapoor
        at.session_state['active_upload_req_id'] = 'REQ-T-11a2f7'
        at.session_state['active_upload_trip_id'] = 'KT-T-0002'
        at.session_state['active_upload_customer_id'] = 'KT-C-0002'
        at.session_state['upload_step'] = 3
        at.session_state['extracted_result'] = {
            'document_type': 'Hotel Voucher',
            'type_confidence': 'high',
            'extracted_fields': {'Hotel Name': 'Marina Bay Sands', 'Guest Name': 'Neha Kapoor'}
        }
        at.session_state['smart_upload_confirmed_type'] = 'Hotel Voucher'
        
        # Now a new upload request comes in for Amit Mehta (REQ-T-01: Flight Ticket)
        at.session_state['upload_req_id'] = 'REQ-T-01'
        at.session_state['upload_trip_id'] = 'KT-T-0001'
        
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        # Context guard must have triggered
        self.assertEqual(at.session_state['upload_step'], 1)
        self.assertIsNone(at.session_state.get('extracted_result'))
        self.assertIsNone(at.session_state.get('smart_upload_confirmed_type'))
        self.assertEqual(at.session_state['active_upload_req_id'], 'REQ-T-01')
        self.assertEqual(at.session_state['active_upload_trip_id'], 'KT-T-0001')
        self.assertEqual(at.session_state['active_upload_customer_id'], 'KT-C-0001')
        # Check that file uploader is rendered for Amit with fresh key
        self.assertEqual(len(at.file_uploader), 1)
        self.assertTrue(at.file_uploader[0].key.startswith('file_uploader_REQ-T-01_'))

    def test_12_smart_upload_change_document_type_during_review(self):
        """Changing document type during review immediately refreshes schema and clears old fields."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at.session_state['upload_req_id'] = 'REQ-T-01'
        at.session_state['upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_req_id'] = 'REQ-T-01'
        at.session_state['active_upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_customer_id'] = 'KT-C-0001'
        at.session_state['upload_step'] = 3
        at.session_state['upload_instance_id'] = 'inst_change_type'
        at.session_state['extracted_result'] = {
            'document_type': 'Needs Review',
            'type_confidence': 'low',
            'extracted_fields': {'Passenger Name': 'Amit Mehta', 'Booking Reference': 'XYZ123'}
        }
        at.run()
        
        # Selectbox should be present
        self.assertEqual(len(at.selectbox), 1)
        # Change to Hotel Voucher
        at.selectbox[0].select('Hotel Voucher')
        at.run()
        
        # Verify confirmed type changed and schema updated
        self.assertEqual(at.session_state['smart_upload_confirmed_type'], 'Hotel Voucher')
        self.assertEqual(at.session_state['extracted_result']['document_type'], 'Hotel Voucher')
        # Check that Guest Name was mapped from Passenger Name alias
        self.assertEqual(at.session_state['extracted_result']['extracted_fields'].get('Guest Name'), 'Amit Mehta')
        self.assertEqual(at.session_state['extracted_result']['extracted_fields'].get('Booking Confirmation Number'), 'XYZ123')

    def test_13_smart_upload_normal_rerun_preserves_staff_edits(self):
        """Staff edits are preserved during normal Streamlit reruns of the same upload."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at.session_state['upload_req_id'] = 'REQ-T-01'
        at.session_state['upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_req_id'] = 'REQ-T-01'
        at.session_state['active_upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_customer_id'] = 'KT-C-0001'
        at.session_state['upload_step'] = 3
        inst_id = 'inst_edits_test'
        at.session_state['upload_instance_id'] = inst_id
        at.session_state['extracted_result'] = {
            'document_type': 'Flight Ticket',
            'type_confidence': 'high',
            'extracted_fields': {'Passenger Name': 'Amit Mehta', 'Airline': 'Emirates'}
        }
        at.session_state['smart_upload_confirmed_type'] = 'Flight Ticket'
        at.run()
        
        # Modify Passenger Name text input
        passenger_inputs = [ti for ti in at.text_input if ti.label == 'Passenger Name']
        self.assertEqual(len(passenger_inputs), 1)
        passenger_inputs[0].input("Amit Mehta Edited")
        at.run()
        
        # Verify edit persisted
        passenger_inputs_after = [ti for ti in at.text_input if ti.label == 'Passenger Name']
        self.assertEqual(passenger_inputs_after[0].value, "Amit Mehta Edited")

    def test_14_smart_upload_arrival_entry_document_schema(self):
        """Arrival / Entry Document renders correct schema fields."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at.session_state['upload_req_id'] = 'REQ-T-06' # Arrival / Entry Document for Amit
        at.session_state['upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_req_id'] = 'REQ-T-06'
        at.session_state['active_upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_customer_id'] = 'KT-C-0001'
        at.session_state['upload_step'] = 3
        at.session_state['upload_instance_id'] = 'inst_arrival_test'
        at.session_state['extracted_result'] = {
            'document_type': 'Arrival / Entry Document',
            'type_confidence': 'high',
            'extracted_fields': {
                'Traveller Name': 'Amit Mehta',
                'Destination': 'Dubai',
                'Arrival Date': '2026-12-12',
                'Departure Date': '2026-12-18',
                'Reference Number': 'ARR-DXB-9988'
            }
        }
        at.session_state['smart_upload_confirmed_type'] = 'Arrival / Entry Document'
        at.run()
        
        labels = [ti.label for ti in at.text_input]
        self.assertIn('Traveller Name', labels)
        self.assertIn('Destination', labels)
        self.assertIn('Arrival Date', labels)
        self.assertIn('Departure Date', labels)
        self.assertIn('Reference Number', labels)


    def test_15_switch_back_to_neha_kapoor(self):
        """Switching from Amit Mehta back to Neha Kapoor invalidates Amit's state."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        # Simulate active upload belonged to Amit Mehta
        at.session_state['active_upload_req_id'] = 'REQ-T-01'
        at.session_state['active_upload_trip_id'] = 'KT-T-0001'
        at.session_state['active_upload_customer_id'] = 'KT-C-0001'
        at.session_state['upload_step'] = 3
        at.session_state['extracted_result'] = {
            'document_type': 'Flight Ticket',
            'type_confidence': 'high',
            'extracted_fields': {'Passenger Name': 'Amit Mehta', 'Flight Number': 'EK501'}
        }
        at.session_state['smart_upload_confirmed_type'] = 'Flight Ticket'
        
        # User opens Neha Kapoor's requirement
        at.session_state['upload_req_id'] = 'REQ-T-11a2f7'
        at.session_state['upload_trip_id'] = 'KT-T-0002'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state['upload_step'], 1)
        self.assertIsNone(at.session_state.get('extracted_result'))
        self.assertIsNone(at.session_state.get('smart_upload_confirmed_type'))
        self.assertEqual(at.session_state['active_upload_req_id'], 'REQ-T-11a2f7')
        self.assertEqual(at.session_state['active_upload_trip_id'], 'KT-T-0002')
        self.assertEqual(at.session_state['active_upload_customer_id'], 'KT-C-0002')

    def test_16_two_customers_same_document_type(self):
        """Two customers uploading Hotel Voucher maintain completely independent states."""
        # 1. Customer 1 (Amit Mehta - REQ-T-02: Hotel Voucher)
        at1 = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at1.session_state['upload_req_id'] = 'REQ-T-02'
        at1.session_state['upload_trip_id'] = 'KT-T-0001'
        at1.run()
        self.assertEqual(at1.session_state['upload_step'], 1)
        inst_1 = at1.session_state['upload_instance_id']
        
        # 2. Customer 2 (Neha Kapoor - REQ-T-11a2f7: Hotel Voucher)
        at2 = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        at2.session_state['upload_req_id'] = 'REQ-T-11a2f7'
        at2.session_state['upload_trip_id'] = 'KT-T-0002'
        at2.run()
        self.assertEqual(at2.session_state['upload_step'], 1)
        inst_2 = at2.session_state['upload_instance_id']
        
        # Ensure instances and widget keys are unique and isolated
        self.assertNotEqual(inst_1, inst_2)
        self.assertEqual(at1.session_state['active_upload_customer_id'], 'KT-C-0001')
        self.assertEqual(at2.session_state['active_upload_customer_id'], 'KT-C-0002')

    def test_17_navigate_away_and_return_no_abandoned_review(self):
        """Navigating away to an unselected requirement screen resets in-progress review state."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'smart_upload.py'))
        # Simulate an abandoned review state
        at.session_state['active_upload_req_id'] = 'REQ-T-01'
        at.session_state['upload_step'] = 3
        at.session_state['extracted_result'] = {'document_type': 'Flight Ticket'}
        # Navigate without req_id (e.g. from generic top-nav or documents)
        at.session_state['upload_req_id'] = None
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state.get('upload_step'), 1)
        self.assertIsNone(at.session_state.get('extracted_result'))
        self.assertIsNone(at.session_state.get('active_upload_req_id'))

    def test_18_trip_workspace_upload_triggers_purge(self):
        """Trip workspace Add Document triggers fresh upload preparation."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'trip_workspace.py'))
        at.query_params['trip_id'] = 'KT-T-0001'
        # Simulate dirty upload state left behind
        at.session_state['upload_step'] = 3
        at.session_state['extracted_result'] = {'stale': 'data'}
        at.session_state['smart_upload_confirmed_type'] = 'Flight Ticket'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        # Find Add Document or Smart Upload button
        smart_up_btn = [b for b in at.button if b.key == "trip_smart_upload"]
        self.assertEqual(len(smart_up_btn), 1)
        smart_up_btn[0].click()
        at.run()
        
        # Check that state was purged
        self.assertEqual(at.session_state.get('upload_step'), 1)
        self.assertIsNone(at.session_state.get('extracted_result'))
        self.assertIsNone(at.session_state.get('smart_upload_confirmed_type'))
        self.assertEqual(at.session_state.get('nav_page'), 'smart_upload')


if __name__ == '__main__':
    unittest.main()

