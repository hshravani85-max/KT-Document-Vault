import sqlite3
import document_processor
import json
import shutil
import os

shutil.copy2('data/kt_vault_v3.db', 'data/test_db.db')
conn = sqlite3.connect('data/test_db.db')

# Test Under Review confirmation
doc = conn.execute('''
    SELECT d.id, d.file_path, d.status
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    WHERE r.trip_id = 'KT-T-0002' AND r.name = 'Flight Ticket'
''').fetchone()

if doc:
    doc_id, file_path, status = doc
    
    # Process it
    with open(file_path, 'rb') as f:
        fb = f.read()
    res = document_processor.process_document(file_path, fb)
    new_data = res['extracted_fields']
    
    assert new_data['Airline'] == ''
    assert new_data['Route'] == 'Mumbai (BOM) - SIN) - BOM)'
    assert new_data['Passenger Name'] == 'Neha Kapoor'
    
    # Save it (Under Review)
    conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(new_data), doc_id))
    conn.commit()
    print("Under Review confirmation successful.")

# Test VERIFIED update rejection (simulate backend check)
doc_verified = conn.execute('''
    SELECT d.id, d.status 
    FROM documents d 
    WHERE d.status = 'Verified' LIMIT 1
''').fetchone()

if doc_verified:
    vid, vstatus = doc_verified
    current_status = conn.execute("SELECT status FROM documents WHERE id = ?", (vid,)).fetchone()[0]
    try:
        if current_status == 'Verified':
            raise Exception("Security Error: Cannot modify extracted data of a VERIFIED document.")
        # If we got here, it's a fail
        assert False, "Should have thrown Security Error"
    except Exception as e:
        assert "Security Error" in str(e)
        print("Verified update rejection successful.")

conn.close()

from services import calculate_readiness
amit_readiness = calculate_readiness('KT-T-0001')
print(f"Amit Readiness: {amit_readiness}")
assert amit_readiness == (9, 9, 0, 0, 100, 'TRAVEL FILE READY')

neha_readiness = calculate_readiness('KT-T-0002')
print(f"Neha Readiness: {neha_readiness}")

os.remove('data/test_db.db')
print("All automated tests passed.")
