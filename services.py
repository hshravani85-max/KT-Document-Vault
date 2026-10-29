import re
import auth_services
import database
import json
import os
from datetime import datetime, date

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
    
    # Optional document types that do not penalize trip readiness when unfulfilled
    OPTIONAL_DOC_TYPES = {'Aadhaar Card', 'PAN Card'}
    
    eval_reqs = []
    for r in reqs:
        name = r.get('name')
        status = r.get('doc_status')
        if name in OPTIONAL_DOC_TYPES and (not status or status in ['Replace Required', 'Re-upload Required', 'Action Required']):
            continue
        eval_reqs.append(r)
        
    total = len(eval_reqs)
    if total == 0: 
        return 0, 0, 0, 0, 0, "NOT READY"
        
    complete = 0
    attention = 0
    missing = 0
    for r in eval_reqs:
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

def save_document(requirement_id, file_path, extracted_data, session_token, expected_trip_id=None, expected_customer_id=None, override_mismatch=False, override_reason=None):
    import auth_services
    import os
    import uuid
    import json
    from datetime import datetime
    import document_processor
    
    if not session_token:
        raise PermissionError('Unauthenticated')
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    
    if not requirement_id or not isinstance(requirement_id, str):
        raise ValueError("requirement_id must be a non-empty string.")
    if extracted_data is None or not isinstance(extracted_data, dict):
        raise ValueError("extracted_data must be a valid dictionary.")
    if not file_path or not isinstance(file_path, str) or not os.path.exists(file_path):
        raise ValueError(f"Document file does not exist on disk: '{file_path}'.")
        
    conn = database.get_connection()
    try:
        req_info = conn.execute('''
            SELECT r.id, r.name, r.trip_id, r.traveller_id,
                   t.customer_id AS trip_customer_id,
                   tr.customer_id AS traveller_customer_id,
                   COALESCE(t.customer_id, tr.customer_id) AS customer_id
            FROM requirements r
            LEFT JOIN trips t ON r.trip_id = t.id
            LEFT JOIN travellers tr ON r.traveller_id = tr.id
            WHERE r.id = ?
        ''', (requirement_id,)).fetchone()
        
        if not req_info:
            raise ValueError(f"Requirement not found: '{requirement_id}'.")
            
        if expected_trip_id is not None:
            if req_info['trip_id'] != expected_trip_id:
                raise ValueError(f"Trip mismatch: requirement '{requirement_id}' belongs to trip '{req_info['trip_id']}', but expected trip '{expected_trip_id}'.")
                
        if expected_customer_id is not None:
            if req_info['customer_id'] != expected_customer_id:
                raise ValueError(f"Customer mismatch: requirement '{requirement_id}' belongs to customer '{req_info['customer_id']}', but expected customer '{expected_customer_id}'.")

        # ----------------------------------------------------
        # Document Type & Identity Validation (Service Layer)
        # ----------------------------------------------------
        import storage_service
        doc_bytes = storage_service.read_decrypted_document(file_path, session_token=session_token, allow_external=True)
        proc_result = document_processor.process_document(os.path.basename(file_path), doc_bytes, expected_requirement=req_info['name'])
        detected_type = proc_result.get('document_type', 'Needs Review')
        type_conf = proc_result.get('type_confidence', 'low')

        req_name = req_info['name'].lower()
        KEYWORD_MAP = {
            'hotel': 'Hotel Voucher', 'flight': 'Flight Ticket', 'ticket': 'Flight Ticket',
            'passport': 'Passport', 'visa': 'Visa / Entry Document', 'insurance': 'Travel Insurance',
            'transfer': 'Transfer Voucher', 'cab': 'Transfer Voucher', 'taxi': 'Transfer Voucher',
            'sightseeing': 'Sightseeing Voucher', 'tour': 'Sightseeing Voucher', 'activity': 'Sightseeing Voucher',
            'land': 'Land Voucher', 'ground': 'Land Voucher',
            'aadhaar': 'Aadhaar Card', 'adhaar': 'Aadhaar Card', 'uidai': 'Aadhaar Card',
            'pan': 'PAN Card', 'pancard': 'PAN Card',
            'arrival': 'Arrival / Entry Document', 'entry': 'Arrival / Entry Document', 'itinerary': 'Itinerary'
        }
        expected_type = 'Needs Review'
        for kw, target in KEYWORD_MAP.items():
            if kw in req_name:
                expected_type = target
                break

        is_type_mismatch = (
            type_conf == 'high'
            and detected_type != 'Needs Review'
            and expected_type != 'Needs Review'
            and detected_type != expected_type
        )

        expected_traveller = None
        trip_travellers = []
        if req_info['traveller_id']:
            tr_row = conn.execute("SELECT name FROM travellers WHERE id = ?", (req_info['traveller_id'],)).fetchone()
            if tr_row:
                expected_traveller = tr_row['name']
        if req_info['trip_id']:
            tt_rows = conn.execute("SELECT tr.name FROM trip_travellers tt JOIN travellers tr ON tt.traveller_id = tr.id WHERE tt.trip_id = ?", (req_info['trip_id'],)).fetchall()
            trip_travellers = [r['name'] for r in tt_rows if r['name']]
        
        cust_row = conn.execute("SELECT name FROM customers WHERE id = ?", (req_info['customer_id'],)).fetchone() if req_info['customer_id'] else None
        customer_name = cust_row['name'] if cust_row else None

        validation_doc_type = detected_type if detected_type != 'Needs Review' else expected_type
        id_validation = document_processor.validate_traveller_identity(
            doc_type=validation_doc_type,
            extracted_fields=extracted_data,
            expected_traveller_name=expected_traveller,
            trip_travellers=trip_travellers,
            customer_name=customer_name
        )
        is_identity_mismatch = (not id_validation['valid'] and id_validation.get('severity') == 'error')

        if is_type_mismatch or is_identity_mismatch:
            mismatch_reasons = []
            if is_type_mismatch:
                mismatch_reasons.append(f"Document type mismatch (detected '{detected_type}' vs requirement '{req_info['name']}')")
            if is_identity_mismatch:
                mismatch_reasons.append(f"Traveller identity mismatch ({id_validation['message']})")
            error_details = " | ".join(mismatch_reasons)

            if not override_mismatch:
                raise ValueError(f"Save blocked by validation guard: {error_details}.")
            else:
                # Override requested: verify Supervisor/Admin role and mandatory reason
                if user['role'] not in ['Supervisor', 'Admin']:
                    raise PermissionError(f"Unauthorized: Role '{user['role']}' cannot authorize document or identity mismatches. Supervisor or Admin authorization required.")
                if not override_reason or not str(override_reason).strip():
                    raise ValueError("An explicit override reason is mandatory when authorizing a document or identity mismatch.")

                now_iso = datetime.now().isoformat()
                act_desc = f"Mismatch override authorized by {user['full_name']} ({user['role']}). Target: {req_info['name']}. Reason: {str(override_reason).strip()}. Details: {error_details}"
                conn.execute("INSERT INTO activity (trip_id, customer_id, description, timestamp) VALUES (?, ?, ?, ?)",
                             (req_info['trip_id'], req_info['customer_id'], act_desc, now_iso))

        existing = conn.execute("SELECT id FROM documents WHERE requirement_id = ?", (requirement_id,)).fetchone()
        if existing:
            doc_id = existing['id']
            conn.execute("UPDATE documents SET status = ?, file_path = ?, extracted_data = ?, uploaded_at = ? WHERE id = ?",
                         ('Under Review', file_path, json.dumps(extracted_data), datetime.now().isoformat(), doc_id))
        else:
            doc_id = 'DOC-' + str(uuid.uuid4())[:8]
            conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (doc_id, requirement_id, 'Under Review', json.dumps(extracted_data), file_path, datetime.now().isoformat()))
        
        if req_info['name'] == 'Passport' and req_info['customer_id']:
            conn.execute("INSERT OR REPLACE INTO user_profile (customer_id, full_name, dob, nationality, passport_number, passport_expiry) VALUES (?, ?, ?, ?, ?, ?)",
                         (req_info['customer_id'], extracted_data.get('Full Name'), extracted_data.get('Date of Birth'), extracted_data.get('Nationality'), extracted_data.get('Passport Number'), extracted_data.get('Expiry Date')))
        
        conn.commit()
        return doc_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

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
        elif req_name == 'Land Voucher':
            mandatory = ['Booking Reference']
        elif req_name == 'Aadhaar Card':
            mandatory = ['Full Name', 'Aadhaar Number']
        elif req_name == 'PAN Card':
            mandatory = ['Full Name', 'PAN Number']
        elif req_name == 'Arrival / Entry Document':
            mandatory = ['Traveller Name', 'Destination', 'Arrival Date', 'Reference Number']
        elif req_name == 'Itinerary':
            mandatory = ['Start Date', 'End Date', 'Schedule Summary']
            
        for m in mandatory:
            val = data.get(m)
            if not val or not str(val).strip():
                raise ValueError(f"Cannot verify: Missing mandatory field '{m}'.")
                
        conn.execute("UPDATE documents SET status = 'Verified' WHERE id = ?", (doc_id,))
        
        # Passport profile synchronization to matching travellers row
        final_passport = None
        final_nat = None
        final_dob = None
        if req and req['name'] == 'Passport' and req['traveller_id']:
            traveller = conn.execute("SELECT * FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
            if not traveller:
                raise ValueError(f"Associated traveller '{req['traveller_id']}' not found.")

            doc_passport = str(data.get('Passport Number')).strip() if data.get('Passport Number') else None
            doc_nationality = str(data.get('Nationality')).strip() if data.get('Nationality') else None
            doc_dob_raw = str(data.get('Date of Birth')).strip() if data.get('Date of Birth') else None

            # Validate and normalize Date of Birth
            normalized_dob = None
            parsed_dob = None
            if doc_dob_raw:
                parsed_dob = parse_flexible_date(doc_dob_raw)
                if not parsed_dob:
                    raise ValueError(f"Cannot verify: Invalid Date of Birth format '{doc_dob_raw}' in Passport document.")
                normalized_dob = parsed_dob.strftime("%d %b %Y")

            # Conflict checks: Never silently overwrite a different nonempty existing value
            traveller_keys = traveller.keys()
            curr_pass = str(traveller['passport_number']).strip() if ('passport_number' in traveller_keys and traveller['passport_number']) else None
            if curr_pass and doc_passport and curr_pass.upper() != doc_passport.upper():
                raise ValueError(
                    f"Synchronization conflict for traveller '{traveller['name']}': "
                    f"existing profile passport '{curr_pass}' does not match verified document passport '{doc_passport}'."
                )

            curr_nat = str(traveller['nationality']).strip() if ('nationality' in traveller_keys and traveller['nationality']) else None
            if curr_nat and doc_nationality and curr_nat.lower() != doc_nationality.lower():
                raise ValueError(
                    f"Synchronization conflict for traveller '{traveller['name']}': "
                    f"existing profile nationality '{curr_nat}' does not match verified document nationality '{doc_nationality}'."
                )

            curr_dob_raw = str(traveller['dob']).strip() if ('dob' in traveller_keys and traveller['dob']) else None
            curr_dob_parsed = None
            if curr_dob_raw and doc_dob_raw:
                curr_dob_parsed = parse_flexible_date(curr_dob_raw)
                if curr_dob_parsed and parsed_dob:
                    if curr_dob_parsed != parsed_dob:
                        raise ValueError(
                            f"Synchronization conflict for traveller '{traveller['name']}': "
                            f"existing profile date of birth '{curr_dob_raw}' does not match verified document date of birth '{doc_dob_raw}'."
                        )
                elif curr_dob_raw.lower() != doc_dob_raw.lower():
                    raise ValueError(
                        f"Synchronization conflict for traveller '{traveller['name']}': "
                        f"existing profile date of birth '{curr_dob_raw}' does not match verified document date of birth '{doc_dob_raw}'."
                    )

            final_passport = doc_passport if not curr_pass else curr_pass
            final_nat = doc_nationality if not curr_nat else curr_nat
            final_dob = normalized_dob if not curr_dob_raw else (normalized_dob if (curr_dob_parsed and parsed_dob and curr_dob_parsed == parsed_dob) else curr_dob_raw)

            col_info = [c[1] for c in conn.execute("PRAGMA table_info(travellers)").fetchall()]
            set_clauses = []
            params = []
            if 'passport_number' in col_info:
                set_clauses.append("passport_number = ?")
                params.append(final_passport)
            if 'nationality' in col_info:
                set_clauses.append("nationality = ?")
                params.append(final_nat)
            if 'dob' in col_info:
                set_clauses.append("dob = ?")
                params.append(final_dob)

            if set_clauses:
                params.append(req['traveller_id'])
                conn.execute(f"UPDATE travellers SET {', '.join(set_clauses)} WHERE id = ?", tuple(params))

        # Add to document_history
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason)
            VALUES (?, 'VERIFY', ?, 'Verified', ?, 'Verification completed')
        ''', (doc_id, doc['status'], actor))

        from datetime import datetime
        now_iso = datetime.now().isoformat()
        if req:
            act_desc = f"Document {doc_id} verified by {actor}"
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))

            if req['name'] == 'Passport' and req['traveller_id'] and final_passport:
                sync_desc = (
                    f"Traveller {req['traveller_id']} profile synchronized from verified Passport: "
                    f"Passport Number: {final_passport}, Nationality: {final_nat}, DOB: {final_dob} by {actor}"
                )
                if req['trip_id']:
                    conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], sync_desc, now_iso))
                elif req['traveller_id']:
                    t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                    if t_cust and t_cust['customer_id']:
                        conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], sync_desc, now_iso))
        
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
        
        from datetime import datetime
        now_iso = datetime.now().isoformat()
        if req:
            act_desc = f"Document {doc_id} reopened by {actor}. Reason: {reason.strip()}"
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))
        
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def reject_document(doc_id, reason, session_token):
    if not reason or not str(reason).strip():
        raise ValueError("Rejection reason is required.")
        
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']
        
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("Document not found.")
        if doc['status'] == 'Verified':
            raise ValueError("Security Error: Cannot reject a VERIFIED document directly. It must be reopened first.")
            
        req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        
        # Invalidate trip readiness if it was TRAVEL FILE READY
        if req and req['trip_id']:
            trip = conn.execute("SELECT status FROM trips WHERE id = ?", (req['trip_id'],)).fetchone()
            if trip and trip['status'] == 'TRAVEL FILE READY':
                conn.execute("UPDATE trips SET status = 'NOT READY' WHERE id = ?", (req['trip_id'],))
                
        conn.execute("UPDATE documents SET status = 'Rejected' WHERE id = ?", (doc_id,))
        
        from datetime import datetime
        now_iso = datetime.now().isoformat()
        
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp)
            VALUES (?, 'REJECT', ?, 'Rejected', ?, ?, ?)
        ''', (doc_id, doc['status'], actor, reason.strip(), now_iso))
        
        if req:
            act_desc = f"Document {doc_id} rejected by {actor}. Reason: {reason.strip()}"
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))
                    
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def request_reupload_document(doc_id, reason, session_token):
    if not reason or not str(reason).strip():
        raise ValueError("Reason for requesting re-upload is required.")
        
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    actor = user['full_name']
        
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("Document not found.")
        if doc['status'] == 'Verified':
            raise ValueError("Security Error: Cannot request re-upload for a VERIFIED document directly. It must be reopened first.")
            
        req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        
        # Invalidate trip readiness if it was TRAVEL FILE READY
        if req and req['trip_id']:
            trip = conn.execute("SELECT status FROM trips WHERE id = ?", (req['trip_id'],)).fetchone()
            if trip and trip['status'] == 'TRAVEL FILE READY':
                conn.execute("UPDATE trips SET status = 'NOT READY' WHERE id = ?", (req['trip_id'],))
                
        conn.execute("UPDATE documents SET status = 'Re-upload Required' WHERE id = ?", (doc_id,))
        
        from datetime import datetime
        now_iso = datetime.now().isoformat()
        
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp)
            VALUES (?, 'REUPLOAD_REQUEST', ?, 'Re-upload Required', ?, ?, ?)
        ''', (doc_id, doc['status'], actor, reason.strip(), now_iso))
        
        if req:
            act_desc = f"Document {doc_id} re-upload requested by {actor}. Reason: {reason.strip()}"
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))
                    
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def save_extracted_information(doc_id, extracted_data, session_token, reason=None):
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    actor = user['full_name']
    
    if extracted_data is None or not isinstance(extracted_data, dict):
        raise ValueError("extracted_data must be a valid dictionary.")
        
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("Document not found.")
        if doc['status'] == 'Verified':
            raise ValueError("Security Error: Cannot modify extracted data of a VERIFIED document.")
            
        conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(extracted_data), doc_id))
        
        from datetime import datetime
        now_iso = datetime.now().isoformat()
        hist_reason = reason.strip() if (reason and str(reason).strip()) else "Extracted information updated by staff"
        
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp)
            VALUES (?, 'EDIT_DATA', ?, ?, ?, ?, ?)
        ''', (doc_id, doc['status'], doc['status'], actor, hist_reason, now_iso))
        
        req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        if req:
            act_desc = f"Document {doc_id} extracted information updated by {actor}"
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))
                    
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def add_document_note(doc_id, note_text, session_token):
    if not note_text or not str(note_text).strip():
        raise ValueError("Note text cannot be empty.")
        
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    actor = user['full_name']
    
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT requirement_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("Document not found.")
        req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        
        from datetime import datetime
        now_iso = datetime.now().isoformat()
        note_desc = f"Note added by {actor}: {str(note_text).strip()}"
        if req:
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], note_desc, now_iso))
            elif req['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
                if t_cust and t_cust['customer_id']:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], note_desc, now_iso))
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def get_safe_document_path(raw_file_path):
    """
    Safely resolves raw_file_path, restricting access strictly to the approved
    'documents' directory and rejecting path traversal, absolute directory escapes,
    and symlink attacks.
    """
    if not raw_file_path or not isinstance(raw_file_path, str):
        return None, "Document path is not specified."
    
    import os
    if hasattr(database, 'DB_PATH') and database.DB_PATH:
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(database.DB_PATH)))
    elif hasattr(database, '__file__') and database.__file__:
        app_root = os.path.dirname(os.path.abspath(database.__file__))
    else:
        app_root = os.path.abspath(os.getcwd())
        
    approved_docs_dir = os.path.realpath(os.path.join(app_root, "documents"))
    candidate = raw_file_path if os.path.isabs(raw_file_path) else os.path.join(app_root, raw_file_path)
    real_path = os.path.realpath(candidate)
    
    try:
        common = os.path.commonpath([approved_docs_dir, real_path])
        if os.path.realpath(common) != approved_docs_dir:
            return None, "Security Error: Document file path is outside the approved document storage directory."
    except (ValueError, Exception):
        return None, "Security Error: Invalid file path or drive boundary."
        
    if not os.path.exists(real_path) or not os.path.isfile(real_path):
        return None, "Document file does not exist on disk."
        
    return real_path, None

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

