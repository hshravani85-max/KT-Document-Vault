import re

with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace verify_document
old_verify = """def verify_document(doc_id):
    conn = database.get_connection()
    conn.execute("UPDATE documents SET status = 'Verified' WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()"""

new_verify = """def verify_document(doc_id, actor="Staff Member (Demo)"):
    import json
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT status, extracted_data, requirement_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc: raise ValueError("Document not found.")
        if doc['status'] == 'Verified': return
        
        req = conn.execute("SELECT name, type, trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        
        # Validation rules
        data = json.loads(doc['extracted_data']) if doc['extracted_data'] else {}
        if not data:
            raise ValueError("Extracted information is empty. Please complete re-extraction before verifying.")
            
        mandatory = []
        if req['name'] == 'Passport':
            mandatory = ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Expiry Date']
        elif req['name'] == 'Flight Ticket':
            mandatory = ['Passenger Name', 'PNR/Booking Reference', 'Route', 'Departure Date/Time', 'Arrival Date/Time']
            
        for m in mandatory:
            val = data.get(m)
            if not val or not str(val).strip():
                raise ValueError(f"Cannot verify: Missing mandatory field '{m}'.")
                
        conn.execute("UPDATE documents SET status = 'Verified' WHERE id = ?", (doc_id,))
        
        # Add to document_history
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason)
            VALUES (?, 'VERIFY', ?, 'Verified', ?, 'Verification completed')
        ''', (doc_id, doc['status'], actor))
        
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def reopen_document(doc_id, reason, actor):
    if not reason or not reason.strip():
        raise ValueError("Correction reason is required.")
    if actor in [None, 'Staff Member (Demo)', '']:
        raise PermissionError("Unauthorized: Valid authenticated staff identity required with proper RBAC roles.")
        
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("Document not found.")
        if doc['status'] != 'Verified':
            raise ValueError("Only VERIFIED documents can be reopened.")
            
        req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        
        # Revert final approval if necessary
        if req['trip_id']:
            trip = conn.execute("SELECT status FROM trips WHERE id = ?", (req['trip_id'],)).fetchone()
            if trip and trip['status'] == 'TRAVEL FILE READY':
                conn.execute("UPDATE trips SET status = 'NOT READY' WHERE id = ?", (req['trip_id'],))
        
        # Append history
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason)
            VALUES (?, 'REOPEN', 'Verified', 'Under Review', ?, ?)
        ''', (doc_id, actor, reason.strip()))
        
        # Status change
        conn.execute("UPDATE documents SET status = 'Under Review' WHERE id = ?", (doc_id,))
        
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()"""

content = content.replace(old_verify, new_verify)

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("services.py patched.")
