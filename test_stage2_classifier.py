import os
import hashlib
import document_processor

prod_db_path = os.path.abspath('data/kt_vault_v3.db')
with open(prod_db_path, 'rb') as f:
    baseline_hash = hashlib.sha256(f.read()).hexdigest()
baseline_size = os.path.getsize(prod_db_path)

fixtures = [
    ('01_Amit_Mehta_Demo_Passport.pdf', 'Passport'),
    ('01_Neha_Kapoor_DEMO_Passport.pdf', 'Passport'),
    ('02_Amit_Mehta_Demo_Visa_Entry.pdf', 'Visa / Entry Document'),
    ('trip_upload_ac7aa46c85fc493c8ac7774cceb4fce6.pdf', 'Flight Ticket'),
    ('04_Dubai_Hotel_Voucher.pdf', 'Hotel Voucher'),
    ('05_Travel_Insurance.pdf', 'Travel Insurance'),
    ('06_Transfer_Voucher.pdf', 'Transfer Voucher'),
    ('07_Sightseeing_Voucher.pdf', 'Sightseeing Voucher'),
    ('08_Arrival_Entry_Document.pdf', 'Arrival / Entry Document'),
    ('09_Dubai_Itinerary.pdf', 'Itinerary')
]

print('--- STAGE 2 CLASSIFIER TESTING (ALL 10 SYNTHETIC FIXTURES) ---')
all_passed = True

for filename, expected_type in fixtures:
    path = os.path.join('documents', filename)
    with open(path, 'rb') as f:
        file_bytes = f.read()
    
    result = document_processor.process_document(filename, file_bytes)
    actual_type = result['document_type']
    confidence = result['type_confidence']
    
    status = 'PASS' if (actual_type == expected_type and confidence == 'high') else 'FAIL'
    if status == 'FAIL':
        all_passed = False
        
    print(f"[{status}] {filename:<50} -> Expected: {expected_type:<24} | Detected: {actual_type:<24} (Conf: {confidence})")

assert all_passed, "One or more document classification tests failed!"

with open(prod_db_path, 'rb') as f:
    post_test_hash = hashlib.sha256(f.read()).hexdigest()
post_test_size = os.path.getsize(prod_db_path)

assert post_test_hash == baseline_hash, "CRITICAL ERROR: Production database hash changed!"
assert post_test_size == baseline_size, "CRITICAL ERROR: Production database size changed!"

print('\n--- PRODUCTION DATABASE INTEGRITY CHECK ---')
print('Baseline SHA256: ', baseline_hash)
print('Post-Test SHA256:', post_test_hash)
print('Status: IDENTICAL (Zero production writes)')
print('\nSTAGE 2 ALL TESTS PASSED SUCCESSFULLY')
