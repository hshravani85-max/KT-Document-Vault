import sys
import os
import hashlib
import sqlite3
import json

prod_db_path = os.path.abspath('data/kt_vault_v3.db')
with open(prod_db_path, 'rb') as f:
    baseline_hash = hashlib.sha256(f.read()).hexdigest()
baseline_size = os.path.getsize(prod_db_path)

test_db_path = os.path.abspath('data/test_stage1_sandbox.db')
if os.path.exists(test_db_path):
    os.remove(test_db_path)

test_conn = sqlite3.connect(test_db_path)
test_cursor = test_conn.cursor()

test_cursor.executescript('''
CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, customer_type TEXT, status TEXT, mobile TEXT, email TEXT);
CREATE TABLE travellers (id TEXT PRIMARY KEY, customer_id TEXT, name TEXT, type TEXT, role TEXT, dob TEXT, relationship TEXT, passport_number TEXT, nationality TEXT);
CREATE TABLE trips (id TEXT PRIMARY KEY, customer_id TEXT, name TEXT, destination TEXT, start_date TEXT, end_date TEXT, trip_type TEXT, service TEXT, department TEXT, status TEXT);
CREATE TABLE trip_travellers (trip_id TEXT, traveller_id TEXT, PRIMARY KEY(trip_id, traveller_id));
CREATE TABLE requirements (id TEXT PRIMARY KEY, trip_id TEXT, traveller_id TEXT, name TEXT, type TEXT, UNIQUE(trip_id, traveller_id, name));
CREATE TABLE documents (id TEXT PRIMARY KEY, requirement_id TEXT, status TEXT, extracted_data TEXT, file_path TEXT, uploaded_at TEXT);
CREATE TABLE user_profile (customer_id TEXT PRIMARY KEY, full_name TEXT, dob TEXT, nationality TEXT, passport_number TEXT, passport_expiry TEXT);
CREATE TABLE activity (id INTEGER PRIMARY KEY AUTOINCREMENT, trip_id TEXT, description TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, customer_id TEXT);
CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash BLOB, salt BLOB, full_name TEXT, role TEXT);
CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, expires_at DATETIME);
''')

test_cursor.execute("INSERT INTO users VALUES ('U-01', 'admin', ?, ?, 'Admin User', 'Admin')", (b'123', b'456'))
test_cursor.execute("INSERT INTO sessions VALUES ('TEST_TOKEN_ADMIN', 'U-01', datetime('now'), datetime('now', '+1 day'))")

test_cursor.execute("INSERT INTO customers VALUES ('CUST-01', 'Synthetic Amit', 'Individual', 'Active', '111', 'amit@test.com')")
test_cursor.execute("INSERT INTO travellers VALUES ('TR-01', 'CUST-01', 'Synthetic Amit', 'Adult', 'Lead', '1990-01-01', 'Self', 'P-AMIT-01', 'Indian')")
test_cursor.execute("INSERT INTO trips VALUES ('TRIP-01', 'CUST-01', 'Dubai Trip', 'Dubai', '2026-12-01', '2026-12-10', 'Leisure', 'All', 'Ops', 'NOT READY')")
test_cursor.execute("INSERT INTO trip_travellers VALUES ('TRIP-01', 'TR-01')")
test_cursor.execute("INSERT INTO requirements VALUES ('REQ-TRIP-AMIT', 'TRIP-01', 'TR-01', 'Passport', 'TRAVELLER')")

test_cursor.execute("INSERT INTO customers VALUES ('CUST-02', 'Synthetic Neha', 'Individual', 'Active', '222', 'neha@test.com')")
test_cursor.execute("INSERT INTO travellers VALUES ('TR-02', 'CUST-02', 'Synthetic Neha', 'Adult', 'Lead', '1995-05-05', 'Self', 'P-NEHA-02', 'Indian')")
test_cursor.execute("INSERT INTO trips VALUES ('TRIP-02', 'CUST-02', 'Singapore Trip', 'Singapore', '2027-01-01', '2027-01-10', 'Leisure', 'All', 'Ops', 'NOT READY')")
test_cursor.execute("INSERT INTO trip_travellers VALUES ('TRIP-02', 'TR-02')")
test_cursor.execute("INSERT INTO requirements VALUES ('REQ-TRIP-NEHA', 'TRIP-02', 'TR-02', 'Passport', 'TRAVELLER')")
test_cursor.execute("INSERT INTO requirements VALUES ('REQ-VAULT-NEHA', NULL, 'TR-02', 'Passport', 'TRAVELLER_VAULT')")

test_cursor.execute("INSERT INTO requirements VALUES ('REQ-ORPHAN', NULL, NULL, 'Passport', 'TRAVELLER')")

test_conn.commit()
test_conn.close()

import database
database.DB_PATH = test_db_path

conn_check = database.get_connection()
active_db = conn_check.execute('PRAGMA database_list').fetchall()[0]['file']
conn_check.close()
assert os.path.samefile(active_db, test_db_path), f'Database path redirection failed! Active: {active_db}'

