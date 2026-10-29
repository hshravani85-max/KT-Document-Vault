import auth_services
import database
import json

def get_trip_details(trip_id):
    conn = database.get_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    conn.close()
    return dict(trip) if trip else None

def get_requirements(trip_id):
    conn = database.get_connection()
    reqs = conn.execute('''
        SELECT r.*, d.id as doc_id, d.status as doc_status, d.extracted_data
        FROM requirements r
        LEFT JOIN documents d ON r.id = d.requirement_id
        WHERE r.trip_id = ?
    ''', (trip_id,)).fetchall()
    conn.close()
    return [dict(r) for r in reqs]

def get_document(doc_id):
    conn = database.get_connection()
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return dict(doc) if doc else None

def get_all_documents_for_review():
    conn = database.get_connection()
    docs = conn.execute('''
        SELECT d.*, r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id, 
               t.name as traveller_name, tr.name as trip_name, 
               COALESCE(tr.customer_id, t.customer_id) as customer_id, 
               COALESCE(c.name, c2.name) as customer_name
        FROM documents d
        JOIN requirements r ON d.requirement_id = r.id
        LEFT JOIN travellers t ON r.traveller_id = t.id
        LEFT JOIN trips tr ON r.trip_id = tr.id
        LEFT JOIN customers c ON tr.customer_id = c.id
        LEFT JOIN customers c2 ON t.customer_id = c2.id
        WHERE d.status = 'Under Review'
    ''').fetchall()
    conn.close()
    return [dict(d) for d in docs]

def calculate_readiness(trip_id):
    reqs = get_requirements(trip_id)
    trip = get_trip_details(trip_id)
    current_trip_status = trip.get('status') if trip else None
    
    total = len(reqs)
    if total == 0: 
        return 0, 0, 0, 0, 0, "NOT READY"
        
    complete = 0
    attention = 0
    missing = 0
    for r in reqs:
        status = r.get('doc_status')
        if not status or status in ['Replace Required', 'Re-upload Required', 'Action Required']:
            missing += 1
        elif status == 'Verified':
            complete += 1
        else:
            attention += 1
            
    pct = int((complete/total)*100)
    
    if current_trip_status == 'TRAVEL FILE READY':
        business_status = 'TRAVEL FILE READY'
    elif complete == total and missing == 0 and attention == 0:
        business_status = 'READY FOR FINAL REVIEW'
    else:
        business_status = 'NOT READY'
        
    return total, complete, attention, missing, pct, business_status

def save_document(requirement_id, file_path, extracted_data, session_token):
    import auth_services
    if not session_token: raise PermissionError('Unauthenticated')
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    import uuid
    from datetime import datetime
    doc_id = 'DOC-' + str(uuid.uuid4())[:8]
    conn = database.get_connection()
    existing = conn.execute("SELECT id FROM documents WHERE requirement_id = ?", (requirement_id,)).fetchone()
    if existing:
        conn.execute("UPDATE documents SET status = ?, file_path = ?, extracted_data = ?, uploaded_at = ? WHERE id = ?",
                     ('Under Review', file_path, json.dumps(extracted_data), datetime.now().isoformat(), existing['id']))
    else:
        conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (doc_id, requirement_id, 'Under Review', json.dumps(extracted_data), file_path, datetime.now().isoformat()))
    
    req_info = conn.execute('''
        SELECT r.name, COALESCE(t.customer_id, tr.customer_id) AS customer_id
        FROM requirements r
        LEFT JOIN trips t ON r.trip_id = t.id
        LEFT JOIN travellers tr ON r.traveller_id = tr.id
        WHERE r.id = ?
    ''', (requirement_id,)).fetchone()
    if req_info and req_info['name'] == 'Passport' and req_info['customer_id']:
        conn.execute("INSERT OR REPLACE INTO user_profile (customer_id, full_name, dob, nationality, passport_number, passport_expiry) VALUES (?, ?, ?, ?, ?, ?)",
                     (req_info['customer_id'], extracted_data.get('Full Name'), extracted_data.get('Date of Birth'), extracted_data.get('Nationality'), extracted_data.get('Passport Number'), extracted_data.get('Expiry Date')))
    
    conn.commit()
    conn.close()
    return doc_id