def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None, session_token=None, allow_duplicate=False):
    import auth_services
    import document_processor
    import re
    if not session_token: raise PermissionError('Unauthenticated')
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    conn = database.get_connection()
    try:
        # Duplicate detection within the same customer
        if not allow_duplicate and full_name:
            norm_name = document_processor.normalize_person_name(full_name)
            clean_pass = re.sub(r'[^A-Za-z0-9]', '', passport_number or '').upper()
            existing = conn.execute(
                "SELECT id, name, passport_number, dob FROM travellers WHERE customer_id = ?",
                (customer_id,)
            ).fetchall()
            for et in existing:
                et_norm = document_processor.normalize_person_name(et['name']) if et['name'] else ''
                et_pass = re.sub(r'[^A-Za-z0-9]', '', et['passport_number'] or '').upper()
                # If passport numbers match and names match:
                if clean_pass and et_pass and clean_pass == et_pass:
                    return et['id']
                # If names match and DOB matches:
                if norm_name and et_norm and norm_name == et_norm:
                    if dob and et['dob'] and str(dob).strip().lower() == str(et['dob']).strip().lower():
                        return et['id']

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

def recover_verified_document_data(
    doc_id: str,
    recovered_data: dict,
    reason: str,
    session_token: str,
    expected_pdf_sha256: str = None,
    expected_data_hash: str = None,
    reverify: bool = True,
    db_path: str = None
):
    """
    Safely recovers missing or legacy extracted information for a Verified document.
    Performs atomic validation, audit archival, and re-verification in a single transaction.
    """
    import os
    import sqlite3
    import hashlib
    import uuid
    from datetime import datetime

    # 1. Authorization check: strictly Supervisor and Admin
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']

    # 2. Input validation
    if not reason or not str(reason).strip():
        raise ValueError("Mandatory recovery reason is required.")

    if recovered_data is None or not isinstance(recovered_data, dict):
        raise ValueError("recovered_data must be a valid dictionary.")

    if not reverify:
        raise ValueError("Explicit Supervisor/Admin re-verification is required to complete recovery.")

    # 3. Connect to database
    if db_path:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
    else:
        conn = database.get_connection()

    try:
        # Check if document_recovery_audit schema is deployed
        has_audit = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_recovery_audit'"
        ).fetchone()
        if not has_audit:
            raise RuntimeError(
                "Migration Required: The 'document_recovery_audit' table is not deployed in this database. "
                "Phase 8.3 schema migration must be approved and executed before recovery can proceed."
            )

        # 4. Check document
        doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError(f"Document '{doc_id}' not found.")
        if doc['status'] != 'Verified':
            raise ValueError(f"Document '{doc_id}' is not in 'Verified' status (current status: '{doc['status']}'). Only Verified documents can be recovered.")

        # 5. Check source PDF exists and hash
        raw_file_path = doc['file_path'] if doc['file_path'] else ""
        safe_full_path, path_err = get_safe_document_path(raw_file_path)
        if path_err or not os.path.exists(safe_full_path):
            raise ValueError(f"Source document file '{raw_file_path}' cannot be accessed or does not exist on disk.")

        import storage_service
        pdf_bytes = storage_service.read_decrypted_document(
            safe_full_path,
            session_token=session_token,
            allowed_roles=['Supervisor', 'Admin']
        )
        current_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()

        if expected_pdf_sha256 and current_pdf_sha256.lower() != expected_pdf_sha256.lower():
            raise ValueError("Conflict: Source PDF hash has changed since recovery review began.")

        # 6. Concurrency check on stored data
        stored_raw = doc['extracted_data'] if doc['extracted_data'] else "{}"
        current_data_hash = hashlib.sha256(stored_raw.encode('utf-8')).hexdigest()
        if expected_data_hash and current_data_hash != expected_data_hash:
            raise ValueError("Conflict: Document extracted data has changed since recovery review began.")

        # 7. Check requirement and schema validation
        req = conn.execute("SELECT name, type, trip_id, traveller_id FROM requirements WHERE id = ?", (doc['requirement_id'],)).fetchone()
        if not req:
            raise ValueError("Associated requirement not found.")

        req_name = req['name']
        mandatory = []
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
            val = recovered_data.get(m)
            if not val or not str(val).strip():
                raise ValueError(f"Cannot complete recovery: Missing mandatory field '{m}'.")

        # 8. Atomic transaction
        tx_id = f"REC-TX-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now().isoformat()

        conn.execute("BEGIN IMMEDIATE")

        # 8a. Insert dedicated recovery audit record
        conn.execute('''
            INSERT INTO document_recovery_audit (
                transaction_id, document_id, file_path, pdf_sha256,
                previous_extracted_data, new_extracted_data,
                previous_status, new_status, actor, reason, outcome, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, 'Verified', 'Verified', ?, ?, 'SUCCESS', ?)
        ''', (
            tx_id, doc_id, doc['file_path'], current_pdf_sha256,
            stored_raw, json.dumps(recovered_data),
            actor, reason.strip(), now_iso
        ))

        # 8b. Update document's extracted data (status remains 'Verified')
        conn.execute(
            "UPDATE documents SET extracted_data = ? WHERE id = ?",
            (json.dumps(recovered_data), doc_id)
        )

        # 8c. Add to document_history
        hist_reason = f"Data Recovery confirmed by {actor}. Reason: {reason.strip()} (Tx: {tx_id})"
        conn.execute('''
            INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp)
            VALUES (?, 'DATA_RECOVERY', 'Verified', 'Verified', ?, ?, ?)
        ''', (doc_id, actor, hist_reason, now_iso))

        # 8d. Add to activity
        act_desc = f"Document {doc_id} recovered and re-verified by {actor} (Tx: {tx_id})"
        if req['trip_id']:
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], act_desc, now_iso))
        elif req['traveller_id']:
            t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id = ?", (req['traveller_id'],)).fetchone()
            if t_cust and t_cust['customer_id']:
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], act_desc, now_iso))

        conn.commit()

        return {
            "success": True,
            "transaction_id": tx_id,
            "document_id": doc_id,
            "actor": actor,
            "timestamp": now_iso
        }
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def parse_flexible_date(val):
    if not val or not isinstance(val, (str, datetime, date)):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
        
    val_clean = str(val).strip()
    if not val_clean:
        return None
    import re
    
    # Strip time if present: e.g. "12 Dec 2026 09:30" -> "12 Dec 2026"
    m_time = re.search(r'^(.+?)(?:\s+\d{1,2}:\d{2}(?::\d{2})?)\s*$', val_clean)
    if m_time:
        val_clean = m_time.group(1).strip()
        
    date_formats = [
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y"
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(val_clean, fmt).date()
        except ValueError:
            continue
    return None

def verify_metadata_pdf_date_agreement(file_path, date_obj, date_raw_str, session_token=None):
    if not file_path or not os.path.exists(file_path):
        return True, ""
    try:
        import document_processor
        import storage_service
        if session_token:
            pdf_bytes = storage_service.read_decrypted_document(file_path, session_token=session_token)
        else:
            pdf_bytes = storage_service.read_decrypted_document(file_path, system_context=True)
        pdf_text = document_processor.simple_pdf_extract(pdf_bytes)
        if not pdf_text:
            return True, ""
            
        if date_raw_str and str(date_raw_str).strip().lower() in pdf_text.lower():
            return True, ""
            
        day_str = str(date_obj.day)
        month_abbr = date_obj.strftime("%b")
        month_full = date_obj.strftime("%B")
        year_str = str(date_obj.year)
        
        patterns = [
            f"{day_str} {month_abbr}",
            f"{day_str} {month_full}",
            f"{month_abbr} {day_str}",
            f"{year_str}-{date_obj.month:02d}-{date_obj.day:02d}",
            f"{date_obj.day:02d}/{date_obj.month:02d}/{year_str}"
        ]
        for p in patterns:
            if p.lower() in pdf_text.lower():
                return True, ""
                
        return False, f"Extracted date '{date_raw_str}' does not appear in source PDF text (potential metadata/PDF disagreement)."
    except Exception:
        return True, ""

def validate_trip_date_consistency(trip_id, proposed_start_date, proposed_end_date, conn=None, session_token=None):
    from datetime import datetime, timedelta
    
    T_start = parse_flexible_date(proposed_start_date)
    T_end = parse_flexible_date(proposed_end_date)
    
    if not T_start or not T_end:
        return {
            'compatible': False,
            'status': 'invalid_proposed_dates',
            'conflicts': ["Proposed trip dates must be valid calendar dates."],
            'warnings': [],
            'document_evaluations': []
        }
        
    if T_end < T_start:
        return {
            'compatible': False,
            'status': 'invalid_date_range',
            'conflicts': ["Proposed return date cannot be earlier than departure date."],
            'warnings': [],
            'document_evaluations': []
        }
        
    should_close = False
    if conn is None:
        conn = database.get_connection()
        should_close = True
        
    try:
        docs = conn.execute('''
            SELECT r.id AS req_id, r.name AS req_name, r.type AS req_type,
                   d.id AS doc_id, d.status AS doc_status, d.extracted_data, d.file_path,
                   t.name AS traveller_name
            FROM requirements r
            JOIN documents d ON r.id = d.requirement_id
            LEFT JOIN travellers t ON r.traveller_id = t.id
            WHERE r.trip_id = ? AND d.status = 'Verified'
        ''', (trip_id,)).fetchall()
        
        conflicts = []
        warnings = []
        doc_evals = []
        
        for d in docs:
            doc_id = d['doc_id']
            doc_type = d['req_name']
            traveller_name = d['traveller_name']
            doc_label = f"{traveller_name} - {doc_type}" if traveller_name else doc_type
            file_path = d['file_path']
            
            raw_ext = d['extracted_data']
            ext_data = json.loads(raw_ext) if raw_ext else {}
            
            doc_compatible = True
            evaluated_dates = {}
            
            if doc_type == 'Passport':
                exp_raw = ext_data.get('Expiry Date')
                exp_d = parse_flexible_date(exp_raw)
                evaluated_dates['Expiry Date'] = exp_raw
                if not exp_d:
                    conflicts.append(f"Passport '{doc_label}' is Verified but has missing/unparseable Expiry Date.")
                    doc_compatible = False
                else:
                    agrees, msg = verify_metadata_pdf_date_agreement(file_path, exp_d, exp_raw, session_token=session_token)
                    if not agrees:
                        conflicts.append(f"Passport '{doc_label}': {msg}")
                        doc_compatible = False
                    if exp_d < T_end:
                        conflicts.append(f"Passport '{doc_label}' expires on {exp_d.strftime('%d %b %Y')}, before proposed trip conclusion {T_end.strftime('%d %b %Y')}.")
                        doc_compatible = False
                    elif exp_d < (T_end + timedelta(days=180)):
                        warnings.append(f"Passport '{doc_label}' has less than 6 months validity remaining after trip end ({exp_d.strftime('%d %b %Y')}).")
                        
            elif doc_type == 'Visa / Entry Document':
                exp_raw = ext_data.get('Expiry Date / Valid Until') or ext_data.get('Expiry Date') or ext_data.get('Valid Until')
                exp_d = parse_flexible_date(exp_raw)
                from_raw = ext_data.get('Valid From') or ext_data.get('Issue Date')
                from_d = parse_flexible_date(from_raw)
                evaluated_dates['Expiry / Valid Until'] = exp_raw
                evaluated_dates['Valid From'] = from_raw
                if not exp_d:
                    conflicts.append(f"Visa '{doc_label}' is Verified but has missing/unparseable Expiry/Validity date.")
                    doc_compatible = False
                else:
                    agrees, msg = verify_metadata_pdf_date_agreement(file_path, exp_d, exp_raw, session_token=session_token)
                    if not agrees:
                        conflicts.append(f"Visa '{doc_label}': {msg}")
                        doc_compatible = False
                    if exp_d < T_end:
                        conflicts.append(f"Visa '{doc_label}' expires on {exp_d.strftime('%d %b %Y')}, before proposed trip end date {T_end.strftime('%d %b %Y')}.")
                        doc_compatible = False
                    if from_d and from_d > T_start:
                        conflicts.append(f"Visa '{doc_label}' validity starts on {from_d.strftime('%d %b %Y')}, after proposed trip start date {T_start.strftime('%d %b %Y')}.")
                        doc_compatible = False
                        
            elif doc_type == 'Flight Ticket':
                dep_raw = ext_data.get('Departure Date/Time') or ext_data.get('Departure Date')
                arr_raw = ext_data.get('Arrival Date/Time') or ext_data.get('Arrival Date')
                dep_d = parse_flexible_date(dep_raw)
                arr_d = parse_flexible_date(arr_raw)
                evaluated_dates['Departure'] = dep_raw
                evaluated_dates['Arrival'] = arr_raw
                if not dep_d and not arr_d:
                    conflicts.append(f"Flight Ticket '{doc_label}' is Verified but has missing departure/return flight dates.")
                    doc_compatible = False
                else:
                    if dep_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, dep_d, dep_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Flight Ticket '{doc_label}': {msg}")
                            doc_compatible = False
                        if dep_d < T_start:
                            conflicts.append(f"Flight Ticket '{doc_label}' departs on {dep_d.strftime('%d %b %Y')}, before proposed trip start date {T_start.strftime('%d %b %Y')}.")
                            doc_compatible = False
                        if dep_d > T_end:
                            conflicts.append(f"Flight Ticket '{doc_label}' departs on {dep_d.strftime('%d %b %Y')}, after proposed trip end date {T_end.strftime('%d %b %Y')}.")
                            doc_compatible = False
                    if arr_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, arr_d, arr_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Flight Ticket '{doc_label}': {msg}")
                            doc_compatible = False
                        if arr_d < T_start:
                            conflicts.append(f"Flight Ticket '{doc_label}' returns on {arr_d.strftime('%d %b %Y')}, before proposed trip start date {T_start.strftime('%d %b %Y')}.")
                            doc_compatible = False
                        if arr_d > T_end:
                            conflicts.append(f"Flight Ticket '{doc_label}' returns on {arr_d.strftime('%d %b %Y')}, after proposed trip end date {T_end.strftime('%d %b %Y')}.")
                            doc_compatible = False
                            
            elif doc_type == 'Hotel Voucher':
                cin_raw = ext_data.get('Check-in Date')
                cout_raw = ext_data.get('Check-out Date')
                cin_d = parse_flexible_date(cin_raw)
                cout_d = parse_flexible_date(cout_raw)
                evaluated_dates['Check-in'] = cin_raw
                evaluated_dates['Check-out'] = cout_raw
                if not cin_d or not cout_d:
                    conflicts.append(f"Hotel Voucher '{doc_label}' is Verified but has missing Check-in or Check-out dates.")
                    doc_compatible = False
                else:
                    agrees1, msg1 = verify_metadata_pdf_date_agreement(file_path, cin_d, cin_raw, session_token=session_token)
                    agrees2, msg2 = verify_metadata_pdf_date_agreement(file_path, cout_d, cout_raw, session_token=session_token)
                    if not agrees1:
                        conflicts.append(f"Hotel Voucher '{doc_label}': {msg1}")
                        doc_compatible = False
                    if not agrees2:
                        conflicts.append(f"Hotel Voucher '{doc_label}': {msg2}")
                        doc_compatible = False
                    if cin_d < T_start:
                        conflicts.append(f"Hotel Voucher '{doc_label}' check-in ({cin_d.strftime('%d %b %Y')}) is before proposed trip start date {T_start.strftime('%d %b %Y')}.")
                        doc_compatible = False
                    if cout_d > T_end:
                        conflicts.append(f"Hotel Voucher '{doc_label}' check-out ({cout_d.strftime('%d %b %Y')}) is after proposed trip end date {T_end.strftime('%d %b %Y')}.")
                        doc_compatible = False
                        
            elif doc_type == 'Travel Insurance':
                vfrom_raw = ext_data.get('Valid From')
                vuntil_raw = ext_data.get('Valid Until')
                vfrom_d = parse_flexible_date(vfrom_raw)
                vuntil_d = parse_flexible_date(vuntil_raw)
                evaluated_dates['Valid From'] = vfrom_raw
                evaluated_dates['Valid Until'] = vuntil_raw
                if not vfrom_d or not vuntil_d:
                    conflicts.append(f"Travel Insurance '{doc_label}' is Verified but has missing coverage dates.")
                    doc_compatible = False
                else:
                    agrees1, msg1 = verify_metadata_pdf_date_agreement(file_path, vfrom_d, vfrom_raw, session_token=session_token)
                    agrees2, msg2 = verify_metadata_pdf_date_agreement(file_path, vuntil_d, vuntil_raw, session_token=session_token)
                    if not agrees1:
                        conflicts.append(f"Travel Insurance '{doc_label}': {msg1}")
                        doc_compatible = False
                    if not agrees2:
                        conflicts.append(f"Travel Insurance '{doc_label}': {msg2}")
                        doc_compatible = False
                    if vfrom_d > T_start:
                        conflicts.append(f"Travel Insurance '{doc_label}' coverage begins on {vfrom_d.strftime('%d %b %Y')}, leaving traveller uninsured at trip start {T_start.strftime('%d %b %Y')}.")
                        doc_compatible = False
                    if vuntil_d < T_end:
                        conflicts.append(f"Travel Insurance '{doc_label}' coverage expires on {vuntil_d.strftime('%d %b %Y')}, leaving traveller uninsured before trip conclusion {T_end.strftime('%d %b %Y')}.")
                        doc_compatible = False
                        
            elif doc_type == 'Transfer Voucher':
                trf_raw = ext_data.get('Transfer Date')
                trf_d = parse_flexible_date(trf_raw)
                evaluated_dates['Transfer Date'] = trf_raw
                if not trf_d:
                    conflicts.append(f"Transfer Voucher '{doc_label}' is Verified but has missing Transfer Date.")
                    doc_compatible = False
                else:
                    agrees, msg = verify_metadata_pdf_date_agreement(file_path, trf_d, trf_raw, session_token=session_token)
                    if not agrees:
                        conflicts.append(f"Transfer Voucher '{doc_label}': {msg}")
                        doc_compatible = False
                    if trf_d < T_start or trf_d > T_end:
                        conflicts.append(f"Transfer Voucher '{doc_label}' transfer date ({trf_d.strftime('%d %b %Y')}) is outside proposed trip dates ({T_start.strftime('%d %b %Y')} to {T_end.strftime('%d %b %Y')}).")
                        doc_compatible = False
                        
            elif doc_type == 'Sightseeing Voucher':
                act_raw = ext_data.get('Activity Date')
                act_d = parse_flexible_date(act_raw)
                evaluated_dates['Activity Date'] = act_raw
                if not act_d:
                    conflicts.append(f"Sightseeing Voucher '{doc_label}' is Verified but has missing Activity Date.")
                    doc_compatible = False
                else:
                    agrees, msg = verify_metadata_pdf_date_agreement(file_path, act_d, act_raw, session_token=session_token)
                    if not agrees:
                        conflicts.append(f"Sightseeing Voucher '{doc_label}': {msg}")
                        doc_compatible = False
                    if act_d < T_start or act_d > T_end:
                        conflicts.append(f"Sightseeing Voucher '{doc_label}' activity date ({act_d.strftime('%d %b %Y')}) is outside proposed trip dates ({T_start.strftime('%d %b %Y')} to {T_end.strftime('%d %b %Y')}).")
                        doc_compatible = False
                        
            elif doc_type == 'Arrival / Entry Document':
                arr_raw = ext_data.get('Arrival Date')
                dep_raw = ext_data.get('Departure Date')
                arr_d = parse_flexible_date(arr_raw)
                dep_d = parse_flexible_date(dep_raw)
                evaluated_dates['Arrival Date'] = arr_raw
                evaluated_dates['Departure Date'] = dep_raw
                if not arr_d and not dep_d:
                    conflicts.append(f"Arrival Document '{doc_label}' is Verified but has missing arrival/departure dates.")
                    doc_compatible = False
                else:
                    if arr_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, arr_d, arr_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Arrival Document '{doc_label}': {msg}")
                            doc_compatible = False
                        if arr_d < T_start or arr_d > T_end:
                            conflicts.append(f"Arrival Document '{doc_label}' arrival date ({arr_d.strftime('%d %b %Y')}) is outside proposed trip dates.")
                            doc_compatible = False
                    if dep_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, dep_d, dep_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Arrival Document '{doc_label}': {msg}")
                            doc_compatible = False
                        if dep_d < T_start or dep_d > T_end:
                            conflicts.append(f"Arrival Document '{doc_label}' departure date ({dep_d.strftime('%d %b %Y')}) is outside proposed trip dates.")
                            doc_compatible = False
                            
            elif doc_type == 'Itinerary':
                istart_raw = ext_data.get('Start Date')
                iend_raw = ext_data.get('End Date')
                istart_d = parse_flexible_date(istart_raw)
                iend_d = parse_flexible_date(iend_raw)
                evaluated_dates['Start Date'] = istart_raw
                evaluated_dates['End Date'] = iend_raw
                if istart_d or iend_d:
                    if istart_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, istart_d, istart_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Itinerary '{doc_label}': {msg}")
                            doc_compatible = False
                        if istart_d < T_start or istart_d > T_end:
                            conflicts.append(f"Itinerary '{doc_label}' start date ({istart_d.strftime('%d %b %Y')}) is outside proposed trip dates.")
                            doc_compatible = False
                    if iend_d:
                        agrees, msg = verify_metadata_pdf_date_agreement(file_path, iend_d, iend_raw, session_token=session_token)
                        if not agrees:
                            conflicts.append(f"Itinerary '{doc_label}': {msg}")
                            doc_compatible = False
                        if iend_d < T_start or iend_d > T_end:
                            conflicts.append(f"Itinerary '{doc_label}' end date ({iend_d.strftime('%d %b %Y')}) is outside proposed trip dates.")
                            doc_compatible = False
                            
            doc_evals.append({
                'doc_id': doc_id,
                'doc_name': doc_label,
                'doc_type': doc_type,
                'status': 'Verified',
                'evaluated_dates': evaluated_dates,
                'is_compatible': doc_compatible,
                'details': "Compatible" if doc_compatible else "Conflict detected"
            })
            
        is_compatible = (len(conflicts) == 0)
        return {
            'compatible': is_compatible,
            'status': 'compatible' if is_compatible else 'conflict',
            'conflicts': conflicts,
            'warnings': warnings,
            'document_evaluations': doc_evals
        }
    finally:
        if should_close:
            conn.close()

def update_trip_dates(trip_id, new_start_date, new_end_date, session_token, reason, expected_current_start_date=None, expected_current_end_date=None):
    import auth_services
    from datetime import datetime
    
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")
        
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    
    if not reason or not isinstance(reason, str) or len(reason.strip()) < 5:
        raise ValueError("A meaningful, non-empty correction reason is mandatory (minimum 5 characters).")
    clean_reason = reason.strip()
    
    start_d = parse_flexible_date(new_start_date)
    end_d = parse_flexible_date(new_end_date)
    if not start_d or not end_d:
        raise ValueError("Invalid date format. Dates must be valid calendar dates (YYYY-MM-DD).")
    if end_d < start_d:
        raise ValueError("Invalid date range: Return date cannot be earlier than departure date.")
        
    new_start_iso = start_d.strftime("%Y-%m-%d")
    new_end_iso = end_d.strftime("%Y-%m-%d")
    
    conn = database.get_connection()
    try:
        trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip:
            raise ValueError(f"Trip not found: '{trip_id}'.")
            
        if trip['status'] == 'TRAVEL FILE READY':
            raise ValueError(f"Cannot modify finalized travel file: Trip '{trip_id}' has already been approved (TRAVEL FILE READY). Reopen trip first if permitted.")
            
        if expected_current_start_date is not None and trip['start_date'] != expected_current_start_date:
            raise ValueError(f"Concurrent edit conflict: Stored departure date ('{trip['start_date']}') does not match expected ('{expected_current_start_date}'). Please refresh.")
        if expected_current_end_date is not None and trip['end_date'] != expected_current_end_date:
            raise ValueError(f"Concurrent edit conflict: Stored return date ('{trip['end_date']}') does not match expected ('{expected_current_end_date}'). Please refresh.")
            
        # Consistency Check against Verified Documents
        consistency = validate_trip_date_consistency(trip_id, new_start_iso, new_end_iso, conn=conn, session_token=session_token)
        if not consistency['compatible']:
            conflict_summary = " | ".join(consistency['conflicts'])
            raise ValueError(f"Date correction blocked by document consistency safeguard: {conflict_summary}")
            
        old_start = trip['start_date']
        old_end = trip['end_date']
        
        # Atomic update and audit logging
        conn.execute("UPDATE trips SET start_date = ?, end_date = ? WHERE id = ?", (new_start_iso, new_end_iso, trip_id))
        
        now_iso = datetime.now().isoformat()
        audit_desc = (
            f"Trip dates updated from {old_start} - {old_end} to {new_start_iso} - {new_end_iso} "
            f"by {user['full_name']} ({user['role']}). Reason: {clean_reason}"
        )
        conn.execute(
            "INSERT INTO activity (trip_id, customer_id, description, timestamp) VALUES (?, ?, ?, ?)",
            (trip_id, trip['customer_id'], audit_desc, now_iso)
        )
        conn.commit()
        
        return {
            "success": True,
            "trip_id": trip_id,
            "old_dates": (old_start, old_end),
            "new_dates": (new_start_iso, new_end_iso),
            "actor": user['full_name'],
            "role": user['role'],
            "audit_description": audit_desc,
            "timestamp": now_iso
        }
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def approve_travel_file(trip_id, session_token):
    import auth_services
    from datetime import datetime
    
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")
        
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    actor = user['full_name']
    
    conn = database.get_connection()
    try:
        trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip:
            raise ValueError(f"Trip not found: '{trip_id}'.")
            
        if trip['status'] == 'TRAVEL FILE READY':
            return {"success": True, "already_approved": True}
            
        # Verify readiness
        total, complete, attention, missing, pct, business_status = calculate_readiness(trip_id)
        if complete != total or missing > 0 or attention > 0:
            raise ValueError(f"Cannot approve travel file: Not all requirements are verified ({complete}/{total} complete).")
            
        # Enforce date consistency before final approval!
        consistency = validate_trip_date_consistency(trip_id, trip['start_date'], trip['end_date'], conn=conn, session_token=session_token)
        if not consistency['compatible']:
            conflict_summary = " | ".join(consistency['conflicts'])
            raise ValueError(f"Approval blocked: Material trip-date conflicts detected between stored trip dates and verified documents: {conflict_summary}")
            
        now_iso = datetime.now().isoformat()
        conn.execute("UPDATE trips SET status = 'TRAVEL FILE READY' WHERE id = ?", (trip_id,))
        conn.execute(
            "INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)",
            (trip_id, f"Travel File Approved by {actor}", now_iso)
        )
        conn.commit()
        return {"success": True, "trip_id": trip_id, "status": "TRAVEL FILE READY", "actor": actor}
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def generate_trip_travel_pack(trip_id, session_token, out_path=None):
    """
    Secure service boundary for generating a consolidated travel document pack / travel file.
    Enforces authentication, Supervisor/Admin role, and TRAVEL FILE READY status.
    Logs successful generation to the activity table.
    """
    import auth_services
    import travel_file_generator
    from datetime import datetime
    import re
    
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required to generate travel files.")
        
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    actor = user['full_name']
    
    if not trip_id or not isinstance(trip_id, str) or not re.match(r'^[A-Za-z0-9_-]+$', trip_id):
        raise ValueError("Invalid trip_id format.")
        
    if out_path is not None:
        if '..' in out_path.replace('\\', '/').split('/') or '..' in out_path:
            raise PermissionError(f"Security violation: Path traversal detected in output path '{out_path}'.")
        
    conn = database.get_connection()
    try:
        trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not trip:
            raise ValueError(f"Trip not found: '{trip_id}'.")
            
        if trip['status'] != 'TRAVEL FILE READY':
            raise ValueError(f"Cannot generate travel file: Trip '{trip_id}' is not approved (status is '{trip['status']}').")
            
        generated_path = travel_file_generator.generate_consolidated_travel_file(
            trip_id=trip_id,
            out_path=out_path,
            session_token=session_token
        )
        
        now_iso = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO activity (trip_id, customer_id, description, timestamp) VALUES (?, ?, ?, ?)",
            (trip_id, trip['customer_id'], f"Consolidated Travel File generated by {actor} ({user['role']})", now_iso)
        )
        conn.commit()
        return generated_path
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def search_customers(query, session_token):
    """
    Search customers by name or ID.
    Requires authenticated session (Staff, Supervisor, Admin).
    """
    import auth_services
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    
    conn = database.get_connection()
    try:
        if not query or not str(query).strip():
            rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
        else:
            clean_q = f"%{str(query).strip()}%"
            rows = conn.execute("SELECT * FROM customers WHERE name LIKE ? OR id LIKE ? ORDER BY id DESC", (clean_q, clean_q)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_customer_documents(customer_id, session_token):
    """
    Retrieves all documents associated with customer_id across trips and travellers.
    Enforces authentication and role verification.
    """
    import auth_services
    import re
    import os
    
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")
    auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    
    if not customer_id or not isinstance(customer_id, str) or not re.match(r'^[A-Za-z0-9_-]+$', customer_id):
        raise ValueError("Invalid customer_id format.")
        
    conn = database.get_connection()
    try:
        cust = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not cust:
            raise ValueError(f"Customer not found: '{customer_id}'.")
            
        q = '''
            SELECT d.id as doc_id, d.requirement_id, d.status, d.file_path, d.uploaded_at, d.extracted_data,
                   r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id,
                   t.name as traveller_name,
                   tr.name as trip_name,
                   tr.destination as trip_destination,
                   COALESCE(tr.customer_id, t.customer_id) as resolved_customer_id
            FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            LEFT JOIN travellers t ON r.traveller_id = t.id
            LEFT JOIN trips tr ON r.trip_id = tr.id
            WHERE COALESCE(tr.customer_id, t.customer_id) = ?
            ORDER BY d.uploaded_at DESC, d.id DESC
        '''
        rows = conn.execute(q, (customer_id,)).fetchall()
        
        results = []
        for r in rows:
            d_dict = dict(r)
            safe_path, path_err = get_safe_document_path(d_dict['file_path'])
            file_size = 0
            file_exists = False
            file_ext = ""
            if safe_path and not path_err and os.path.exists(safe_path):
                file_exists = True
                file_size = os.path.getsize(safe_path)
                file_ext = os.path.splitext(safe_path)[1].lower()
            
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            elif file_size > 0:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = "0 KB"
                
            fmt_label = file_ext[1:].upper() if file_ext else "UNKNOWN"
            d_dict['file_exists'] = file_exists
            d_dict['file_size_bytes'] = file_size
            d_dict['file_size_str'] = size_str
            d_dict['file_format'] = fmt_label
            d_dict['customer_name'] = cust['name']
            results.append(d_dict)
            
        return results
    finally:
        conn.close()

def get_document_for_download_or_preview(doc_id, customer_id, session_token, action='download'):
    """
    Retrieves original document bytes for preview or download after validating:
    - Session authentication & role
    - Cross-customer ownership
    - Path traversal & safe storage containment
    - File existence & size safety
    Logs audit event to activity table.
    """
    import auth_services
    import re
    import os
    from datetime import datetime
    
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
    
    if not doc_id or not isinstance(doc_id, str) or not re.match(r'^[A-Za-z0-9_-]+$', doc_id):
        raise ValueError("Invalid doc_id format.")
    if not customer_id or not isinstance(customer_id, str) or not re.match(r'^[A-Za-z0-9_-]+$', customer_id):
        raise ValueError("Invalid customer_id format.")
        
    conn = database.get_connection()
    try:
        q = '''
            SELECT d.*, r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id,
                   t.name as traveller_name,
                   tr.name as trip_name,
                   COALESCE(tr.customer_id, t.customer_id) as doc_customer_id,
                   c.name as customer_name
            FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            LEFT JOIN travellers t ON r.traveller_id = t.id
            LEFT JOIN trips tr ON r.trip_id = tr.id
            LEFT JOIN customers c ON COALESCE(tr.customer_id, t.customer_id) = c.id
            WHERE d.id = ?
        '''
        doc_row = conn.execute(q, (doc_id,)).fetchone()
        if not doc_row:
            raise ValueError(f"Document not found: '{doc_id}'.")
            
        # Cross-customer validation
        if doc_row['doc_customer_id'] != customer_id:
            raise PermissionError(
                f"Security violation: Document '{doc_id}' does not belong to customer '{customer_id}' "
                f"(actual owner is '{doc_row['doc_customer_id']}'). Access rejected."
            )
            
        safe_path, path_err = get_safe_document_path(doc_row['file_path'])
        if path_err or not safe_path:
            raise FileNotFoundError(f"Document file unavailable: {path_err}")
            
        if not os.path.isfile(safe_path):
            raise FileNotFoundError(f"Document path '{safe_path}' is not a regular file.")
            
        file_size = os.path.getsize(safe_path)
        if file_size > 50 * 1024 * 1024:
            raise ValueError("Document exceeds maximum allowed size (50MB).")
            
        import storage_service
        file_bytes = storage_service.read_decrypted_document(
            safe_path,
            session_token=session_token,
            doc_id=doc_id,
            customer_id=customer_id
        )
            
        ext = os.path.splitext(safe_path)[1].lower()
        if ext == '.pdf':
            mime_type = 'application/pdf'
        elif ext in ('.jpg', '.jpeg'):
            mime_type = 'image/jpeg'
        elif ext == '.png':
            mime_type = 'image/png'
        else:
            mime_type = 'application/octet-stream'
            
        # Generate safe download filename
        subject = doc_row['traveller_name'] or doc_row['customer_name'] or "Customer"
        raw_name = f"{subject}_{doc_row['req_name']}{ext}"
        safe_filename = re.sub(r'[^A-Za-z0-9._-]', '_', raw_name)
        safe_filename = re.sub(r'_+', '_', safe_filename)
        
        # Audit logging (safe action logging without sensitive credentials or content)
        now_iso = datetime.now().isoformat()
        action_verb = "Downloaded" if str(action).lower() == "download" else "Previewed"
        audit_desc = (
            f"Document '{doc_row['req_name']}' ({action_verb}) for customer '{customer_id}' "
            f"accessed by {user['full_name']} ({user['role']})"
        )
        conn.execute(
            "INSERT INTO activity (customer_id, trip_id, description, timestamp) VALUES (?, ?, ?, ?)",
            (customer_id, doc_row['trip_id'], audit_desc, now_iso)
        )
        conn.commit()
        
        return {
            'doc_id': doc_row['id'],
            'req_name': doc_row['req_name'],
            'file_path': safe_path,
            'file_bytes': file_bytes,
            'file_size': file_size,
            'file_name': safe_filename,
            'mime_type': mime_type,
            'status': doc_row['status'],
            'customer_id': customer_id,
            'traveller_name': doc_row['traveller_name'],
            'trip_name': doc_row['trip_name']
        }
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()


def advanced_vault_search(
    session_token,
    query=None,
    document_type=None,
    verification_status=None,
    destination=None,
    trip_start=None,
    trip_end=None,
    limit=50,
    offset=0,
    conn=None
):
    """
    Advanced Customer, Traveller, Trip & Document Search (Phase 11C).

    Validates authentication and RBAC ('Staff', 'Supervisor', 'Admin').
    Supports parameterized multi-criteria searching across:
      - Customer (Name, ID)
      - Traveller (Name, ID, exact/conservative normalized passport number)
      - Trip (ID, Name, Destination, Overlapping Date Range)
      - Document (Type/Requirement Name, Verification Status)
      - Passport Number: Searches traveller.passport_number and Verified Passport document extracted_data.
        Strictly isolates passport numbers to individual travellers, rejecting cross-traveller leaks
        and ambiguous customer-level fallbacks.

    Returns structured results:
      {
          'documents': [...],
          'results': [...],       # alias to documents
          'customers': [...],
          'travellers': [...],
          'trips': [...],
          'total_documents': int,
          'limit': int,
          'offset': int
      }
    Zero raw OCR text or extracted_data JSON is exposed in results.
    Filesystem paths are not exposed.
    """
    import auth_services
    import json
    import re
    import os
    from datetime import datetime

    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required.")

    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])

    # Validate and normalize pagination parameters
    try:
        limit_int = int(limit)
        if limit_int < 1:
            limit_int = 50
        elif limit_int > 100:
            limit_int = 100
    except (ValueError, TypeError):
        limit_int = 50

    try:
        offset_int = int(offset)
        if offset_int < 0:
            offset_int = 0
    except (ValueError, TypeError):
        offset_int = 0

    # Validate ISO date strings
    def _validate_iso_date(d_val):
        if d_val is None or str(d_val).strip() == "":
            return None
        d_str = str(d_val).strip()
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', d_str):
            raise ValueError(f"Invalid date format: '{d_str}'. Expected YYYY-MM-DD.")
        try:
            datetime.strptime(d_str, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Invalid calendar date: '{d_str}'.")
        return d_str

    clean_trip_start = _validate_iso_date(trip_start)
    clean_trip_end = _validate_iso_date(trip_end)
    if clean_trip_start and clean_trip_end:
        if clean_trip_start > clean_trip_end:
            raise ValueError("Invalid date range: trip_start must be on or before trip_end.")

    close_conn = False
    if conn is None:
        conn = database.get_connection()
        close_conn = True

    try:
        clean_query = str(query).strip() if query is not None else ""
        matched_passport_traveller_ids = set()

        if clean_query:
            norm_q = clean_query.upper()
            # 1. Exact passport search in travellers table
            trav_rows = conn.execute(
                "SELECT id, passport_number FROM travellers WHERE passport_number IS NOT NULL AND TRIM(passport_number) != ''"
            ).fetchall()
            for tr_row in trav_rows:
                p_num = str(tr_row['passport_number']).strip().upper()
                if p_num == norm_q:
                    matched_passport_traveller_ids.add(tr_row['id'])

            # 2. Exact passport search in Verified Passport document extracted_data
            # for travellers whose passport_number is empty/NULL
            doc_pass_rows = conn.execute('''
                SELECT r.traveller_id, d.extracted_data
                FROM documents d
                JOIN requirements r ON d.requirement_id = r.id
                JOIN travellers t ON r.traveller_id = t.id
                WHERE r.name = 'Passport'
                  AND d.status = 'Verified'
                  AND (t.passport_number IS NULL OR TRIM(t.passport_number) = '')
                  AND d.extracted_data IS NOT NULL
            ''').fetchall()

            for dp_row in doc_pass_rows:
                if dp_row['extracted_data']:
                    try:
                        ext_data = json.loads(dp_row['extracted_data'])
                        if isinstance(ext_data, dict):
                            raw_p = ext_data.get('Passport Number') or ext_data.get('passport_number') or ext_data.get('PassportNo')
                            if raw_p and str(raw_p).strip().upper() == norm_q:
                                matched_passport_traveller_ids.add(dp_row['traveller_id'])
                    except Exception:
                        # Malformed extracted_data safely handled without breaking search
                        pass

        # Build WHERE clauses for documents
        where_clauses = ["1=1"]
        params = []

        if clean_query:
            text_like = f"%{clean_query}%"
            if matched_passport_traveller_ids:
                ph = ",".join(["?"] * len(matched_passport_traveller_ids))
                where_clauses.append(
                    f"(r.traveller_id IN ({ph}) OR c.name LIKE ? OR c.id LIKE ? OR t.name LIKE ? OR t.id LIKE ? OR tr.name LIKE ? OR tr.id LIKE ? OR tr.destination LIKE ? OR r.name LIKE ?)"
                )
                params.extend(list(matched_passport_traveller_ids))
                params.extend([text_like] * 8)
            else:
                where_clauses.append(
                    "(c.name LIKE ? OR c.id LIKE ? OR t.name LIKE ? OR t.id LIKE ? OR tr.name LIKE ? OR tr.id LIKE ? OR tr.destination LIKE ? OR r.name LIKE ?)"
                )
                params.extend([text_like] * 8)

        if document_type and str(document_type).strip() and str(document_type).strip().lower() != "all":
            clean_type = str(document_type).strip()
            where_clauses.append("(LOWER(r.name) = LOWER(?) OR LOWER(r.name) LIKE LOWER(?))")
            params.extend([clean_type, f"%{clean_type}%"])

        if verification_status and str(verification_status).strip() and str(verification_status).strip().lower() != "all":
            clean_status = str(verification_status).strip()
            where_clauses.append("d.status = ?")
            params.append(clean_status)

        if destination and str(destination).strip():
            clean_dest = f"%{str(destination).strip()}%"
            where_clauses.append("tr.destination LIKE ?")
            params.append(clean_dest)

        if clean_trip_start and clean_trip_end:
            where_clauses.append("tr.start_date IS NOT NULL AND tr.end_date IS NOT NULL AND tr.start_date <= ? AND tr.end_date >= ?")
            params.extend([clean_trip_end, clean_trip_start])
        elif clean_trip_start:
            where_clauses.append("tr.end_date IS NOT NULL AND tr.end_date >= ?")
            params.append(clean_trip_start)
        elif clean_trip_end:
            where_clauses.append("tr.start_date IS NOT NULL AND tr.start_date <= ?")
            params.append(clean_trip_end)

        # Count total matching documents
        count_sql = f'''
            SELECT COUNT(DISTINCT d.id) as cnt
            FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            LEFT JOIN trips tr ON r.trip_id = tr.id
            LEFT JOIN travellers t ON r.traveller_id = t.id
            LEFT JOIN customers c ON COALESCE(tr.customer_id, t.customer_id) = c.id
            WHERE {' AND '.join(where_clauses)}
        '''
        total_count = conn.execute(count_sql, params).fetchone()['cnt']

        # Query paginated matching documents with deterministic ordering
        doc_query_sql = f'''
            SELECT DISTINCT
                d.id as doc_id,
                d.status as doc_status,
                d.file_path,
                d.uploaded_at,
                r.id as req_id,
                r.name as req_name,
                r.type as req_type,
                r.trip_id,
                r.traveller_id,
                tr.name as trip_name,
                tr.destination as trip_destination,
                tr.start_date as trip_start_date,
                tr.end_date as trip_end_date,
                t.name as traveller_name,
                t.passport_number as traveller_passport,
                COALESCE(tr.customer_id, t.customer_id) as resolved_customer_id,
                c.name as customer_name
            FROM documents d
            JOIN requirements r ON d.requirement_id = r.id
            LEFT JOIN trips tr ON r.trip_id = tr.id
            LEFT JOIN travellers t ON r.traveller_id = t.id
            LEFT JOIN customers c ON COALESCE(tr.customer_id, t.customer_id) = c.id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY d.uploaded_at DESC, d.id DESC
            LIMIT ? OFFSET ?
        '''
        exec_params = list(params) + [limit_int, offset_int]
        doc_rows = conn.execute(doc_query_sql, exec_params).fetchall()

        # Format document items (mask sensitive identifiers, zero OCR/raw extracted data exposure)
        formatted_docs = []
        for row in doc_rows:
            d = dict(row)
            safe_path, path_err = get_safe_document_path(d.get('file_path'))
            file_size = 0
            file_exists = False
            file_ext = ""
            if safe_path and not path_err and os.path.exists(safe_path):
                file_exists = True
                file_size = os.path.getsize(safe_path)
                file_ext = os.path.splitext(safe_path)[1].lower()

            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            elif file_size > 0:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = "0 KB"

            fmt_label = file_ext[1:].upper() if file_ext else "UNKNOWN"

            masked_passport = None
            raw_p = d.get('traveller_passport')
            if raw_p and str(raw_p).strip():
                clean_p = str(raw_p).strip()
                masked_passport = f"****{clean_p[-4:]}" if len(clean_p) >= 4 else "****"

            doc_item = {
                'doc_id': d['doc_id'],
                'requirement_id': d['req_id'],
                'req_name': d['req_name'],
                'req_type': d['req_type'],
                'status': d['doc_status'],
                'customer_id': d['resolved_customer_id'],
                'customer_name': d['customer_name'] or "Unknown Customer",
                'traveller_id': d['traveller_id'],
                'traveller_name': d['traveller_name'],
                'trip_id': d['trip_id'],
                'trip_name': d['trip_name'] or "Traveller Vault (Reusable)",
                'trip_destination': d['trip_destination'],
                'trip_start_date': d['trip_start_date'],
                'trip_end_date': d['trip_end_date'],
                'uploaded_at': d['uploaded_at'],
                'file_format': fmt_label,
                'file_size_bytes': file_size,
                'file_size_str': size_str,
                'file_exists': file_exists,
                'masked_passport': masked_passport
            }
            formatted_docs.append(doc_item)

        # Match Customers for context
        matched_customers = []
        cust_clauses = []
        cust_params = []
        if clean_query:
            cust_clauses.append("name LIKE ? OR id LIKE ?")
            cust_params.extend([text_like, text_like])
            if matched_passport_traveller_ids:
                ph = ",".join(["?"] * len(matched_passport_traveller_ids))
                cust_clauses.append(f"id IN (SELECT customer_id FROM travellers WHERE id IN ({ph}))")
                cust_params.extend(list(matched_passport_traveller_ids))
        if cust_clauses:
            c_rows = conn.execute(
                f"SELECT DISTINCT * FROM customers WHERE ({' OR '.join(cust_clauses)}) ORDER BY id DESC LIMIT 20",
                cust_params
            ).fetchall()
            for cr in c_rows:
                cd = dict(cr)
                matched_customers.append({
                    'id': cd['id'],
                    'name': cd['name'],
                    'customer_type': cd.get('customer_type', 'Individual'),
                    'status': cd.get('status', 'Active'),
                    'mobile': cd.get('mobile'),
                    'email': cd.get('email')
                })

        # Match Travellers for context
        matched_travellers = []
        trav_clauses = []
        trav_params = []
        if clean_query:
            trav_clauses.append("t.name LIKE ? OR t.id LIKE ?")
            trav_params.extend([text_like, text_like])
            if matched_passport_traveller_ids:
                ph = ",".join(["?"] * len(matched_passport_traveller_ids))
                trav_clauses.append(f"t.id IN ({ph})")
                trav_params.extend(list(matched_passport_traveller_ids))
        if trav_clauses:
            t_rows = conn.execute(f'''
                SELECT DISTINCT t.*, c.name as customer_name
                FROM travellers t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE ({' OR '.join(trav_clauses)})
                ORDER BY t.id DESC LIMIT 20
            ''', trav_params).fetchall()
            for tr in t_rows:
                td = dict(tr)
                raw_p = td.get('passport_number')
                mp = f"****{str(raw_p).strip()[-4:]}" if (raw_p and len(str(raw_p).strip()) >= 4) else ("****" if raw_p else None)
                matched_travellers.append({
                    'id': td['id'],
                    'customer_id': td['customer_id'],
                    'customer_name': td.get('customer_name') or "Unknown Customer",
                    'name': td['name'],
                    'type': td.get('type', 'Adult'),
                    'role': td.get('role', 'Standard'),
                    'masked_passport': mp
                })

        # Match Trips for context
        matched_trips = []
        trip_clauses = []
        trip_params = []
        if clean_query:
            trip_clauses.append("(tr.name LIKE ? OR tr.id LIKE ? OR tr.destination LIKE ?)")
            trip_params.extend([text_like, text_like, text_like])
        if destination and str(destination).strip():
            trip_clauses.append("tr.destination LIKE ?")
            trip_params.append(f"%{str(destination).strip()}%")
        if clean_trip_start and clean_trip_end:
            trip_clauses.append("tr.start_date IS NOT NULL AND tr.end_date IS NOT NULL AND tr.start_date <= ? AND tr.end_date >= ?")
            trip_params.extend([clean_trip_end, clean_trip_start])
        elif clean_trip_start:
            trip_clauses.append("tr.end_date IS NOT NULL AND tr.end_date >= ?")
            trip_params.append(clean_trip_start)
        elif clean_trip_end:
            trip_clauses.append("tr.start_date IS NOT NULL AND tr.start_date <= ?")
            trip_params.append(clean_trip_end)

        if trip_clauses:
            tr_rows = conn.execute(f'''
                SELECT DISTINCT tr.*, c.name as customer_name
                FROM trips tr
                LEFT JOIN customers c ON tr.customer_id = c.id
                WHERE {' AND '.join(trip_clauses)}
                ORDER BY tr.id DESC LIMIT 20
            ''', trip_params).fetchall()
            for tr in tr_rows:
                trd = dict(tr)
                matched_trips.append({
                    'id': trd['id'],
                    'customer_id': trd['customer_id'],
                    'customer_name': trd.get('customer_name') or "Unknown Customer",
                    'name': trd['name'],
                    'destination': trd['destination'],
                    'start_date': trd['start_date'],
                    'end_date': trd['end_date'],
                    'status': trd['status']
                })

        return {
            'documents': formatted_docs,
            'results': formatted_docs,
            'customers': matched_customers,
            'travellers': matched_travellers,
            'trips': matched_trips,
            'total_documents': total_count,
            'limit': limit_int,
            'offset': offset_int
        }
    finally:
        if close_conn:
            conn.close()



# -------------------------------------------------------------
# Smart Intake Idempotency & Persistence Service (Phase 12C)
# -------------------------------------------------------------
_SMART_INTAKE_IDEMPOTENCY_CACHE = {}

def complete_smart_intake(
    customer_id=None,
    customer_data=None,
    traveller_data=None,
    document_fields=None,
    file_path=None,
    session_token=None,
    idempotency_key=None,
    force_new_version=False
):
    """
    Atomically finalizes a Smart Intake operation:
    1. Authenticates staff/supervisor/admin role.
    2. Validates idempotency key to prevent duplicate submissions on rerun or retry.
    3. Physically verifies document file on disk before committing to database.
    4. Creates or reuses customer record in a single atomic transaction.
    5. Detects existing matching traveller for this customer to prevent duplicate profiles.
    6. Attaches or updates the passport document in the Traveller Vault (reusable).
    7. Provides rollback and file compensation if any error occurs.
    """
    import auth_services
    import document_processor
    import os
    import re
    import uuid
    import json
    import hashlib
    import shutil
    import tempfile
    from datetime import datetime

    if not session_token:
        raise PermissionError("Unauthenticated: valid session token required.")
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])

    # 1. Idempotency Check
    if idempotency_key:
        clean_key = str(idempotency_key).strip()
        if clean_key in _SMART_INTAKE_IDEMPOTENCY_CACHE:
            return _SMART_INTAKE_IDEMPOTENCY_CACHE[clean_key]

        conn_check = database.get_connection()
        try:
            act_row = conn_check.execute(
                "SELECT customer_id, description FROM activity WHERE description LIKE ? ORDER BY id DESC LIMIT 1",
                (f"%[idempotency_key:{clean_key}]%",)
            ).fetchone()
            if act_row:
                desc = act_row['description']
                m_cust = re.search(r'customer:([A-Za-z0-9\-]+)', desc)
                m_trav = re.search(r'traveller:([A-Za-z0-9\-]+)', desc)
                m_doc = re.search(r'doc:([A-Za-z0-9\-]+)', desc)
                cached_res = {
                    'customer_id': m_cust.group(1) if m_cust else act_row['customer_id'],
                    'traveller_id': m_trav.group(1) if m_trav else None,
                    'document_id': m_doc.group(1) if m_doc else None,
                    'status': 'already_processed',
                    'reused': True
                }
                _SMART_INTAKE_IDEMPOTENCY_CACHE[clean_key] = cached_res
                return cached_res
        finally:
            conn_check.close()

    # 2. File Physical Validation
    if not file_path or not isinstance(file_path, str):
        raise ValueError("file_path must be a non-empty string.")

    # Determine approved documents root
    if hasattr(database, 'DB_PATH') and database.DB_PATH:
        app_root = os.path.dirname(os.path.dirname(os.path.abspath(database.DB_PATH)))
    elif hasattr(database, '__file__') and database.__file__:
        app_root = os.path.dirname(os.path.abspath(database.__file__))
    else:
        app_root = os.path.abspath(os.getcwd())

    approved_docs_dir = os.path.realpath(os.path.join(app_root, "documents"))
    os.makedirs(approved_docs_dir, exist_ok=True)

    # Reject explicit path traversal sequences
    norm_parts = file_path.replace('\\', '/').split('/')
    if '..' in norm_parts:
        raise ValueError(f"Security Error: Path traversal sequence detected in file_path: '{file_path}'.")

    newly_copied = False
    safe_file_path, path_err = get_safe_document_path(file_path)
    if safe_file_path and not path_err and os.path.exists(safe_file_path):
        pass
    else:
        # File is not inside approved documents; check if it is inside system temp directory
        candidate_abs = os.path.realpath(os.path.abspath(file_path))
        temp_root = os.path.realpath(tempfile.gettempdir())
        is_in_temp = False
        try:
            is_in_temp = (os.path.realpath(os.path.commonpath([temp_root, candidate_abs])) == temp_root)
        except (ValueError, Exception):
            is_in_temp = False

        if is_in_temp and os.path.exists(candidate_abs) and os.path.isfile(candidate_abs):
            ext = os.path.splitext(candidate_abs)[1].lower()
            if not ext:
                ext = ".pdf"
            target_name = f"intake_{uuid.uuid4().hex}{ext}"
            target_path = os.path.join(approved_docs_dir, target_name)
            with open(candidate_abs, "rb") as f_cand:
                cand_data = f_cand.read()
            import storage_service
            storage_service.write_document_file(
                target_path,
                cand_data,
                session_token=session_token,
                base_dir=approved_docs_dir
            )
            safe_file_path = target_path
            newly_copied = True
        else:
            raise ValueError(f"Security Error or File Missing: Document file '{file_path}' does not exist or is outside approved directories.")

    if not os.path.exists(safe_file_path):
        raise ValueError(f"Document file does not exist on disk: '{safe_file_path}'.")

    file_size = os.path.getsize(safe_file_path)
    if file_size == 0:
        raise ValueError(f"Document file is empty (0 bytes): '{safe_file_path}'.")

    rel_doc_path = os.path.relpath(safe_file_path, app_root)

    # 3. Database Operations in a Single Atomic Transaction
    conn = database.get_connection()
    try:
        # A. Customer
        if customer_id:
            cust_row = conn.execute("SELECT id, name FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if not cust_row:
                raise ValueError(f"Customer not found: '{customer_id}'.")
            c_id = customer_id
            c_name = cust_row['name']
        else:
            if not customer_data or not customer_data.get('name', '').strip():
                raise ValueError("Customer Name is required.")
            c_name = customer_data['name'].strip()
            c_id = generate_next_id(conn, 'customers', 'KT-C-')
            c_mob = customer_data.get('mobile')
            c_em = customer_data.get('email')
            c_type = customer_data.get('customer_type') or 'Individual'
            conn.execute('''
                INSERT INTO customers (id, name, mobile, email, customer_type, status)
                VALUES (?, ?, ?, ?, ?, 'Active')
            ''', (c_id, c_name, c_mob, c_em, c_type))
            conn.execute('''
                INSERT INTO activity (customer_id, description, timestamp)
                VALUES (?, ?, datetime('now'))
            ''', (c_id, f"Customer created: {c_name}"))

        # B. Traveller with Duplicate Detection
        trav_data = traveller_data or {}
        t_name = trav_data.get('name') or (document_fields or {}).get('Full Name') or c_name
        t_dob = trav_data.get('dob') or (document_fields or {}).get('Date of Birth')
        t_pass = trav_data.get('passport_number') or (document_fields or {}).get('Passport Number')
        t_nat = trav_data.get('nationality') or (document_fields or {}).get('Nationality')
        t_type = trav_data.get('traveller_type') or 'Adult'
        t_rel = trav_data.get('relationship') or 'Self'
        t_lead = trav_data.get('lead_traveller', True)

        existing_travellers = conn.execute(
            "SELECT id, name, passport_number, dob, nationality FROM travellers WHERE customer_id = ?",
            (c_id,)
        ).fetchall()

        matched_trav_id = None
        norm_target_name = document_processor.normalize_person_name(t_name) if t_name else ""
        clean_target_pass = re.sub(r'[^A-Za-z0-9]', '', t_pass).upper() if t_pass else ""

        for et in existing_travellers:
            et_norm_name = document_processor.normalize_person_name(et['name']) if et['name'] else ""
            et_clean_pass = re.sub(r'[^A-Za-z0-9]', '', et['passport_number'] or '').upper()

            # Passport match
            if clean_target_pass and et_clean_pass and clean_target_pass == et_clean_pass:
                matched_trav_id = et['id']
                break
            # Name + DOB match
            if norm_target_name and et_norm_name and norm_target_name == et_norm_name:
                if t_dob and et['dob'] and str(t_dob).strip().lower() == str(et['dob']).strip().lower():
                    matched_trav_id = et['id']
                    break
                if not clean_target_pass and not et_clean_pass:
                    matched_trav_id = et['id']
                    break

        if matched_trav_id:
            trav_id = matched_trav_id
            trav_reused = True
        else:
            trav_id = generate_next_id(conn, 'travellers', 'KT-TR-')
            conn.execute('''
                INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role, passport_number, nationality)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (trav_id, c_id, t_name, t_dob, t_type, t_rel, 'Lead Traveller' if t_lead else 'Standard', t_pass, t_nat))
            conn.execute('''
                INSERT INTO activity (customer_id, description, timestamp)
                VALUES (?, ?, datetime('now'))
            ''', (c_id, f"Traveller added: {t_name}"))
            trav_reused = False

        # C. Requirement & Document Attachment
        req_row = conn.execute('''
            SELECT id FROM requirements 
            WHERE traveller_id = ? AND name = 'Passport' AND type = 'TRAVELLER_VAULT'
        ''', (trav_id,)).fetchone()

        if req_row:
            req_id = req_row['id']
        else:
            req_id = f"REQ-TRV-{uuid.uuid4().hex[:6]}"
            conn.execute('''
                INSERT INTO requirements (id, trip_id, traveller_id, name, type)
                VALUES (?, NULL, ?, 'Passport', 'TRAVELLER_VAULT')
            ''', (req_id, trav_id))

        existing_doc = conn.execute('''
            SELECT id, status, file_path, extracted_data FROM documents
            WHERE requirement_id = ?
            ORDER BY uploaded_at DESC LIMIT 1
        ''', (req_id,)).fetchone()

        doc_reused = False
        if existing_doc:
            existing_full_path, _ = get_safe_document_path(existing_doc['file_path'])
            same_content = False
            if existing_full_path and os.path.exists(existing_full_path):
                import storage_service
                f1_bytes = storage_service.read_decrypted_document(safe_file_path, session_token=session_token)
                f2_bytes = storage_service.read_decrypted_document(existing_full_path, session_token=session_token)
                same_content = (hashlib.sha256(f1_bytes).digest() == hashlib.sha256(f2_bytes).digest())

            if same_content and not force_new_version:
                doc_id = existing_doc['id']
                doc_reused = True
            else:
                # Legitimate renewal or new document version
                doc_id = existing_doc['id']
                try:
                    conn.execute('''
                        INSERT INTO document_history (document_id, event_type, previous_status, new_status, actor, reason, timestamp)
                        VALUES (?, 'VERSION_REPLACE', ?, 'Under Review', ?, 'Updated document uploaded via Smart Intake', datetime('now'))
                    ''', (doc_id, existing_doc['status'], user['full_name']))
                except Exception:
                    pass
                conn.execute('''
                    UPDATE documents SET status = 'Under Review', file_path = ?, extracted_data = ?, uploaded_at = datetime('now')
                    WHERE id = ?
                ''', (rel_doc_path, json.dumps(document_fields or {}), doc_id))
                conn.execute('''
                    INSERT INTO activity (customer_id, description, timestamp)
                    VALUES (?, ?, datetime('now'))
                ''', (c_id, f"Passport document updated for traveller: {t_name}"))
        else:
            doc_id = f"DOC-{uuid.uuid4().hex[:8]}"
            conn.execute('''
                INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at)
                VALUES (?, ?, 'Under Review', ?, ?, datetime('now'))
            ''', (doc_id, req_id, json.dumps(document_fields or {}), rel_doc_path))
            conn.execute('''
                INSERT INTO activity (customer_id, description, timestamp)
                VALUES (?, ?, datetime('now'))
            ''', (c_id, "Passport uploaded for traveller"))

        # User profile synchronization
        if t_name and c_id:
            conn.execute('''
                INSERT OR REPLACE INTO user_profile (customer_id, full_name, dob, nationality, passport_number, passport_expiry)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (c_id, t_name, t_dob, t_nat, t_pass, (document_fields or {}).get('Expiry Date')))

        # Log completion with idempotency tag
        if idempotency_key:
            act_tag = f"Smart intake completed [idempotency_key:{idempotency_key}] (customer:{c_id}, traveller:{trav_id}, doc:{doc_id})"
            conn.execute('''
                INSERT INTO activity (customer_id, description, timestamp)
                VALUES (?, ?, datetime('now'))
            ''', (c_id, act_tag))

        conn.commit()

        result = {
            'customer_id': c_id,
            'traveller_id': trav_id,
            'document_id': doc_id,
            'status': 'success',
            'traveller_reused': trav_reused,
            'document_reused': doc_reused,
            'reused': (trav_reused and doc_reused)
        }

        if idempotency_key:
            _SMART_INTAKE_IDEMPOTENCY_CACHE[clean_key] = result

        return result

    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        if newly_copied and safe_file_path and os.path.exists(safe_file_path):
            try:
                os.remove(safe_file_path)
            except Exception:
                pass
        raise e
    finally:
        conn.close()


def mask_aadhaar(aadhaar_val):
    if not aadhaar_val:
        return ""
    val_clean = re.sub(r'[^0-9X]', '', str(aadhaar_val))
    if len(val_clean) >= 4:
        return f"XXXX-XXXX-{val_clean[-4:]}"
    return "XXXX-XXXX-XXXX"


def delete_document(doc_id: str, session_token: str):
    """
    Administrator-only document deletion control.
    Ordinary staff, sales, operations, visa, ticketing, and auditors are strictly forbidden from deleting documents.
    """
    if not session_token:
        raise PermissionError("Unauthenticated: A valid session token is required to delete documents.")
    
    auth_services.require_permission(session_token, "document:delete")
    user = auth_services.require_role(session_token, ["Admin", "Administrator"])
    
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT id, requirement_id, file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError(f"Document '{doc_id}' not found.")
            
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        
        auth_services.log_security_event(
            "DOCUMENT_DELETED",
            username=user.get("username"),
            user_id=user.get("id"),
            role=user.get("role"),
            details=f"Deleted document record {doc_id}"
        )
    finally:
        conn.close()