import services
token = 'TEST_TOKEN_ADMIN'

print('--- RUNNING STAGE 1 TESTS AGAINST ISOLATED SYNTHETIC SANDBOX ---')

amit_data = {
    'Full Name': 'Synthetic Amit',
    'Date of Birth': '01 Jan 1990',
    'Nationality': 'Indian',
    'Passport Number': 'P-AMIT-01',
    'Expiry Date': '01 Jan 2030'
}
services.save_document('REQ-TRIP-AMIT', 'dummy/path/amit.pdf', amit_data, token)

conn_test = database.get_connection()
p_amit = conn_test.execute("SELECT * FROM user_profile WHERE customer_id = 'CUST-01'").fetchone()
assert p_amit is not None, 'Amit profile not created!'
assert p_amit['full_name'] == 'Synthetic Amit'
assert p_amit['passport_number'] == 'P-AMIT-01'
print('Test 1 (Amit Trip Passport): PASS -> Profile created correctly for CUST-01')

neha_trip_data = {
    'Full Name': 'Synthetic Neha',
    'Date of Birth': '05 May 1995',
    'Nationality': 'Indian',
    'Passport Number': 'P-NEHA-02',
    'Expiry Date': '05 May 2035'
}
services.save_document('REQ-TRIP-NEHA', 'dummy/path/neha.pdf', neha_trip_data, token)

p_neha = conn_test.execute("SELECT * FROM user_profile WHERE customer_id = 'CUST-02'").fetchone()
p_amit_check = conn_test.execute("SELECT * FROM user_profile WHERE customer_id = 'CUST-01'").fetchone()

assert p_neha is not None, 'Neha profile not created!'
assert p_neha['full_name'] == 'Synthetic Neha'
assert p_neha['passport_number'] == 'P-NEHA-02'
assert p_amit_check['full_name'] == 'Synthetic Amit', 'Amit profile was overwritten!'
assert p_amit_check['passport_number'] == 'P-AMIT-01', 'Amit passport was overwritten!'
print('Test 2 (Neha Trip Passport - Overwrite Prevention): PASS -> CUST-02 created, CUST-01 untouched')

neha_vault_data = {
    'Full Name': 'Synthetic Neha Updated',
    'Date of Birth': '05 May 1995',
    'Nationality': 'Indian',
    'Passport Number': 'P-NEHA-VAULT-99',
    'Expiry Date': '05 May 2035'
}
services.save_document('REQ-VAULT-NEHA', 'dummy/path/neha_vault.pdf', neha_vault_data, token)

p_neha_vault = conn_test.execute("SELECT * FROM user_profile WHERE customer_id = 'CUST-02'").fetchone()
p_amit_check2 = conn_test.execute("SELECT * FROM user_profile WHERE customer_id = 'CUST-01'").fetchone()

assert p_neha_vault['passport_number'] == 'P-NEHA-VAULT-99'
assert p_amit_check2['passport_number'] == 'P-AMIT-01', 'Amit profile was corrupted by vault update!'
print('Test 3 (Traveller Vault Passport - trip_id NULL): PASS -> Resolved customer via traveller relationship')

orphan_data = {
    'Full Name': 'Unknown Orphan',
    'Date of Birth': '01 Jan 2000',
    'Nationality': 'Unknown',
    'Passport Number': 'P-ORPHAN-00',
    'Expiry Date': '01 Jan 2030'
}
doc_id_orphan = services.save_document('REQ-ORPHAN', 'dummy/path/orphan.pdf', orphan_data, token)
assert doc_id_orphan is not None, 'Document row should still be saved even if profile sync is skipped'

profiles = conn_test.execute("SELECT customer_id FROM user_profile").fetchall()
profile_ids = [row['customer_id'] for row in profiles]
assert 'KT-C-0001' not in profile_ids, 'Default KT-C-0001 was erroneously assigned!'
assert len(profile_ids) == 2, f'Expected 2 profiles (CUST-01, CUST-02), found: {profile_ids}'
print('Test 4 (Orphaned Requirement): PASS -> Profile sync safely skipped without assigning default ID')

conn_test.close()

if os.path.exists(test_db_path):
    os.remove(test_db_path)

with open(prod_db_path, 'rb') as f:
    post_test_hash = hashlib.sha256(f.read()).hexdigest()
post_test_size = os.path.getsize(prod_db_path)

assert post_test_hash == baseline_hash, 'CRITICAL FAILURE: Production database hash changed!'
assert post_test_size == baseline_size, 'CRITICAL FAILURE: Production database size changed!'

print('\n--- PRODUCTION DATABASE SAFETY VERIFICATION ---')
print('Baseline SHA256: ', baseline_hash)
print('Post-Test SHA256:', post_test_hash)
print('Status: IDENTICAL (Zero production bytes written)')
print('ALL STAGE 1 VERIFICATIONS COMPLETED SUCCESSFULLY')
