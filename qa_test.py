import sqlite3
import json
import shutil
import os
import services
import auth_services

def run_qa_tests():
    shutil.copy2('data/kt_vault_v3.db', 'data/test_qa.db')
    services.database.DB_PATH = 'data/test_qa.db' # Mock the DB path for services
    
    conn = sqlite3.connect('data/test_qa.db')
    
    # 1. Login to get tokens
    admin_session = auth_services.authenticate_user('admin', 'admin123')
    staff_session = auth_services.authenticate_user('staff', 'staff123')
    super_session = auth_services.authenticate_user('supervisor', 'super123')
    
    admin_token = admin_session['token']
    staff_token = staff_session['token']
    
    doc_id = 'DOC-4c9a4d78' # Verified flight ticket
    
    print("Test A: Unauthorized reopening is rejected (Staff)")
    try:
        services.reopen_document(doc_id, "Need to fix route", staff_token)
        assert False, "Should have rejected unauthorized actor"
    except PermissionError as e:
        print(" -> PASS (Staff blocked)")
        
    print("Test B: Empty correction reason is rejected")
    try:
        services.reopen_document(doc_id, "   ", admin_token)
        assert False, "Should have rejected empty reason"
    except ValueError as e:
        assert "Correction reason is required" in str(e)
        print(" -> PASS (Empty reason blocked)")
        
    print("Test C: Verified document successfully reopens with a reason (Admin)")
    services.reopen_document(doc_id, "Fixing flight route formatting", admin_token)
    status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
    assert status == 'Under Review'
    
    hist = conn.execute("SELECT * FROM document_history WHERE document_id = ?", (doc_id,)).fetchall()
    assert len(hist) == 1
    assert hist[0][2] == 'REOPEN'
    assert hist[0][5] == 'System Admin' # Actor name
    print(" -> PASS (Reopened successfully, history preserved)")
    
    print("Test D: Empty mandatory extracted information blocks verification")
    conn.execute("UPDATE documents SET extracted_data = '{}' WHERE id = ?", (doc_id,))
    conn.commit()
    try:
        services.verify_document(doc_id, admin_token)
        assert False, "Should have blocked verification"
    except ValueError as e:
        print(" -> PASS (Empty extracted data blocked)")
        
    valid_data = {
        'Passenger Name': 'Neha Kapoor',
        'Route': 'Mumbai - SIN',
        'Departure Date/Time': '20 Jan',
        'Arrival Date/Time': '26 Jan',
        'PNR/Booking Reference': 'KT-DEMO-FLT-3002'
    }
    conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(valid_data), doc_id))
    conn.commit()
    
    print("Test E: Staff cannot verify")
    try:
        services.verify_document(doc_id, staff_token)
        assert False, "Staff should not be able to verify"
    except PermissionError as e:
        print(" -> PASS (Staff verification blocked)")
        
    print("Test F: Re-verification by Admin creates new history")
    services.verify_document(doc_id, admin_token)
    status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
    assert status == 'Verified'
    hist = conn.execute("SELECT * FROM document_history WHERE document_id = ? ORDER BY id ASC", (doc_id,)).fetchall()
    assert len(hist) == 2
    assert hist[1][2] == 'VERIFY'
    assert hist[1][5] == 'System Admin'
    print(" -> PASS (Re-verification successful, history preserved)")
    
    print("Test G: Consolidated PDF Generation")
    import travel_file_generator
    pdf_path = travel_file_generator.generate_consolidated_travel_file('KT-T-0001')
    assert os.path.exists(pdf_path)
    print(" -> PASS (PDF Generated at", pdf_path, ")")

    conn.close()
    
    # Restore original path
    services.database.DB_PATH = 'data/kt_vault_v3.db'
    os.remove('data/test_qa.db')
    print("\\nALL TESTS COMPLETED SUCCESSFULLY")

if __name__ == "__main__":
    run_qa_tests()
