"""
Phase 7B Regression Test Suite: Legacy Document Data Recovery (Extraction Preview)
Khanna Travels - KT Vault V3
"""

import os
import sys
import shutil
import sqlite3
import hashlib
import json
import unittest

from streamlit.testing.v1 import AppTest
import database

PROD_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase7b_sandbox.db')
BASELINE_SHA256 = 'dbf00a0b578d55a9f5c2c33e069fa365d8386af2cb5b307c20451dfac0dbec25'
BASELINE_SIZE = 102400

def get_prod_checksum():
    h = hashlib.sha256()
    with open(PROD_DB_PATH, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(PROD_DB_PATH)


class Phase7BDataRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Verify production DB baseline
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size mismatch: {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB hash mismatch: {sha} != {BASELINE_SHA256}"
        
        # 2. Create isolated sandbox database for synthetic edge case tests
        shutil.copy2(PROD_DB_PATH, SANDBOX_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        # Clean up sandbox DB
        if os.path.exists(SANDBOX_DB_PATH):
            try:
                os.remove(SANDBOX_DB_PATH)
            except Exception:
                pass
                
        # Final prod DB verification
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size changed! {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB SHA256 changed! {sha} != {BASELINE_SHA256}"

    def test_01_neha_flight_ticket_preview(self):
        """Case 1: Neha Kapoor's Singapore Flight Ticket preview displays extracted fields and missing fields."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-4c9a4d78'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        btn_labels = [b.label.encode('ascii', 'replace').decode('ascii') for b in at.button]
        self.assertIn("Preview Extracted Information", btn_labels)
        
        # Click Preview Extracted Information
        at.button(key='preview_btn_DOC-4c9a4d78').click().run()
        self.assertEqual(len(at.exception), 0)
        
        md_text = "\n".join(m.value for m in at.markdown)
        self.assertIn("Extracted Preview — Not Saved or Verified", md_text)
        self.assertIn("Detected Document Type:** `Flight Ticket`", md_text)
        self.assertIn("Missing Fields (4):</strong> Airline, Flight Number, Origin, Destination", md_text)
        
        # Check text inputs
        ti_vals = {ti.label: ti.value for ti in at.text_input}
        self.assertEqual(ti_vals.get("Passenger Name [Extracted]"), "Neha Kapoor")
        self.assertEqual(ti_vals.get("PNR/Booking Reference [Extracted]"), "KT-DEMO-FLT-3002")
        self.assertEqual(ti_vals.get("Route [Extracted]"), "Mumbai (BOM) - Singapore (SIN) - Mumbai (BOM)")
        self.assertEqual(ti_vals.get("Departure Date/Time [Extracted]"), "20 Jan 2027")
        self.assertEqual(ti_vals.get("Arrival Date/Time [Extracted]"), "26 Jan 2027")
        self.assertEqual(ti_vals.get("Cabin Class [Extracted]"), "Economy - DEMO")
        self.assertEqual(ti_vals.get("Airline [Missing]"), "[Not Extracted / Missing in Document]")
        self.assertEqual(ti_vals.get("Flight Number [Missing]"), "[Not Extracted / Missing in Document]")
        
        # All inputs must be disabled
        for ti in at.text_input:
            if "preview_field_" in ti.key:
                self.assertTrue(ti.disabled)

    def test_02_amit_flight_ticket_preview(self):
        """Case 2: Amit Mehta's Dubai Flight Ticket preview displays extracted fields and missing fields."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-6f58596d'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        at.button(key='preview_btn_DOC-6f58596d').click().run()
        self.assertEqual(len(at.exception), 0)
        
        md_text = "\n".join(m.value for m in at.markdown)
        self.assertIn("Extracted Preview — Not Saved or Verified", md_text)
        self.assertIn("Detected Document Type:** `Flight Ticket`", md_text)
        
        ti_vals = {ti.label: ti.value for ti in at.text_input}
        self.assertEqual(ti_vals.get("Passenger Name [Extracted]"), "Amit Mehta")
        self.assertEqual(ti_vals.get("PNR/Booking Reference [Extracted]"), "KTDEMO-DXB-4812")
        self.assertEqual(ti_vals.get("Route [Extracted]"), "Mumbai - Dubai - Mumbai")
        self.assertEqual(ti_vals.get("Departure Date/Time [Extracted]"), "12 Dec 2026")
        self.assertEqual(ti_vals.get("Arrival Date/Time [Extracted]"), "18 Dec 2026")
        self.assertEqual(ti_vals.get("Cabin Class [Extracted]"), "Economy - Demo")
        self.assertEqual(ti_vals.get("Airline [Missing]"), "[Not Extracted / Missing in Document]")
        self.assertEqual(ti_vals.get("Flight Number [Missing]"), "[Not Extracted / Missing in Document]")

    def test_03_modern_document_with_saved_fields(self):
        """Case 3: A modern document with saved extracted fields does not show the preview button."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-ab6d8384' # Neha's Visa
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        btn_labels = [b.label.encode('ascii', 'replace').decode('ascii') for b in at.button]
        self.assertNotIn("Preview Extracted Information", btn_labels)
        
        ti_labels = [ti.label for ti in at.text_input]
        self.assertIn("Full Name", ti_labels)
        self.assertIn("Date of Birth", ti_labels)

    def test_04_missing_file_handling(self):
        """Case 4: A document whose file is missing on disk displays an error gracefully."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path, extracted_data)
                VALUES ('DOC-SYNTH-MISSING', 'REQ-T-01', 'Verified', 'documents/missing_ticket.pdf', '{}')
            """)
            conn.commit()
            conn.close()
            
            at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at.query_params['doc_id'] = 'DOC-SYNTH-MISSING'
            at.run()
            self.assertEqual(len(at.exception), 0)
            
            # Click Preview button
            at.button(key='preview_btn_DOC-SYNTH-MISSING').click().run()
            self.assertEqual(len(at.exception), 0)
            
            err_texts = [e.value for e in at.error]
            self.assertTrue(any("missing or inaccessible" in e for e in err_texts))
        finally:
            database.DB_PATH = orig_db

    def test_05_incomplete_extraction_identified(self):
        """Case 5: A document with incomplete extraction highlights missing fields and does not auto-populate."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-4c9a4d78'
        at.run()
        at.button(key='preview_btn_DOC-4c9a4d78').click().run()
        
        # Verify missing fields callout
        md_text = "\n".join(m.value for m in at.markdown)
        self.assertIn("Missing Fields (4):</strong> Airline, Flight Number, Origin, Destination", md_text)
        
        # Verify missing fields are not auto-populated with fictitious data
        ti_vals = {ti.label: ti.value for ti in at.text_input}
        self.assertEqual(ti_vals["Airline [Missing]"], "[Not Extracted / Missing in Document]")
        self.assertEqual(ti_vals["Flight Number [Missing]"], "[Not Extracted / Missing in Document]")
        self.assertEqual(ti_vals["Origin [Missing]"], "[Not Extracted / Missing in Document]")
        self.assertEqual(ti_vals["Destination [Missing]"], "[Not Extracted / Missing in Document]")

    def test_06_incorrect_detected_type_warning(self):
        """Case 6: A document with incorrect detected type displays mismatch warning."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            # Create a requirement named "Flight Ticket - Paris" but point it to Hotel Voucher PDF
            conn.execute("""
                INSERT OR REPLACE INTO requirements (id, trip_id, name, type)
                VALUES ('REQ-SYNTH-FLIGHT', 'KT-T-0001', 'Flight Ticket - Paris', 'flight')
            """)
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path, extracted_data)
                VALUES ('DOC-SYNTH-MISMATCH', 'REQ-SYNTH-FLIGHT', 'Verified', 'documents/04_Dubai_Hotel_Voucher.pdf', '{}')
            """)
            conn.commit()
            conn.close()
            
            at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at.query_params['doc_id'] = 'DOC-SYNTH-MISMATCH'
            at.run()
            self.assertEqual(len(at.exception), 0)
            
            at.button(key='preview_btn_DOC-SYNTH-MISMATCH').click().run()
            self.assertEqual(len(at.exception), 0)
            
            # Should identify Hotel Voucher and warn about mismatch with Flight Ticket requirement
            warnings = [w.value for w in at.warning]
            self.assertTrue(any("Detected Document Type Mismatch" in w for w in warnings))
            self.assertTrue(any("Hotel Voucher" in w and "Flight Ticket - Paris" in w for w in warnings))
        finally:
            database.DB_PATH = orig_db

    def test_07_cross_customer_and_security_isolation(self):
        """Case 7: Path traversal and cross-customer security isolation."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path, extracted_data)
                VALUES ('DOC-SYNTH-TRAVERSAL', 'REQ-T-01', 'Verified', '../services.py', '{}')
            """)
            conn.commit()
            conn.close()
            
            at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at.query_params['doc_id'] = 'DOC-SYNTH-TRAVERSAL'
            at.run()
            self.assertEqual(len(at.exception), 0)
            
            at.button(key='preview_btn_DOC-SYNTH-TRAVERSAL').click().run()
            self.assertEqual(len(at.exception), 0)
            
            err_texts = [e.value for e in at.error]
            self.assertTrue(any("outside the approved document storage directory" in e for e in err_texts))
        finally:
            database.DB_PATH = orig_db

    def test_08_cancel_and_close_preview_behavior(self):
        """Case 8: Closing the preview cleanly restores the un-previewed state."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-4c9a4d78'
        at.run()
        
        # 1. Open preview
        at.button(key='preview_btn_DOC-4c9a4d78').click().run()
        btn_labels_open = [b.label.encode('ascii', 'replace').decode('ascii') for b in at.button]
        self.assertIn("Close Preview", btn_labels_open)
        
        # 2. Close preview
        at.button(key='close_preview_btn_DOC-4c9a4d78').click().run()
        self.assertEqual(len(at.exception), 0)
        
        btn_labels_closed = [b.label.encode('ascii', 'replace').decode('ascii') for b in at.button]
        self.assertIn("Preview Extracted Information", btn_labels_closed)
        self.assertNotIn("Close Preview", btn_labels_closed)
        
        md_text = "\n".join(m.value for m in at.markdown)
        self.assertNotIn("Extracted Preview — Not Saved or Verified", md_text)

    def test_09_no_changes_to_verification_history_or_status(self):
        """Case 9: Document verification status and history are unchanged."""
        conn = sqlite3.connect(f'file:{PROD_DB_PATH}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        
        doc_neha = conn.execute("SELECT status, extracted_data FROM documents WHERE id = 'DOC-4c9a4d78'").fetchone()
        doc_amit = conn.execute("SELECT status, extracted_data FROM documents WHERE id = 'DOC-6f58596d'").fetchone()
        
        hist_neha = conn.execute("SELECT COUNT(*) as c FROM document_history WHERE document_id = 'DOC-4c9a4d78'").fetchone()['c']
        hist_amit = conn.execute("SELECT COUNT(*) as c FROM document_history WHERE document_id = 'DOC-6f58596d'").fetchone()['c']
        conn.close()
        
        self.assertEqual(doc_neha['status'], 'Verified')
        self.assertEqual(doc_neha['extracted_data'], '{}')
        self.assertEqual(hist_neha, 0)
        
        self.assertEqual(doc_amit['status'], 'Verified')
        self.assertEqual(doc_amit['extracted_data'], '{}')
        self.assertEqual(hist_amit, 0)

    def test_10_production_database_remains_unchanged(self):
        """Case 10: Production database size and SHA256 checksum remain identical."""
        sha, sz = get_prod_checksum()
        self.assertEqual(sz, BASELINE_SIZE)
        self.assertEqual(sha, BASELINE_SHA256)


if __name__ == '__main__':
    unittest.main()