def verify_document(doc_id, session_token):
    import json
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']
    
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
        req_name = req['name']
        if req_name == 'Passport':
            mandatory = ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Expiry Date']
        elif req_name == 'Flight Ticket':
            mandatory = ['Passenger Name', 'PNR/Booking Reference', 'Route', 'Departure Date/Time', 'Arrival Date/Time']
        elif req_name == 'Visa / Entry Document':
            mandatory = ['Traveller Name', 'Visa Number / Reference', 'Destination']
        elif req_name == 'Hotel Voucher':
            mandatory = ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number']
        elif req_name == 'Travel Insurance':
            mandatory = ['Insured Name', 'Policy Number', 'Valid From', 'Valid Until']
        elif req_name == 'Transfer Voucher':
            mandatory = ['Passenger Name', 'Booking Reference', 'Pickup Location', 'Dropoff Location', 'Transfer Date']
        elif req_name == 'Sightseeing Voucher':
            mandatory = ['Guest Name', 'Booking Reference', 'Tour / Activity Name', 'Activity Date']
        elif req_name == 'Arrival / Entry Document':
            mandatory = ['Traveller Name', 'Destination', 'Arrival Date', 'Reference Number']
        elif req_name == 'Itinerary':
            mandatory = ['Start Date', 'End Date', 'Schedule Summary']
            
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

def reopen_document(doc_id, reason, session_token):
    if not reason or not reason.strip():
        raise ValueError("Correction reason is required.")
        
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']
        
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
        conn.close()

def generate_next_id(conn, table, prefix):
    prefix_len = len(prefix) + 1
    cursor = conn.cursor()
    query = f"SELECT MAX(CAST(SUBSTR(id, ?) AS INTEGER)) FROM {table} WHERE id LIKE ?"
    cursor.execute(query, (prefix_len, f"{prefix}%"))
    result = cursor.fetchone()[0]
    next_num = 1 if result is None else result + 1
    return f"{prefix}{next_num:04d}"

def create_customer(full_name, mobile=None, email=None, customer_type="Individual", session_token=None):
    import auth_services
    if not session_token: raise PermissionError('Unauthenticated')
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'customers', 'KT-C-')
        conn.execute('''
            INSERT INTO customers (id, name, mobile, email, customer_type, status)
            VALUES (?, ?, ?, ?, ?, 'Active')
        ''', (new_id, full_name, mobile, email, customer_type))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (new_id, f"Customer created: {full_name}"))
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None, session_token=None):
    import auth_services
    if not session_token: raise PermissionError('Unauthenticated')
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'travellers', 'KT-TR-')
        conn.execute('''
            INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role, passport_number, nationality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, customer_id, full_name, dob, traveller_type, relationship, 'Lead Traveller' if lead_traveller else 'Standard', passport_number, nationality))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (customer_id, f"Traveller added: {full_name}"))
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids, session_token=None):
    import auth_services
    if not session_token: raise PermissionError('Unauthenticated')
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    conn = database.get_connection()
    try:
        import uuid
        new_id = generate_next_id(conn, 'trips', 'KT-T-')
        
        conn.execute('''
            INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NOT READY')
        ''', (new_id, customer_id, name, destination, start_date, end_date, trip_type, service, department))
        
        for tr_id in traveller_ids:
            conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES (?, ?)", (new_id, tr_id))
            
            for doc_name in ["Passport", "Visa / Entry Document"]:
                req_id = f"REQ-TR-{uuid.uuid4().hex[:6]}"
                conn.execute('''
                    INSERT INTO requirements (id, trip_id, traveller_id, name, type) 
                    VALUES (?, ?, ?, ?, 'TRAVELLER')
                ''', (req_id, new_id, tr_id, doc_name))
                
                existing_doc = conn.execute('''
                    SELECT d.* FROM documents d
                    JOIN requirements r ON d.requirement_id = r.id
                    WHERE r.traveller_id = ? AND r.name = ? AND r.type = 'TRAVELLER_VAULT'
                    ORDER BY d.uploaded_at DESC LIMIT 1
                ''', (tr_id, doc_name)).fetchone()
                
                if existing_doc:
                    conn.execute('''
                        INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (f"DOC-{uuid.uuid4().hex[:8]}", req_id, existing_doc['status'], existing_doc['extracted_data'], existing_doc['file_path'], existing_doc['uploaded_at']))
            
        trip_reqs = [
            'Flight Ticket', 'Hotel Voucher', 'Travel Insurance', 
            'Transfer Voucher', 'Sightseeing Voucher', 'Arrival / Entry Document', 'Itinerary'
        ]
        for tr in trip_reqs:
            conn.execute('''
                INSERT INTO requirements (id, trip_id, traveller_id, name, type)
                VALUES (?, ?, NULL, ?, 'TRIP')
            ''', (f"REQ-T-{uuid.uuid4().hex[:6]}", new_id, tr))
            
        conn.execute('''
            INSERT INTO activity (trip_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (new_id, f"Trip created: {name}"))
        
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()
