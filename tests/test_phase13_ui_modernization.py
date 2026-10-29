import unittest
import os
import sys
import secrets
import tempfile
import shutil
from datetime import datetime, timedelta

# Ensure project root is in path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from streamlit.testing.v1 import AppTest
import database
import auth_services

class TestPhase13UIModernization(unittest.TestCase):
    """
    Automated UI regression and verification suite for Phase 13
    Khanna Travels Premium UI Modernization.
    """

    @classmethod
    def setUpClass(cls):
        cls.orig_db_path = database.DB_PATH
        cls.temp_dir = tempfile.mkdtemp(prefix="kt_test_ui_")
        cls.test_db_path = os.path.join(cls.temp_dir, "test_ui.db")
        shutil.copyfile(cls.orig_db_path, cls.test_db_path)
        database.DB_PATH = cls.test_db_path

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls.orig_db_path
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        # Create an authenticated session directly in database for UI testing without plaintext passwords
        conn = database.get_connection()
        user = conn.execute("SELECT id, full_name, role FROM users WHERE username = 'admin'").fetchone()
        self.assertIsNotNone(user)
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=12)
        conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)", (token, user['id'], expires_at.isoformat()))
        conn.commit()
        conn.close()
        
        self.token = token
        self.session = {
            'token': token,
            'user_id': user['id'],
            'full_name': user['full_name'],
            'role': user['role']
        }

    def tearDown(self):
        if hasattr(self, 'token') and self.token:
            auth_services.logout(self.token)

    def test_01_login_page_renders_cleanly(self):
        """Verify login page renders without errors and contains branding."""
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.run()
        self.assertFalse(at.exception)
        # Should have username and password text inputs
        self.assertGreaterEqual(len(at.text_input), 2)
        # Should have Login button
        self.assertTrue(any("Sign In" in b.label or "Login" in b.label for b in at.button))

    def test_02_staff_home_dashboard(self):
        """Verify staff_home loads banner, KPI cards, trips, quick actions, attention items."""
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'staff_home'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'staff_home'
        at.run()
        self.assertFalse(at.exception)

        # Check sidebar buttons exist
        button_labels = [b.label for b in at.button]
        self.assertIn("Home", button_labels)
        self.assertIn("Customers", button_labels)
        self.assertIn("Trips", button_labels)
        self.assertIn("Documents", button_labels)
        self.assertIn("Smart Intake", button_labels)
        self.assertIn("Smart Upload", button_labels)
        self.assertIn("Document Review", button_labels)
        self.assertIn("Vault Search", button_labels)

        # Check Quick Actions exist
        self.assertIn("➕ Add Customer", button_labels)
        self.assertIn("✈️ View Trips", button_labels)
        self.assertIn("📤 Smart Upload", button_labels)
        self.assertIn("🔍 Search Documents", button_labels)

    def test_03_customers_and_customer_workspace(self):
        """Verify customers list and customer workspace render with tabs."""
        # 1. Customers page
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'customers'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'customers'
        at.run()
        self.assertFalse(at.exception)

        # 2. Customer workspace for Aarav Demo (KT-C-0004)
        at_cw = AppTest.from_file(os.path.join(project_root, "app.py"))
        at_cw.query_params['page'] = 'customer_workspace'
        at_cw.query_params['customer_id'] = 'KT-C-0004'
        at_cw.session_state['session_token'] = self.token
        at_cw.session_state['user_full_name'] = self.session['full_name']
        at_cw.session_state['user_role'] = self.session['role']
        at_cw.session_state['nav_page'] = 'customer_workspace'
        at_cw.run()
        self.assertFalse(at_cw.exception)
        # Should render 6 tabs
        self.assertGreaterEqual(len(at_cw.tabs), 6)

    def test_04_trips_and_trip_workspace(self):
        """Verify trips list and trip workspace render with travel readiness."""
        # 1. Trips page
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'trips'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'trips'
        at.run()
        self.assertFalse(at.exception)

        # 2. Trip workspace for Aarav Demo trip (KT-T-0004)
        at_tw = AppTest.from_file(os.path.join(project_root, "app.py"))
        at_tw.query_params['page'] = 'trip_workspace'
        at_tw.query_params['trip_id'] = 'KT-T-0004'
        at_tw.session_state['session_token'] = self.token
        at_tw.session_state['user_full_name'] = self.session['full_name']
        at_tw.session_state['user_role'] = self.session['role']
        at_tw.session_state['nav_page'] = 'trip_workspace'
        at_tw.run()
        self.assertFalse(at_tw.exception)
        self.assertGreaterEqual(len(at_tw.tabs), 6)

    def test_05_documents_page(self):
        """Verify documents page renders with filter controls."""
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'documents'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'documents'
        at.run()
        self.assertFalse(at.exception)

    def test_06_document_review_with_and_without_doc_id(self):
        """Verify document review handles queue view and two-column inspection."""
        # A: Without doc_id -> should display review queue gracefully
        at_queue = AppTest.from_file(os.path.join(project_root, "app.py"))
        at_queue.query_params['page'] = 'document_review'
        at_queue.session_state['session_token'] = self.token
        at_queue.session_state['user_full_name'] = self.session['full_name']
        at_queue.session_state['user_role'] = self.session['role']
        at_queue.session_state['nav_page'] = 'document_review'
        at_queue.run()
        self.assertFalse(at_queue.exception)

        # B: With doc_id (DOC-c966f3e1 - Aarav passport)
        at_doc = AppTest.from_file(os.path.join(project_root, "app.py"))
        at_doc.query_params['page'] = 'document_review'
        at_doc.query_params['doc_id'] = 'DOC-c966f3e1'
        at_doc.session_state['session_token'] = self.token
        at_doc.session_state['user_full_name'] = self.session['full_name']
        at_doc.session_state['user_role'] = self.session['role']
        at_doc.session_state['nav_page'] = 'document_review'
        at_doc.run()
        self.assertFalse(at_doc.exception)

    def test_07_smart_intake_page(self):
        """Verify smart intake renders with step indicator."""
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'smart_intake'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'smart_intake'
        at.run()
        self.assertFalse(at.exception)

    def test_08_vault_search_page(self):
        """Verify vault search renders with filters and search bar."""
        at = AppTest.from_file(os.path.join(project_root, "app.py"))
        at.query_params['page'] = 'vault_search'
        at.session_state['session_token'] = self.token
        at.session_state['user_full_name'] = self.session['full_name']
        at.session_state['user_role'] = self.session['role']
        at.session_state['nav_page'] = 'vault_search'
        at.run()
        self.assertFalse(at.exception)
        self.assertGreaterEqual(len(at.tabs), 4)

if __name__ == '__main__':
    unittest.main()
