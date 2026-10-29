import unittest
import os
import hashlib
import document_processor as dp

class TestPhase9ExtractionRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.db_path = r"C:\KT_Vault_V3\data\kt_vault_v3.db"
        cls.initial_db_size = os.path.getsize(cls.db_path)
        with open(cls.db_path, "rb") as f:
            cls.initial_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        
        cls.rohan_dir = r"C:\Users\Admin\Downloads\KT_Vault_V3_Rohan_All_9_Demo_Documents"
        cls.rahul_dir = r"C:\Users\Admin\Downloads\Rahul_Sharma_KT_Vault_Demo_Pack (1)"
        cls.legacy_dir = r"C:\KT_Vault_V3\documents"

    def test_01_rohan_pack_all_9_documents(self):
        """Verify 100% accuracy on Rohan Test all 9 synthetic documents."""
        self.assertTrue(os.path.exists(self.rohan_dir), f"Rohan pack directory not found: {self.rohan_dir}")
        
        expected_results = {
            "01_Passport_Demo.pdf": {
                "type": "Passport",
                "fields": {
                    "Full Name": "Rohan Test",
                    "Passport Number": "DEMO-PASSPORT-0001",
                    "Date of Birth": "15 Jun 1995",
                    "Nationality": "Indian",
                    "Issue Date": "10 Jan 2024",
                    "Expiry Date": "10 Jan 2030"
                }
            },
            "02_Visa_Entry_Document_Demo.pdf": {
                "type": "Visa / Entry Document",
                "fields": {
                    "Traveller Name": "Rohan Test",
                    "Visa Number / Reference": "DEMO-VISA-DXB-2026-001",
                    "Destination": "Dubai, UAE",
                    "Purpose": "Tourist",
                    "Issue Date": "",
                    "Travel Dates": "",
                    "Expiry Date / Valid Until": "31 Dec 2026"
                }
            },
            "03_Flight_Ticket_Demo.pdf": {
                "type": "Flight Ticket",
                "fields": {
                    "Passenger Name": "Rohan Test",
                    "Route": "Mumbai - Dubai - Mumbai",
                    "Airline": "Demo Airways (fictional)",
                    "Flight Number": "DM 1206",
                    "PNR/Booking Reference": "DEMO-DXB-4812",
                    "Origin": "Mumbai",
                    "Destination": "Dubai",
                    "Departure Date/Time": "12 Dec 2026 09:30",
                    "Arrival Date/Time": "18 Dec 2026 21:45",
                    "Cabin Class": "Economy"
                }
            },
            "04_Hotel_Voucher_Demo.pdf": {
                "type": "Hotel Voucher",
                "fields": {
                    "Hotel Name": "Demo Palm Hotel Dubai (fictional)",
                    "Guest Name": "Rohan Test",
                    "Check-in Date": "12 Dec 2026",
                    "Check-out Date": "18 Dec 2026",
                    "Booking Confirmation Number": "DEMO-HOTEL-4821",
                    "Room Type": "Deluxe Room",
                    "Hotel Address": "Dubai, UAE"
                }
            },
            "05_Travel_Insurance_Demo.pdf": {
                "type": "Travel Insurance",
                "fields": {
                    "Insured Name": "Rohan Test",
                    "Policy Number": "DEMO-INS-2026-1206",
                    "Insurance Provider": "Demo Travel Cover (fictional)",
                    "Valid From": "12 Dec 2026",
                    "Valid Until": "18 Dec 2026",
                    "Destination / Coverage Area": "Dubai, UAE"
                }
            },
            "06_Itinerary_Demo.pdf": {
                "type": "Itinerary",
                "fields": {
                    "Trip Destination": "Dubai, UAE",
                    "Start Date": "12 Dec 2026",
                    "End Date": "18 Dec 2026",
                    "Schedule Summary": "Day 1: Arrival and hotel check-in | Day 2: Dubai city tour | Day 3: Desert safari | Day 4: Museum and leisure | Day 5: Marina sightseeing"
                }
            },
            "07_Transfer_Voucher_Demo.pdf": {
                "type": "Transfer Voucher",
                "fields": {
                    "Passenger Name": "Rohan Test",
                    "Booking Reference": "DEMO-TRF-2048",
                    "Pickup Location": "Dubai International Airport",
                    "Dropoff Location": "Demo Palm Hotel Dubai",
                    "Transfer Date": "12 Dec 2026"
                }
            },
            "08_Sightseeing_Voucher_Demo.pdf": {
                "type": "Sightseeing Voucher",
                "fields": {
                    "Guest Name": "Rohan Test",
                    "Booking Reference": "DEMO-SEE-7841",
                    "Tour / Activity Name": "Dubai City Tour (fictional booking)",
                    "Activity Date": "13 Dec 2026",
                    "Number of Guests": "1 Adult"
                }
            },
            "09_Arrival_Entry_Document_Demo.pdf": {
                "type": "Arrival / Entry Document",
                "fields": {
                    "Traveller Name": "Rohan Test",
                    "Trip Name": "Rohan Dubai Demo Holiday",
                    "Destination": "Dubai, UAE",
                    "Arrival Date": "12 Dec 2026",
                    "Departure Date": "18 Dec 2026"
                }
            }
        }
        
        total_fields = 0
        correct_fields = 0
        
        for fname, expected in expected_results.items():
            fpath = os.path.join(self.rohan_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"File {fpath} not found")
            with open(fpath, "rb") as f:
                res = dp.process_document(fname, f.read())
            
            self.assertEqual(res["document_type"], expected["type"], f"Type mismatch for {fname}")
            fields = res["extracted_fields"]
            for field_name, expected_val in expected["fields"].items():
                total_fields += 1
                actual_val = fields.get(field_name, "")
                if actual_val == expected_val:
                    correct_fields += 1
                else:
                    self.assertEqual(actual_val, expected_val, f"Field '{field_name}' in '{fname}' mismatch: got '{actual_val}', expected '{expected_val}'")
        
        accuracy = (correct_fields / total_fields) * 100
        self.assertGreaterEqual(accuracy, 98.0, f"Rohan accuracy {accuracy}% below 98%")

    def test_02_rahul_sharma_pack_all_documents(self):
        """Verify extraction and classification across Rahul Sharma demo pack."""
        self.assertTrue(os.path.exists(self.rahul_dir), f"Rahul pack directory not found: {self.rahul_dir}")
        
        expected_results = {
            "01_Rahul_Passport_V1.pdf": {
                "type": "Passport",
                "fields": {
                    "Full Name": "Rahul Sharma",
                    "Passport Number": "P0001001",
                    "Nationality": "Indian",
                    "Date of Birth": "14 Mar 1987"
                }
            },
            "02_Rahul_Visa_Entry_Document.pdf": {
                "type": "Visa / Entry Document",
                "fields": {
                    "Traveller Name": "Rahul Sharma",
                    "Visa Number / Reference": "KT-VISA-DEMO-1001"
                }
            },
            "03_Flight_Ticket.pdf": {
                "type": "Flight Ticket",
                "fields": {
                    "Passenger Name": "Rahul, Priya, Aarav, Anaya Sharma",
                    "PNR/Booking Reference": "KT-FLT-DEMO-2201"
                }
            },
            "04_Hotel_Confirmation.pdf": {
                "type": "Hotel Voucher",
                "fields": {
                    "Hotel Name": "Harbour View Demo Hotel - fictional",
                    "Guest Name": "Sharma Family - 4 travellers",
                    "Booking Confirmation Number": "KT-HTL-DEMO-3301"
                }
            },
            "05_Travel_Insurance.pdf": {
                "type": "Travel Insurance",
                "fields": {
                    "Insured Name": "Rahul Sharma",
                    "Policy Number": "KT-INS-DEMO-4401"
                }
            },
            "06_Arrival_Transfer_Voucher.pdf": {
                "type": "Transfer Voucher",
                "fields": {
                    "Passenger Name": "Sharma Family - 4 travellers",
                    "Booking Reference": "KT-TRF-DEMO-5501",
                    "Pickup Location": "Demo Airport",
                    "Dropoff Location": "Demo Hotel"
                }
            },
            "07_Departure_Transfer_Voucher.pdf": {
                "type": "Transfer Voucher",
                "fields": {
                    "Passenger Name": "Sharma Family - 4 travellers",
                    "Booking Reference": "KT-TRF-DEMO-5502",
                    "Pickup Location": "Demo Hotel",
                    "Dropoff Location": "Demo Airport"
                }
            },
            "08_City_Tour_Voucher.pdf": {
                "type": "Sightseeing Voucher",
                "fields": {
                    "Guest Name": "Rahul Sharma",
                    "Booking Reference": "KT-ACT-DEMO-6601",
                    "Tour / Activity Name": "Demo Singapore City Highlights Tour"
                }
            },
            "09_Night_Safari_Voucher.pdf": {
                "type": "Sightseeing Voucher",
                "fields": {
                    "Guest Name": "Rahul Sharma",
                    "Booking Reference": "KT-ACT-DEMO-6602",
                    "Tour / Activity Name": "Demo Night Safari Experience"
                }
            },
            "10_Arrival_Card_Demo.pdf": {
                "type": "Arrival / Entry Document",
                "fields": {
                    "Traveller Name": "Rahul Sharma",
                    "Trip Name": "Sharma Family - Singapore Holiday",
                    "Reference Number": "KT-ARR-DEMO-7701"
                }
            },
            "11_Final_Itinerary_Draft.pdf": {
                "type": "Itinerary",
                "fields": {
                    "Start Date": "15 Dec 2026",
                    "End Date": "20 Dec 2026",
                    "Schedule Summary": ""
                }
            },
            "12_Rahul_Bank_Statement_Supporting_Demo.pdf": {
                "type": "Needs Review",
                "fields": {}
            }
        }
        
        total_fields = 0
        correct_fields = 0
        
        for fname, expected in expected_results.items():
            fpath = os.path.join(self.rahul_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"File {fpath} not found")
            with open(fpath, "rb") as f:
                res = dp.process_document(fname, f.read())
            
            self.assertEqual(res["document_type"], expected["type"], f"Type mismatch for {fname}")
            fields = res["extracted_fields"]
            for field_name, expected_val in expected["fields"].items():
                total_fields += 1
                actual_val = fields.get(field_name, "")
                if actual_val == expected_val:
                    correct_fields += 1
                else:
                    self.assertEqual(actual_val, expected_val, f"Field '{field_name}' in '{fname}' mismatch: got '{actual_val}', expected '{expected_val}'")
        
        accuracy = (correct_fields / total_fields) * 100
        self.assertGreaterEqual(accuracy, 98.0, f"Rahul pack accuracy {accuracy}% below 98%")

    def test_03_legacy_documents_in_production(self):
        """Verify extraction across legacy demo documents in documents/."""
        expected_types = {
            "01_Amit_Mehta_Demo_Passport.pdf": "Passport",
            "02_Amit_Mehta_Demo_Visa_Entry.pdf": "Visa / Entry Document",
            "03_Dubai_Flight_Ticket.pdf": "Flight Ticket",
            "04_Dubai_Hotel_Voucher.pdf": "Hotel Voucher",
            "05_Travel_Insurance.pdf": "Travel Insurance",
            "06_Transfer_Voucher.pdf": "Transfer Voucher",
            "07_Sightseeing_Voucher.pdf": "Sightseeing Voucher",
            "08_Arrival_Entry_Document.pdf": "Arrival / Entry Document",
            "09_Dubai_Itinerary.pdf": "Itinerary"
        }
        for fname, exp_type in expected_types.items():
            fpath = os.path.join(self.legacy_dir, fname)
            self.assertTrue(os.path.exists(fpath), f"File {fpath} not found")
            with open(fpath, "rb") as f:
                res = dp.process_document(fname, f.read())
            self.assertEqual(res["document_type"], exp_type, f"Got {res['document_type']}, expected {exp_type}")

    def test_04_type_mismatch_detection_logic(self):
        """Verify that high-confidence document mismatch is correctly identified."""
        # 1. Transfer voucher uploaded for Arrival / Entry Document requirement
        transfer_file = os.path.join(self.rahul_dir, "06_Arrival_Transfer_Voucher.pdf")
        with open(transfer_file, "rb") as f:
            res = dp.process_document("06_Arrival_Transfer_Voucher.pdf", f.read())
        
        doc_type = res["document_type"]
        type_conf = res["type_confidence"]
        
        # Simulating requirement 'Arrival / Entry Document'
        target_req_name = "Arrival / Entry Document"
        
        # Test detection logic
        self.assertEqual(doc_type, "Transfer Voucher")
        self.assertEqual(type_conf, "high")
        
        # In smart_upload, fallback_suggestion for this requirement is 'Arrival / Entry Document'
        fallback_suggestion = "Arrival / Entry Document"
        is_type_mismatch = (
            type_conf == 'high'
            and doc_type != 'Needs Review'
            and fallback_suggestion != 'Needs Review'
            and doc_type != fallback_suggestion
        )
        self.assertTrue(is_type_mismatch, "Should flag type mismatch between Transfer Voucher and Arrival Document")

        # 2. Matching document
        passport_file = os.path.join(self.rohan_dir, "01_Passport_Demo.pdf")
        with open(passport_file, "rb") as f:
            res_pass = dp.process_document("01_Passport_Demo.pdf", f.read())
        
        pass_type = res_pass["document_type"]
        pass_conf = res_pass["type_confidence"]
        pass_req_name = "Passport"
        is_pass_mismatch = (
            pass_conf == 'high'
            and pass_type != 'Needs Review'
            and pass_req_name != 'Needs Review'
            and pass_type != pass_req_name
        )
        self.assertFalse(is_pass_mismatch, "Should NOT flag mismatch when document matches requirement")

    def test_05_production_database_integrity_and_immutability(self):
        """Verify that the production database remains completely bit-for-bit untouched."""
        self.assertTrue(os.path.exists(self.db_path), f"Production database not found: {self.db_path}")
        self.assertEqual(os.path.getsize(self.db_path), self.initial_db_size, "Database size changed during test run!")
        
        with open(self.db_path, "rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
            
        self.assertEqual(
            actual_sha256,
            self.initial_db_sha256,
            "CRITICAL INTEGRITY VIOLATION: Production database SHA-256 changed during test run!"
        )
        conn = self.sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()

    def test_06_visa_purpose_cleaning_and_label_rejection(self):
        """Verify that field labels are never captured as purpose values and genuine purposes are cleaned."""
        # Field labels must be rejected and result in empty string
        self.assertEqual(dp.clean_purpose_value("Visa Type"), "")
        self.assertEqual(dp.clean_purpose_value("Purpose"), "")
        self.assertEqual(dp.clean_purpose_value("Category"), "")
        self.assertEqual(dp.clean_purpose_value("Class of Entry"), "")
        self.assertEqual(dp.clean_purpose_value("Type"), "")

        # Genuine values with suffixes/prefixes must be cleaned
        self.assertEqual(dp.clean_purpose_value("Tourist - DEMO"), "Tourist")
        self.assertEqual(dp.clean_purpose_value("Business / Conference"), "Business")
        self.assertEqual(dp.clean_purpose_value("Purpose: Tourism"), "Tourism")
        self.assertEqual(dp.clean_purpose_value("Category: Employment"), "Employment")

        # Visa without genuine purpose text leaves Purpose empty
        visa_text_no_purpose = """
        DEMO ENTRY VISA
        Traveller: Test Person
        Visa Number: V123456
        Validity: 30 Days
        """
        data, _, _, _ = dp.parse_passport_text(visa_text_no_purpose, expected_requirement="Visa / Entry Document")
        self.assertEqual(data.get("Purpose", ""), "")

    def test_07_itinerary_metadata_exclusion_and_schedule_parsing(self):
        """Verify that table headers and metadata words are strictly excluded from schedule summary."""
        # Draft without schedule yields empty schedule summary
        fpath = os.path.join(self.rahul_dir, "11_Final_Itinerary_Draft.pdf")
        with open(fpath, "rb") as f:
            res = dp.process_document("11_Final_Itinerary_Draft.pdf", f.read())
        self.assertEqual(res["extracted_fields"].get("Schedule Summary"), "")

        # Rohan itinerary has 5 days without metadata leakage
        fpath_rohan = os.path.join(self.rohan_dir, "06_Itinerary_Demo.pdf")
        with open(fpath_rohan, "rb") as f:
            res_rohan = dp.process_document("06_Itinerary_Demo.pdf", f.read())
        sched = res_rohan["extracted_fields"].get("Schedule Summary", "")
        self.assertNotIn("End Date", sched)
        self.assertNotIn("Start Date", sched)
        self.assertIn("Day 1: Arrival and hotel check-in", sched)
        self.assertIn("Day 2: Dubai city tour", sched)
        self.assertIn("Day 3: Desert safari", sched)
        self.assertIn("Day 4: Museum and leisure", sched)
        self.assertIn("Day 5: Marina sightseeing", sched)

    def test_08_traveller_identity_validation(self):
        """Verify comprehensive traveller identity validation across exact, manifest, family, and mismatch cases."""
        # 1. Exact match
        r1 = dp.validate_traveller_identity(
            doc_type="Passport",
            extracted_fields={"Full Name": "Rohan Test"},
            expected_traveller_name="Rohan Test"
        )
        self.assertTrue(r1["valid"])
        self.assertNotEqual(r1.get("severity"), "error")

        # 2. Case / Title / Spacing tolerance
        r2 = dp.validate_traveller_identity(
            doc_type="Passport",
            extracted_fields={"Full Name": "Mr. Rohan Test"},
            expected_traveller_name="rohan test"
        )
        self.assertTrue(r2["valid"])

        # 3. Multi-passenger manifest distributes shared surname
        r3 = dp.validate_traveller_identity(
            doc_type="Flight Ticket",
            extracted_fields={"Passenger Name": "Rahul, Priya, Aarav, Anaya Sharma"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma", "Aarav Sharma", "Anaya Sharma"]
        )
        self.assertTrue(r3["valid"])

        r3b = dp.validate_traveller_identity(
            doc_type="Flight Ticket",
            extracted_fields={"Passenger Name": "Rahul, Priya, Aarav, Anaya Sharma"},
            expected_traveller_name="Aarav Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma", "Aarav Sharma", "Anaya Sharma"]
        )
        self.assertTrue(r3b["valid"])

        # 4. Family booking voucher
        r4 = dp.validate_traveller_identity(
            doc_type="Hotel Voucher",
            extracted_fields={"Guest Name": "Sharma Family - 4 travellers"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma"]
        )
        self.assertTrue(r4["valid"])
        self.assertEqual(r4.get("severity"), "warning")

        # 5. Shared voucher: lead guest is another trip traveller
        r5 = dp.validate_traveller_identity(
            doc_type="Hotel Voucher",
            extracted_fields={"Guest Name": "Priya Sharma"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma"]
        )
        self.assertTrue(r5["valid"])
        self.assertEqual(r5.get("severity"), "warning")

        # 6. Passport strict mismatch: Priya Sharma passport uploaded to Rahul Sharma requirement
        r6 = dp.validate_traveller_identity(
            doc_type="Passport",
            extracted_fields={"Full Name": "Priya Sharma"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma"]
        )
        self.assertFalse(r6["valid"])
        self.assertEqual(r6.get("severity"), "error")

        # 7. Visa strict mismatch: Priya Sharma visa uploaded to Rahul Sharma requirement
        r7 = dp.validate_traveller_identity(
            doc_type="Visa / Entry Document",
            extracted_fields={"Traveller Name": "Priya Sharma"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma"]
        )
        self.assertFalse(r7["valid"])
        self.assertEqual(r7.get("severity"), "error")

        # 8. Cross-customer mismatch: Amit Mehta uploaded to Rahul Sharma
        r8 = dp.validate_traveller_identity(
            doc_type="Passport",
            extracted_fields={"Full Name": "Amit Mehta"},
            expected_traveller_name="Rahul Sharma",
            trip_travellers=["Rahul Sharma", "Priya Sharma"],
            customer_name="Rahul Sharma"
        )
        self.assertFalse(r8["valid"])
        self.assertEqual(r8.get("severity"), "error")

    def test_09_service_layer_mismatch_blocking_and_supervisor_override(self):
        """Verify services.save_document blocks unauthorized mismatches and enforces supervisor override with reason."""
        import tempfile
        import sqlite3
        import database
        import services
        import auth_services

        test_dir = tempfile.mkdtemp()
        test_db_path = os.path.join(test_dir, "test_isolated.db")
        orig_db_path = database.DB_PATH
        
        try:
            database.DB_PATH = test_db_path
            database.init_db()
            
            # Setup test data in isolated DB
            conn = sqlite3.connect(test_db_path)
            conn.execute("INSERT INTO customers (id, name, customer_type, status) VALUES ('CUST-T1', 'Test Customer', 'Individual', 'Active')")
            conn.execute("INSERT INTO travellers (id, customer_id, name, type, role) VALUES ('TRAV-T1', 'CUST-T1', 'Rahul Sharma', 'Adult', 'Lead')")
            conn.execute("INSERT INTO trips (id, customer_id, name, start_date, end_date, destination, status) VALUES ('TRIP-T1', 'CUST-T1', 'Dubai Tour', '2026-12-01', '2026-12-05', 'Dubai', 'Planning')")
            conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES ('TRIP-T1', 'TRAV-T1')")
            conn.execute("INSERT INTO requirements (id, trip_id, traveller_id, name, type) VALUES ('REQ-PASSPORT', 'TRIP-T1', 'TRAV-T1', 'Passport', 'Mandatory')")
            
            # Setup users: Staff and Supervisor
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash BLOB,
                salt BLOB,
                full_name TEXT,
                role TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """)
            staff_token = "token-staff-test"
            sup_token = "token-sup-test"
            salt = b'1234567812345678'
            pwd_hash = hashlib.pbkdf2_hmac('sha256', b'pass', salt, 100000)
            conn.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES ('U-STF', 'staff1', ?, ?, 'Staff Person', 'Staff')", (pwd_hash, salt))
            conn.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES ('U-SUP', 'sup1', ?, ?, 'Supervisor Person', 'Supervisor')", (pwd_hash, salt))
            conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, 'U-STF', '2030-01-01')", (staff_token,))
            conn.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (?, 'U-SUP', '2030-01-01')", (sup_token,))
            conn.commit()
            conn.close()

            # Mismatched file: Rohan Test passport uploaded to Rahul Sharma passport requirement
            sample_mismatch_pdf = os.path.join(self.rohan_dir, "01_Passport_Demo.pdf")
            extracted_mismatch_data = {"Full Name": "Rohan Test", "Passport Number": "DEMO-PASSPORT-0001"}

            # Case 1: Un-overridden mismatch -> ValueError
            with self.assertRaises(ValueError) as ctx1:
                services.save_document(
                    requirement_id='REQ-PASSPORT',
                    file_path=sample_mismatch_pdf,
                    extracted_data=extracted_mismatch_data,
                    session_token=staff_token,
                    override_mismatch=False
                )
            self.assertIn("Save blocked by validation guard", str(ctx1.exception))

            # Case 2: Staff attempts override -> PermissionError
            with self.assertRaises(PermissionError) as ctx2:
                services.save_document(
                    requirement_id='REQ-PASSPORT',
                    file_path=sample_mismatch_pdf,
                    extracted_data=extracted_mismatch_data,
                    session_token=staff_token,
                    override_mismatch=True,
                    override_reason="Staff override attempt"
                )
            self.assertIn("Unauthorized: Role 'Staff' cannot authorize", str(ctx2.exception))

            # Case 3: Supervisor attempts override without reason -> ValueError
            with self.assertRaises(ValueError) as ctx3:
                services.save_document(
                    requirement_id='REQ-PASSPORT',
                    file_path=sample_mismatch_pdf,
                    extracted_data=extracted_mismatch_data,
                    session_token=sup_token,
                    override_mismatch=True,
                    override_reason=""
                )
            self.assertIn("override reason is mandatory", str(ctx3.exception))

            # Case 4: Supervisor attempts override with valid reason -> SUCCESS & ACTIVITY LOGGED
            doc_id = services.save_document(
                requirement_id='REQ-PASSPORT',
                file_path=sample_mismatch_pdf,
                extracted_data=extracted_mismatch_data,
                session_token=sup_token,
                override_mismatch=True,
                override_reason="Authorized testing override by senior supervisor"
            )
            self.assertTrue(doc_id.startswith("DOC-"))

            # Verify activity record was created
            conn = sqlite3.connect(test_db_path)
            conn.row_factory = sqlite3.Row
            act = conn.execute("SELECT * FROM activity WHERE trip_id = 'TRIP-T1' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(act)
            self.assertIn("Mismatch override authorized by Supervisor Person", act['description'])
            self.assertIn("Authorized testing override", act['description'])
            conn.close()

        finally:
            database.DB_PATH = orig_db_path
            try:
                import shutil
                shutil.rmtree(test_dir, ignore_errors=True)
            except Exception:
                pass

if __name__ == "__main__":
    unittest.main()
