"""
Phase 7B Hotfix Test Suite: Actual app.py Page-Loader Execution & Path Resolution Tests
Khanna Travels - KT Vault V3
"""

import os
import sys
import shutil
import sqlite3
import hashlib
import unittest

import streamlit as st
import database
import app

PROD_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase7b_hotfix_sandbox.db')
BASELINE_SHA256 = 'dbf00a0b578d55a9f5c2c33e069fa365d8386af2cb5b307c20451dfac0dbec25'
BASELINE_SIZE = 102400

def get_prod_checksum():
    h = hashlib.sha256()
    with open(PROD_DB_PATH, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(PROD_DB_PATH)


class Phase7BHotfixPageLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Verify baseline DB before tests
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size mismatch: {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB hash mismatch: {sha} != {BASELINE_SHA256}"
        
        # Create sandbox DB for synthetic fixture tests
        shutil.copy2(PROD_DB_PATH, SANDBOX_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(SANDBOX_DB_PATH):
            try:
                os.remove(SANDBOX_DB_PATH)
            except Exception:
                pass
                
        # Final prod DB verification
        sha, sz = get_prod_checksum()
        assert sz == BASELINE_SIZE, f"Prod DB size changed! {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Prod DB SHA256 changed! {sha} != {BASELINE_SHA256}"

    def test_01_neha_flight_ticket_preview_via_page_loader(self):
        """Case 1: Neha Kapoor's Flight Ticket preview loads cleanly through actual app.load_page()."""
        st.query_params['doc_id'] = 'DOC-4c9a4d78'
        st.session_state['preview_mode_DOC-4c9a4d78'] = True
        st.session_state['nav_page'] = 'document_review'
        
        # Must execute without NameError: name '__file__' is not defined
        try:
            app.load_page('document_review')
        except NameError as e:
            self.fail(f"app.load_page failed with NameError: {e}")
        except Exception as e:
            # Rerun exceptions in Streamlit are normal if triggered, but NameError is not
            if "Rerun" not in type(e).__name__:
                self.fail(f"Unexpected exception during load_page: {e}")

    def test_02_amit_flight_ticket_preview_via_page_loader(self):
        """Case 2: Amit Mehta's Flight Ticket preview loads cleanly through actual app.load_page()."""
        st.query_params['doc_id'] = 'DOC-6f58596d'
        st.session_state['preview_mode_DOC-6f58596d'] = True
        st.session_state['nav_page'] = 'document_review'
        
        try:
            app.load_page('document_review')
        except NameError as e:
            self.fail(f"app.load_page failed with NameError: {e}")
        except Exception as e:
            if "Rerun" not in type(e).__name__:
                self.fail(f"Unexpected exception during load_page: {e}")

    def test_03_close_preview_via_page_loader(self):
        """Case 3: Toggling preview off and loading via app.load_page executes smoothly."""
        st.query_params['doc_id'] = 'DOC-4c9a4d78'
        st.session_state['preview_mode_DOC-4c9a4d78'] = False
        st.session_state['nav_page'] = 'document_review'
        
        try:
            app.load_page('document_review')
        except Exception as e:
            if "Rerun" not in type(e).__name__:
                self.fail(f"Unexpected exception: {e}")

    def test_04_existing_verification_history_via_page_loader(self):
        """Case 4: Existing verification history renders cleanly through app.load_page."""
        # Test modern doc with document_history
        st.query_params['doc_id'] = 'DOC-ab6d8384'
        st.session_state['nav_page'] = 'document_review'
        try:
            app.load_page('document_review')
        except Exception as e:
            if "Rerun" not in type(e).__name__:
                self.fail(f"Unexpected exception: {e}")
                
        # Test legacy doc with activity fallback
        st.query_params['doc_id'] = 'DOC-4c9a4d78'
        try:
            app.load_page('document_review')
        except Exception as e:
            if "Rerun" not in type(e).__name__:
                self.fail(f"Unexpected exception: {e}")

    def test_05_document_storage_path_security_via_page_loader(self):
        """Case 5: Path traversal attempts are blocked inside exec page-loader context."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path, extracted_data)
                VALUES ('DOC-TRAVERSAL-TEST', 'REQ-T-01', 'Verified', '../../etc/passwd', '{}')
            """)
            conn.commit()
            conn.close()
            
            st.query_params['doc_id'] = 'DOC-TRAVERSAL-TEST'
            st.session_state['preview_mode_DOC-TRAVERSAL-TEST'] = True
            
            # Must run safely without path traversal
            app.load_page('document_review')
        finally:
            database.DB_PATH = orig_db

    def test_06_missing_file_handling_via_page_loader(self):
        """Case 6: Missing files on disk are handled gracefully inside exec page-loader context."""
        orig_db = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH
        try:
            conn = sqlite3.connect(SANDBOX_DB_PATH)
            conn.execute("""
                INSERT OR REPLACE INTO documents (id, requirement_id, status, file_path, extracted_data)
                VALUES ('DOC-MISSING-TEST', 'REQ-T-01', 'Verified', 'documents/missing_flight.pdf', '{}')
            """)
            conn.commit()
            conn.close()
            
            st.query_params['doc_id'] = 'DOC-MISSING-TEST'
            st.session_state['preview_mode_DOC-MISSING-TEST'] = True
            
            # Must handle missing file cleanly without unhandled exception
            app.load_page('document_review')
        finally:
            database.DB_PATH = orig_db

    def test_07_resilience_without_file_in_globals(self):
        """Case 7: document_review.py executes cleanly even if a caller's exec globals omit __file__ completely."""
        st.query_params['doc_id'] = 'DOC-4c9a4d78'
        st.session_state['preview_mode_DOC-4c9a4d78'] = True
        
        page_path = os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py')
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            
        # Explicitly omit __file__ from page_globals to simulate older/alternative loaders
        bare_globals = {"__name__": "__main__", "st": st, "os": os}
        try:
            exec(code, bare_globals)
        except NameError as e:
            self.fail(f"Bare exec failed with NameError: {e}")
        except Exception as e:
            if "Rerun" not in type(e).__name__:
                self.fail(f"Bare exec failed with unexpected error: {e}")

    def test_08_production_database_remains_unchanged(self):
        """Case 8: Production database size and SHA256 checksum remain identical."""
        sha, sz = get_prod_checksum()
        self.assertEqual(sz, BASELINE_SIZE)
        self.assertEqual(sha, BASELINE_SHA256)


if __name__ == '__main__':
    unittest.main()
