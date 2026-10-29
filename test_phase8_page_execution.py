"""
Phase 8.1 Streamlit Page Execution & UI Authorization Simulation Test
Khanna Travels - KT Vault V3
Tests pages/document_review.py execution under app.py page loader
with mock Streamlit context and sandbox database.
"""

import os
import sys
import shutil
import sqlite3
import hashlib
import unittest
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import database
import auth_services

PROD_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase8_page_sandbox.db')
BASELINE_SHA256 = '74db64ae59cdf3bb16baab683f4401355c4088c1b8d1e02161af1befef73ad2b'
BASELINE_SIZE = 102400

def get_file_checksum(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(filepath)


class Phase8PageExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sha, sz = get_file_checksum(PROD_DB_PATH)
        assert sz == BASELINE_SIZE
        assert sha == BASELINE_SHA256

        if os.path.exists(SANDBOX_DB_PATH):
            os.remove(SANDBOX_DB_PATH)
        shutil.copy2(PROD_DB_PATH, SANDBOX_DB_PATH)

        cls.orig_db_path = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH

        # Seed test user and doc
        conn = database.get_connection()
        try:
            salt = os.urandom(16)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', b'TestPass1!', salt, 100000)
            conn.execute("INSERT OR REPLACE INTO users (id, username, password_hash, salt, full_name, role) VALUES ('U-STF', 'staff_u', ?, ?, 'Staff User', 'Staff')", (pwd_hash, salt))
            conn.execute("INSERT OR REPLACE INTO users (id, username, password_hash, salt, full_name, role) VALUES ('U-SUP', 'sup_u', ?, ?, 'Sup User', 'Supervisor')", (pwd_hash, salt))
            
            now = datetime.now()
            cls.staff_token = "tok_staff_exec_123"
            cls.sup_token = "tok_sup_exec_123"
            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, 'U-STF', ?)", (cls.staff_token, (now + timedelta(hours=4)).isoformat()))
            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, 'U-SUP', ?)", (cls.sup_token, (now + timedelta(hours=4)).isoformat()))
            
            conn.execute("INSERT OR REPLACE INTO customers (id, name, customer_type, status) VALUES ('C-10', 'Demo Cust', 'Individual', 'Active')")
            conn.execute("INSERT OR REPLACE INTO trips (id, customer_id, name, status) VALUES ('T-10', 'C-10', 'Demo Trip', 'NOT READY')")
            conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, name, type) VALUES ('R-10', 'T-10', 'Flight Ticket', 'TRIP')")
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES ('DOC-EXEC-1', 'R-10', 'Under Review', '{}', 'documents/03_Dubai_Flight_Ticket.pdf', ?)", (now.isoformat(),))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        if os.path.exists(SANDBOX_DB_PATH):
            try:
                os.remove(SANDBOX_DB_PATH)
            except Exception:
                pass

        sha, sz = get_file_checksum(PROD_DB_PATH)
        assert sz == BASELINE_SIZE
        assert sha == BASELINE_SHA256

    def test_page_unauthenticated_stops(self):
        page_path = os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py')
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()

        mock_st = MagicMock()
        mock_st.session_state = {}  # No session token
        mock_st.query_params = {'doc_id': 'DOC-EXEC-1'}
        mock_st.stop.side_effect = SystemExit("Streamlit Stop")

        page_globals = {"__name__": "__main__", "st": mock_st, "os": os, "__file__": page_path}
        
        with patch.dict(sys.modules, {'streamlit': mock_st}):
            with self.assertRaises(SystemExit):
                exec(code, page_globals)

        # Verified that st.error was called with authentication required
        mock_st.error.assert_called_with("Authentication required: Invalid, missing, or expired session. Please log in.")

    def test_page_authenticated_staff_renders_safely(self):
        page_path = os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py')
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()

        mock_st = MagicMock()
        mock_st.session_state = {'session_token': self.staff_token}
        mock_st.query_params = {'doc_id': 'DOC-EXEC-1'}
        mock_st.button.return_value = False
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        mock_st.stop.side_effect = SystemExit("Unexpected Stop")

        page_globals = {"__name__": "__main__", "st": mock_st, "os": os, "__file__": page_path}
        
        with patch.dict(sys.modules, {'streamlit': mock_st}):
            exec(code, page_globals)

        # Verify that staff message about requiring supervisor privileges was displayed
        calls = [str(c) for c in mock_st.info.mock_calls]
        has_rbac_notice = any("require Supervisor or Admin privileges" in c for c in calls)
        self.assertTrue(has_rbac_notice, f"Expected RBAC notice in calls: {calls}")

    def test_page_authenticated_supervisor_renders_actions(self):
        page_path = os.path.join(os.path.dirname(__file__), 'pages', 'document_review.py')
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()

        mock_st = MagicMock()
        mock_st.session_state = {'session_token': self.sup_token}
        mock_st.query_params = {'doc_id': 'DOC-EXEC-1'}
        mock_st.button.return_value = False
        mock_st.columns.side_effect = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
        mock_st.stop.side_effect = SystemExit("Unexpected Stop")

        page_globals = {"__name__": "__main__", "st": mock_st, "os": os, "__file__": page_path}
        
        with patch.dict(sys.modules, {'streamlit': mock_st}):
            exec(code, page_globals)

        # For Supervisor, the restriction notice should NOT be shown
        calls = [str(c) for c in mock_st.info.mock_calls]
        has_rbac_notice = any("require Supervisor or Admin privileges" in c for c in calls)
        self.assertFalse(has_rbac_notice, "Supervisor should not see permission restriction notice")


if __name__ == '__main__':
    unittest.main()
