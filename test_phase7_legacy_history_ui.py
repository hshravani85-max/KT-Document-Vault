"""
Phase 7 Regression Test Suite: Legacy Verification History UI Repair
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
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase7_sandbox.db')
BASELINE_SHA256 = 'dbf00a0b578d55a9f5c2c33e069fa365d8386af2cb5b307c20451dfac0dbec25'
BASELINE_SIZE = 102400

def get_prod_checksum():
    h = hashlib.sha256()
    with open(PROD_DB_PATH, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(PROD_DB_PATH)


class Phase7LegacyHistoryUITests(unittest.TestCase):
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

    def test_01_neha_flight_ticket_displays_legacy_activity_event(self):
        """Case 1: Neha Kapoor's legacy verified Flight Ticket displays historical Activity event."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-4c9a4d78'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        markdown_text = "\n".join(m.value for m in at.markdown)
        
        # Must show Legacy Verification Record with recorded timestamp
        self.assertIn("Legacy Verification Record", markdown_text)
        self.assertIn("Verified on: 2026-10-09 16:58:48", markdown_text)
        self.assertIn("Source: Historical Activity Log", markdown_text)
        self.assertIn("This verification predates the current document history system.", markdown_text)
        
        # Must not fabricate an actor line since activity doesn't have actor column
        self.assertNotIn("Actor: None", markdown_text)

    def test_02_amit_flight_ticket_displays_legacy_activity_event(self):
        """Case 2: Amit Mehta's legacy verified Flight Ticket displays historical Activity event."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-6f58596d'
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        markdown_text = "\n".join(m.value for m in at.markdown)
        
        # Must show Legacy Verification Record with recorded timestamp
        self.assertIn("Legacy Verification Record", markdown_text)
        self.assertIn("Verified on: 2026-10-03 06:49:47", markdown_text)
        self.assertIn("Source: Historical Activity Log", markdown_text)
        self.assertIn("This verification predates the current document history system.", markdown_text)

    def test_03_modern_document_with_genuine_history_displays_without_duplication(self):
        """Case 3: A modern document with genuine document_history records displays original history without duplication."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-ab6d8384' # Neha's Visa with genuine document_history
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        markdown_text = "\n".join(m.value for m in at.markdown)
        
        # Must display genuine history entry
        self.assertIn("VERIFY - Actor: System Administrator - Reason: Verification completed", markdown_text)
        self.assertIn("2026-10-10 07:57:41", markdown_text)
        
        # Must NOT display Legacy Verification Record
        self.assertNotIn("Legacy Verification Record", markdown_text)
        self.assertNotIn("Source: Historical Activity Log", markdown_text)

    def test_04_unverified_document_without_history_no_fabricated_verification(self):
        """Case 4: An unverified document without history does not display a fabricated verification."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-f7ad49b6' # Under Review Arrival Doc
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        markdown_text = "\n".join(m.value for m in at.markdown)
        
        # Must NOT display any verification record
        self.assertNotIn("Legacy Verification Record", markdown_text)
        self.assertNotIn("Source: Historical Activity Log", markdown_text)
        self.assertNotIn("✓ Verified", markdown_text)

    def test_05_verified_document_without_activity_event_honest_fallback(self):
        """Case 5: A verified document without any matching historical Activity event displays an honest fallback."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            # Create a synthetic verified document in sandbox with NO activity records
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES ('DOC-SYNTH-NOACT', 'REQ-T-01', 'Verified', '{}')")
            conn.commit()
            conn.close()
            
            at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at.query_params['doc_id'] = 'DOC-SYNTH-NOACT'
            at.run()
            
            self.assertEqual(len(at.exception), 0)
            markdown_text = "\n".join(m.value for m in at.markdown)
            
            # Must NOT fabricate a verification record
            self.assertNotIn("Legacy Verification Record", markdown_text)
            self.assertNotIn("Source: Historical Activity Log", markdown_text)
        finally:
            database.DB_PATH = orig_db

    def test_06_activity_records_for_other_docs_never_displayed(self):
        """Case 6: Activity records referencing other document IDs are never displayed."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            # Create DOC-A (Verified) and an activity record only for DOC-B
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES ('DOC-AAA-01', 'REQ-T-01', 'Verified', '{}')")
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES ('KT-T-0001', 'Document DOC-BBB-02 verified', '2026-10-01 10:00:00')")
            conn.commit()
            conn.close()
            
            at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at.query_params['doc_id'] = 'DOC-AAA-01'
            at.run()
            
            self.assertEqual(len(at.exception), 0)
            markdown_text = "\n".join(m.value for m in at.markdown)
            
            # Must NOT display DOC-BBB's activity timestamp
            self.assertNotIn("2026-10-01 10:00:00", markdown_text)
            self.assertNotIn("Legacy Verification Record", markdown_text)
        finally:
            database.DB_PATH = orig_db

    def test_07_empty_extracted_information_described_accurately(self):
        """Case 7: Empty extracted information is described accurately (legacy vs unverified)."""
        # 1. Legacy verified document:
        at_legacy = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at_legacy.query_params['doc_id'] = 'DOC-4c9a4d78'
        at_legacy.run()
        
        markdown_legacy = "\n".join(m.value for m in at_legacy.markdown)
        info_legacy = "\n".join(inf.value for inf in at_legacy.info)
        
        self.assertIn("Extracted Information Not Available", markdown_legacy)
        self.assertIn("This document was saved before the current extraction workflow. Its original file is preserved, but structured extracted information was not stored.", info_legacy)
        self.assertNotIn("Re-extract information or enter details for review", "\n".join(w.value for w in at_legacy.warning))
        
        # 2. In-progress unverified document with empty data in sandbox:
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data) VALUES ('DOC-SYNTH-REVIEW', 'REQ-T-01', 'Under Review', '{}')")
            conn.commit()
            conn.close()
            
            at_unverified = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
            at_unverified.query_params['doc_id'] = 'DOC-SYNTH-REVIEW'
            at_unverified.run()
            
            warning_unverified = "\n".join(w.value for w in at_unverified.warning)
            self.assertIn("No extracted information is saved for this document. Re-extract information or enter details for review.", warning_unverified)
        finally:
            database.DB_PATH = orig_db

    def test_08_existing_extracted_information_displays_correctly(self):
        """Case 8: Existing extracted information continues to display correctly in disabled inputs."""
        at = AppTest.from_file(os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py'))
        at.query_params['doc_id'] = 'DOC-ab6d8384' # Neha's Visa
        at.run()
        
        self.assertEqual(len(at.exception), 0)
        labels = [ti.label for ti in at.text_input]
        values = {ti.label: ti.value for ti in at.text_input}
        
        self.assertIn("Full Name", labels)
        self.assertIn("Date of Birth", labels)
        self.assertIn("Expiry Date", labels)
        self.assertIn("Neha Kapoor", values["Full Name"])
        self.assertEqual(values["Date of Birth"], "12 Jun 1993")
        self.assertEqual(values["Expiry Date"], "15 Feb 2027")

    def test_09_verification_status_remains_unchanged(self):
        """Case 9: Document verification statuses in the database remain unchanged."""
        conn = sqlite3.connect(f'file:{PROD_DB_PATH}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        
        doc_neha = conn.execute("SELECT status FROM documents WHERE id = 'DOC-4c9a4d78'").fetchone()
        doc_amit = conn.execute("SELECT status FROM documents WHERE id = 'DOC-6f58596d'").fetchone()
        conn.close()
        
        self.assertEqual(doc_neha['status'], 'Verified')
        self.assertEqual(doc_amit['status'], 'Verified')

    def test_10_production_database_remains_unchanged(self):
        """Case 10: Production database size and SHA256 checksum remain identical."""
        sha, sz = get_prod_checksum()
        self.assertEqual(sz, BASELINE_SIZE)
        self.assertEqual(sha, BASELINE_SHA256)


if __name__ == '__main__':
    unittest.main()
