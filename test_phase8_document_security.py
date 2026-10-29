"""
Phase 8.1 Document Access Security & RBAC Test Suite
Khanna Travels - KT Vault V3
Tests strict authorization, session validation, path traversal defense,
audit trail logging, and readiness recalculation using an isolated sandbox database.
"""

import os
import sys
import shutil
import sqlite3
import hashlib
import unittest
import json
from datetime import datetime, timedelta

# Ensure KT Vault V3 root is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

import database
import auth_services
import services

PROD_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')
SANDBOX_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'test_phase8_sandbox.db')
BASELINE_SHA256 = '74db64ae59cdf3bb16baab683f4401355c4088c1b8d1e02161af1befef73ad2b'
BASELINE_SIZE = 102400

def get_file_checksum(filepath):
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest(), os.path.getsize(filepath)


class Phase8DocumentSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Verify baseline production DB integrity before anything touches disk
        sha, sz = get_file_checksum(PROD_DB_PATH)
        assert sz == BASELINE_SIZE, f"Production DB size mismatch: {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Production DB hash mismatch: {sha} != {BASELINE_SHA256}"

        # 2. Create isolated sandbox database from production DB copy
        if os.path.exists(SANDBOX_DB_PATH):
            os.remove(SANDBOX_DB_PATH)
        shutil.copy2(PROD_DB_PATH, SANDBOX_DB_PATH)

        # 3. Direct database module to the sandbox database
        cls.orig_db_path = database.DB_PATH
        database.DB_PATH = SANDBOX_DB_PATH

        # 4. Seed synthetic test users and sessions in sandbox DB
        conn = database.get_connection()
        try:
            # Synthetic Users
            users_to_add = [
                ('TEST-U-STAFF', 'synth_staff', 'Synthetic Staff', 'Staff'),
                ('TEST-U-SUP', 'synth_supervisor', 'Synthetic Supervisor', 'Supervisor'),
                ('TEST-U-ADMIN', 'synth_admin', 'Synthetic Admin', 'Admin')
            ]
            for uid, uname, fname, role in users_to_add:
                salt = os.urandom(16)
                pwd_hash = hashlib.pbkdf2_hmac('sha256', b'Password123!', salt, 100000)
                conn.execute(
                    "INSERT OR REPLACE INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                    (uid, uname, pwd_hash, salt, fname, role)
                )

            # Synthetic Sessions
            now = datetime.now()
            cls.staff_token = "synth_token_staff_valid_1234567890"
            cls.supervisor_token = "synth_token_supervisor_valid_1234567890"
            cls.admin_token = "synth_token_admin_valid_1234567890"
            cls.expired_token = "synth_token_expired_9876543210"

            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                         (cls.staff_token, 'TEST-U-STAFF', (now + timedelta(hours=6)).isoformat()))
            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                         (cls.supervisor_token, 'TEST-U-SUP', (now + timedelta(hours=6)).isoformat()))
            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                         (cls.admin_token, 'TEST-U-ADMIN', (now + timedelta(hours=6)).isoformat()))
            conn.execute("INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                         (cls.expired_token, 'TEST-U-STAFF', (now - timedelta(hours=2)).isoformat()))

            # Synthetic Customer & Trip
            conn.execute("INSERT OR REPLACE INTO customers (id, name, customer_type, status) VALUES (?, ?, ?, ?)",
                         ('TEST-C-001', 'Test Customer', 'Individual', 'Active'))
            conn.execute("INSERT OR REPLACE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         ('TEST-T-001', 'TEST-C-001', 'Test Holiday', 'Paris', '2026-11-01', '2026-11-10', 'Leisure', 'Outbound', 'Europe', 'TRAVEL FILE READY'))

            # Synthetic Requirements
            conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, ?, NULL, ?, ?)",
                         ('TEST-REQ-001', 'TEST-T-001', 'Flight Ticket', 'TRIP'))
            conn.execute("INSERT OR REPLACE INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, ?, NULL, ?, ?)",
                         ('TEST-REQ-002', 'TEST-T-001', 'Hotel Voucher', 'TRIP'))

            # Synthetic Documents
            sample_flight_data = {
                'Passenger Name': 'Test Passenger',
                'PNR/Booking Reference': 'TESTPNR123',
                'Route': 'DEL - CDG',
                'Departure Date/Time': '2026-11-01 10:00',
                'Arrival Date/Time': '2026-11-01 16:00'
            }
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                         ('DOC-TEST-UNDER-REVIEW', 'TEST-REQ-001', 'Under Review', json.dumps(sample_flight_data), 'documents/03_Dubai_Flight_Ticket.pdf', now.isoformat()))
            conn.execute("INSERT OR REPLACE INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                         ('DOC-TEST-VERIFIED', 'TEST-REQ-002', 'Verified', json.dumps({'Hotel Name': 'Grand Hotel', 'Guest Name': 'Test Passenger'}), 'documents/04_Dubai_Hotel_Voucher.pdf', now.isoformat()))

            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        # Restore original database path
        database.DB_PATH = cls.orig_db_path

        # Remove sandbox database
        if os.path.exists(SANDBOX_DB_PATH):
            try:
                os.remove(SANDBOX_DB_PATH)
            except Exception:
                pass

        # Final assertion: Production DB remains completely untouched
        sha, sz = get_file_checksum(PROD_DB_PATH)
        assert sz == BASELINE_SIZE, f"Production DB altered! Size: {sz} != {BASELINE_SIZE}"
        assert sha == BASELINE_SHA256, f"Production DB altered! Hash: {sha} != {BASELINE_SHA256}"

    # 1. Staff, Supervisor and Admin Permissions
    def test_01_role_permissions_enforcement(self):
        # Staff is blocked from Verify
        with self.assertRaises(PermissionError):
            services.verify_document('DOC-TEST-UNDER-REVIEW', self.staff_token)

        # Staff is blocked from Reject
        with self.assertRaises(PermissionError):
            services.reject_document('DOC-TEST-UNDER-REVIEW', 'Staff cannot reject', self.staff_token)

        # Staff is blocked from Request Re-upload
        with self.assertRaises(PermissionError):
            services.request_reupload_document('DOC-TEST-UNDER-REVIEW', 'Staff cannot request reupload', self.staff_token)

        # Staff is blocked from Reopen
        with self.assertRaises(PermissionError):
            services.reopen_document('DOC-TEST-VERIFIED', 'Staff cannot reopen', self.staff_token)

        # Supervisor can verify
        services.verify_document('DOC-TEST-UNDER-REVIEW', self.supervisor_token)
        doc = services.get_document('DOC-TEST-UNDER-REVIEW')
        self.assertEqual(doc['status'], 'Verified')

        # Supervisor can reopen verified document
        services.reopen_document('DOC-TEST-UNDER-REVIEW', 'Need correction', self.supervisor_token)
        doc = services.get_document('DOC-TEST-UNDER-REVIEW')
        self.assertEqual(doc['status'], 'Under Review')

        # Admin can reject
        services.reject_document('DOC-TEST-UNDER-REVIEW', 'Admin rejected', self.admin_token)
        doc = services.get_document('DOC-TEST-UNDER-REVIEW')
        self.assertEqual(doc['status'], 'Rejected')

        # Admin can request re-upload
        services.request_reupload_document('DOC-TEST-UNDER-REVIEW', 'Admin re-upload request', self.admin_token)
        doc = services.get_document('DOC-TEST-UNDER-REVIEW')
        self.assertEqual(doc['status'], 'Re-upload Required')

    # 2. Missing and Expired Sessions
    def test_02_missing_and_expired_sessions(self):
        # Missing token
        with self.assertRaises(PermissionError):
            services.verify_document('DOC-TEST-UNDER-REVIEW', None)
        with self.assertRaises(PermissionError):
            services.reject_document('DOC-TEST-UNDER-REVIEW', 'Reason', None)
        with self.assertRaises(PermissionError):
            services.save_extracted_information('DOC-TEST-UNDER-REVIEW', {}, None)

        # Invalid token
        with self.assertRaises(PermissionError):
            services.verify_document('DOC-TEST-UNDER-REVIEW', 'fake_token_xyz')

        # Expired token
        with self.assertRaises(PermissionError):
            services.verify_document('DOC-TEST-UNDER-REVIEW', self.expired_token)

    # 3. Tampered Document IDs
    def test_03_tampered_document_ids(self):
        with self.assertRaises(ValueError):
            services.verify_document('DOC-NONEXISTENT-999', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.reject_document('DOC-NONEXISTENT-999', 'Reason', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.request_reupload_document('DOC-NONEXISTENT-999', 'Reason', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.reopen_document('DOC-NONEXISTENT-999', 'Reason', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.save_extracted_information('DOC-NONEXISTENT-999', {'Key': 'Val'}, self.staff_token)

    # 4. Cross-department viewing by authorized staff
    def test_04_cross_department_viewing(self):
        # Staff can retrieve details of any document, trip or requirements
        doc = services.get_document('DOC-TEST-VERIFIED')
        self.assertIsNotNone(doc)
        trip = services.get_trip_details('TEST-T-001')
        self.assertIsNotNone(trip)
        reqs = services.get_requirements('TEST-T-001')
        self.assertEqual(len(reqs), 2)

    # 5. Unauthorized rejection and re-upload attempts (Missing reasons & Role barriers)
    def test_05_rejection_and_reupload_validation(self):
        # Rejection without reason fails
        with self.assertRaises(ValueError):
            services.reject_document('DOC-TEST-UNDER-REVIEW', '', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.reject_document('DOC-TEST-UNDER-REVIEW', '   ', self.supervisor_token)

        # Re-upload without reason fails
        with self.assertRaises(ValueError):
            services.request_reupload_document('DOC-TEST-UNDER-REVIEW', '', self.supervisor_token)
        with self.assertRaises(ValueError):
            services.request_reupload_document('DOC-TEST-UNDER-REVIEW', '   ', self.supervisor_token)

    # 6. Verified-document modification protection
    def test_06_verified_document_protection(self):
        # Cannot modify extracted_data of Verified document
        with self.assertRaises(ValueError) as cm:
            services.save_extracted_information('DOC-TEST-VERIFIED', {'Hotel Name': 'Hacked Hotel'}, self.staff_token)
        self.assertIn("Cannot modify extracted data of a VERIFIED document", str(cm.exception))

        # Cannot reject Verified document directly
        with self.assertRaises(ValueError) as cm:
            services.reject_document('DOC-TEST-VERIFIED', 'Direct reject attempt', self.supervisor_token)
        self.assertIn("Cannot reject a VERIFIED document directly", str(cm.exception))

        # Cannot request re-upload for Verified document directly
        with self.assertRaises(ValueError) as cm:
            services.request_reupload_document('DOC-TEST-VERIFIED', 'Direct reupload attempt', self.supervisor_token)
        self.assertIn("Cannot request re-upload for a VERIFIED document directly", str(cm.exception))

    # 7. Secure PDF path handling
    def test_07_secure_pdf_path_handling(self):
        # Legitimate path inside documents/
        safe_path, err = services.get_safe_document_path('documents/03_Dubai_Flight_Ticket.pdf')
        self.assertIsNone(err)
        self.assertIsNotNone(safe_path)
        self.assertTrue(os.path.isabs(safe_path))

        # Path traversal attack
        safe_path, err = services.get_safe_document_path('documents/../../windows/win.ini')
        self.assertIsNone(safe_path)
        self.assertIn("Security Error", err)

        # Directory traversal escaping documents folder
        safe_path, err = services.get_safe_document_path('documents/../app.py')
        self.assertIsNone(safe_path)
        self.assertIn("Security Error", err)

        # System file access attempt
        safe_path, err = services.get_safe_document_path('C:/windows/system32/cmd.exe')
        self.assertIsNone(safe_path)
        self.assertIn("Security Error", err)

        # Empty / None path
        safe_path, err = services.get_safe_document_path('')
        self.assertIsNone(safe_path)
        self.assertIn("not specified", err)

    # 8. Audit history creation
    def test_08_audit_history_creation(self):
        conn = database.get_connection()
        # Reset doc status to Under Review
        conn.execute("UPDATE documents SET status = 'Under Review' WHERE id = 'DOC-TEST-UNDER-REVIEW'")
        conn.commit()
        conn.close()

        # Update data -> Check EDIT_DATA in document_history
        new_data = {
            'Passenger Name': 'Test Passenger Edited',
            'PNR/Booking Reference': 'TESTPNR123',
            'Route': 'DEL - CDG',
            'Departure Date/Time': '2026-11-01 10:00',
            'Arrival Date/Time': '2026-11-01 16:00'
        }
        services.save_extracted_information('DOC-TEST-UNDER-REVIEW', new_data, self.staff_token, 'Staff edited PNR')
        conn = database.get_connection()
        h = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-TEST-UNDER-REVIEW' AND event_type = 'EDIT_DATA' ORDER BY timestamp DESC LIMIT 1").fetchone()
        self.assertIsNotNone(h)
        self.assertEqual(h['actor'], 'Synthetic Staff')
        self.assertEqual(h['reason'], 'Staff edited PNR')
        conn.close()

        # Reject -> Check REJECT in document_history
        services.reject_document('DOC-TEST-UNDER-REVIEW', 'Barcode unreadable', self.supervisor_token)
        conn = database.get_connection()
        h = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-TEST-UNDER-REVIEW' AND event_type = 'REJECT' ORDER BY timestamp DESC LIMIT 1").fetchone()
        self.assertIsNotNone(h)
        self.assertEqual(h['actor'], 'Synthetic Supervisor')
        self.assertEqual(h['reason'], 'Barcode unreadable')
        conn.close()

        # Re-upload Request -> Check REUPLOAD_REQUEST in document_history
        services.request_reupload_document('DOC-TEST-UNDER-REVIEW', 'Please re-scan page 2', self.supervisor_token)
        conn = database.get_connection()
        h = conn.execute("SELECT * FROM document_history WHERE document_id = 'DOC-TEST-UNDER-REVIEW' AND event_type = 'REUPLOAD_REQUEST' ORDER BY timestamp DESC LIMIT 1").fetchone()
        self.assertIsNotNone(h)
        self.assertEqual(h['actor'], 'Synthetic Supervisor')
        self.assertEqual(h['reason'], 'Please re-scan page 2')
        conn.close()

    # 9. Readiness recalculation
    def test_09_readiness_recalculation(self):
        conn = database.get_connection()
        # Set trip to 'TRAVEL FILE READY'
        conn.execute("UPDATE trips SET status = 'TRAVEL FILE READY' WHERE id = 'TEST-T-001'")
        conn.execute("UPDATE documents SET status = 'Under Review' WHERE id = 'DOC-TEST-UNDER-REVIEW'")
        conn.commit()
        conn.close()

        # Rejection should revert trip status to NOT READY
        services.reject_document('DOC-TEST-UNDER-REVIEW', 'Defect in document', self.supervisor_token)
        trip = services.get_trip_details('TEST-T-001')
        self.assertEqual(trip['status'], 'NOT READY')

        total, complete, attention, missing, pct, business_status = services.calculate_readiness('TEST-T-001')
        self.assertEqual(business_status, 'NOT READY')

    # 10. Existing Smart Upload and Review Functionality Preservation
    def test_10_existing_functionality_preservation(self):
        # Staff note addition
        services.add_document_note('DOC-TEST-UNDER-REVIEW', 'Internal staff remark', self.staff_token)
        conn = database.get_connection()
        act = conn.execute("SELECT * FROM activity WHERE trip_id = 'TEST-T-001' AND description LIKE '%Internal staff remark%'").fetchone()
        self.assertIsNotNone(act)
        conn.close()

        # get_all_documents_for_review works
        conn = database.get_connection()
        conn.execute("UPDATE documents SET status = 'Under Review' WHERE id = 'DOC-TEST-UNDER-REVIEW'")
        conn.commit()
        conn.close()
        review_docs = services.get_all_documents_for_review()
        self.assertTrue(any(d['id'] == 'DOC-TEST-UNDER-REVIEW' for d in review_docs))

        # Smart upload save_document works with Staff token
        saved_id = services.save_document(
            requirement_id='TEST-REQ-001',
            file_path='documents/03_Dubai_Flight_Ticket.pdf',
            extracted_data={'Test': 'Value'},
            session_token=self.staff_token,
            expected_trip_id='TEST-T-001',
            expected_customer_id='TEST-C-001'
        )
        self.assertIsNotNone(saved_id)


if __name__ == '__main__':
    unittest.main()
