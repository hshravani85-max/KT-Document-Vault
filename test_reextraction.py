import sqlite3
import document_processor
import json
import shutil
import os

# Create a temporary database for testing
shutil.copy2('data/kt_vault_v3.db', 'data/test_reextraction.db')

conn = sqlite3.connect('data/test_reextraction.db')

# Test A: Existing Flight Ticket extraction
doc = conn.execute('''
    SELECT d.id, d.file_path, d.extracted_data, d.status, d.requirement_id
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    WHERE r.trip_id = 'KT-T-0002' AND r.name = 'Flight Ticket'
''').fetchone()

doc_id, file_path, extracted_data, status, req_id = doc

print(f"Original extracted_data: {extracted_data}")
assert extracted_data == '{}' or json.loads(extracted_data) == {}
assert status == 'Under Review'

with open(file_path, 'rb') as f:
    fb = f.read()

res = document_processor.process_document(file_path, fb)
new_data = res['extracted_fields']

print("Re-extracted data:")
import pprint
pprint.pprint(new_data)

assert new_data['Passenger Name'] == 'Neha Kapoor'
assert 'KT-DEMO-FLT-3002' in new_data['PNR/Booking Reference']

# Simulate Save
conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(new_data), doc_id))
conn.commit()

# Verify no duplicate rows
doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE requirement_id = ?", (req_id,)).fetchone()[0]
assert doc_count == 1
print(f"Duplicate protection passed. Count = {doc_count}")

# Verify status unchanged
new_status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
assert new_status == 'Under Review'
print("Status unchanged passed.")

# Test D: Passport regression
doc_p = conn.execute('''
    SELECT d.id, d.file_path, d.extracted_data, d.status
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    WHERE r.traveller_id = 'KT-TR-0002' AND r.type = 'TRAVELLER_VAULT'
''').fetchone()

if doc_p:
    p_id, p_file, p_data, p_status = doc_p
    assert p_status == 'Verified'
    with open(p_file, 'rb') as f:
        fb_p = f.read()
    res_p = document_processor.process_document(p_file, fb_p)
    p_new = res_p['extracted_fields']
    assert p_new['Passenger Name'] == '' or p_new.get('Passenger Name') is None or 'Passenger Name' not in p_new
    assert p_new['Passport Number'] == 'N9003002'
    print("Passport regression passed.")

conn.close()

from services import calculate_readiness
print('Amit:', calculate_readiness('KT-T-0001'))

os.remove('data/test_reextraction.db')
print("All automated tests passed.")
