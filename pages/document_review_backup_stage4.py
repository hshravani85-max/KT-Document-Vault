import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import verify_document, get_document
import database
import json

inject_custom_css()
render_top_nav()

doc_id = st.query_params.get("doc_id")
if not doc_id:
    st.error("No document selected.")
    st.stop()

if st.button("← Back", key="back_btn_doc_review"):
    if 'doc_id' in st.query_params:
        del st.query_params['doc_id']
    st.session_state['nav_page'] = "documents"
    st.query_params.page = "documents"
    st.rerun()

conn = database.get_connection()
d = conn.execute('''
    SELECT d.*, r.name as req_name, r.trip_id, r.traveller_id,
           COALESCE(c.name, c2.name) as customer_name, 
           t.name as trip_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    LEFT JOIN trips t ON r.trip_id = t.id
    LEFT JOIN customers c ON t.customer_id = c.id
    LEFT JOIN travellers tr ON r.traveller_id = tr.id
    LEFT JOIN customers c2 ON tr.customer_id = c2.id
    WHERE d.id = ?
''', (doc_id,)).fetchone()

veri_act = None
if d:
    veri_act = conn.execute('''
        SELECT * FROM activity 
        WHERE trip_id = ? AND description LIKE ? 
        ORDER BY timestamp DESC LIMIT 1
    ''', (d['trip_id'], f"%Document {d['id']} verified%")).fetchone()

conn.close()

if not d:
    st.error("Document not found.")
    st.stop()

st.markdown(f"<h2>Review: {d['req_name']} for {d['customer_name']}</h2>", unsafe_allow_html=True)
st.write(f"Trip: {d['trip_name']}")

col1, col2 = st.columns([1, 1])
with col1:
    import os, base64
    file_path = d['file_path']
    if file_path and os.path.exists(file_path):
        if file_path.lower().endswith('.pdf'):
            try:
                with open(file_path, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" style="border:1px solid #ccc; border-radius:8px;" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception:
                st.info("Preview unavailable for this file.")
        elif file_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            st.image(file_path, use_column_width=True)
        else:
            st.info("Preview unavailable for this file.")
    else:
        st.info("Preview unavailable for this file.")

with col2:
    status = d['status']
    
    if status == 'Verified':
        st.markdown('''
        <div style="background:#e6f4ea; padding:15px; border-radius:8px; border:1px solid #ceead6; margin-bottom: 20px;">
            <h3 style="color:#1e8e3e; margin-top:0;">✓ Verified</h3>
        ''', unsafe_allow_html=True)
        
        if veri_act:
            verified_on = veri_act['timestamp'][:19].replace('T', ' ')
            st.markdown(f'''
            <p style="margin:0; color:#333;"><strong>Verified by:</strong> {veri_act['actor'] if 'actor' in veri_act.keys() else 'Staff'}</p>
            <p style="margin:0; color:#333;"><strong>Verified on:</strong> {verified_on}</p>
            ''', unsafe_allow_html=True)
            
        st.markdown('</div>', unsafe_allow_html=True)

    elif status == 'Rejected':
        st.markdown('''
        <div style="background:#fce8e6; padding:15px; border-radius:8px; border:1px solid #fad2cf; margin-bottom: 20px;">
            <h3 style="color:#d93025; margin-top:0;">Rejected</h3>
        </div>
        ''', unsafe_allow_html=True)
    elif status == 'Re-upload Required':
        st.markdown('''
        <div style="background:#fce8e6; padding:15px; border-radius:8px; border:1px solid #fad2cf; margin-bottom: 20px;">
            <h3 style="color:#d93025; margin-top:0;">Re-upload Required</h3>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown(f"**Status:** {render_badge(status)}", unsafe_allow_html=True)



    st.write("### Verification History")
    conn = database.get_connection()
    hist = conn.execute("SELECT * FROM document_history WHERE document_id = ? ORDER BY timestamp DESC", (d['id'],)).fetchall()
    conn.close()
    if hist:
        for h in hist:
            st.markdown(f"<small>**{h['timestamp'][:19]}** - {h['event_type']} - Actor: {h['actor']} - Reason: {h['reason']}</small>", unsafe_allow_html=True)
    else:
        st.write("<small>No history available.</small>", unsafe_allow_html=True)

    if status == 'Verified':
        if st.session_state.get(f'reopen_mode_{doc_id}'):
            st.warning("You are requesting to reopen a VERIFIED document. This will invalidate its current verification and recalculate trip readiness.")
            reason = st.text_input("Mandatory Correction Reason (Required)")
            cr1, cr2 = st.columns(2)
            if cr1.button("Cancel", key=f"cancel_reopen_{doc_id}"):
                st.session_state[f'reopen_mode_{doc_id}'] = False
                st.rerun()
            if cr2.button("Confirm Reopen", key=f"confirm_reopen_{doc_id}"):
                if not reason.strip():
                    st.error("Correction reason is required.")
                else:
                    try:
                        import services
                        services.reopen_document(doc_id, reason, st.session_state.get('session_token'))
                        st.session_state[f'reopen_mode_{doc_id}'] = False
                        st.success("Document reopened successfully.")
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Error reopening: {str(e)}")
        else:
            if st.button("Reopen for Review", key=f"reopen_btn_{doc_id}"):
                st.session_state[f'reopen_mode_{doc_id}'] = True
                st.rerun()

    st.write("### Extracted Information")
    
    if st.session_state.get(f'reextract_mode_{doc_id}'):
        st.info("Please correct any missing or incorrect fields below before saving. Extracted information requires human confirmation.")
        re_data = st.session_state.get(f'reextract_data_{doc_id}', {})
        detected_t = st.session_state.get(f'reextract_type_{doc_id}', 'Hotel Voucher' if 'Hotel' in d['req_name'] else ('Flight Ticket' if 'Flight' in d['req_name'] else 'Needs Review'))
        
        SUPPORTED_TYPES = [
            'Hotel Voucher',
            'Flight Ticket',
            'Passport',
            'Visa / Entry Document',
            'Travel Insurance',
            'Transfer Voucher',
            'Sightseeing Voucher',
            'Arrival / Entry Document',
            'Itinerary',
            'Needs Review'
        ]
        
        SCHEMAS = {
            'Passport': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
            'Visa / Entry Document': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
            'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class'],
            'Hotel Voucher': ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address'],
            'Travel Insurance': ['Insured Name', 'Policy Number', 'Valid From', 'Valid Until'],
            'Transfer Voucher': ['Passenger Name', 'Pickup Location', 'Dropoff Location', 'Date', 'Time'],
            'Sightseeing Voucher': ['Guest Name', 'Tour Name', 'Date', 'Booking Reference'],
            'Arrival / Entry Document': ['Passenger Name', 'Arrival Date', 'Reference Number'],
            'Itinerary': ['Passenger Name', 'Start Date', 'End Date'],
            'Needs Review': ['Document Details']
        }
        
        def_idx = SUPPORTED_TYPES.index(detected_t) if detected_t in SUPPORTED_TYPES else 0
        chosen_type = st.selectbox("Confirm Document Type Form:", options=SUPPORTED_TYPES, index=def_idx, key=f"re_type_select_{doc_id}")
        if chosen_type != detected_t:
            st.session_state[f'reextract_type_{doc_id}'] = chosen_type
            target_fields = SCHEMAS.get(chosen_type, ['Document Details'])
            re_data = {tf: re_data.get(tf, '') for tf in target_fields}
            st.session_state[f'reextract_data_{doc_id}'] = re_data
            
        updated_re_data = {}
        for k, v in re_data.items():
            updated_re_data[k] = st.text_input(k, value=v, key=f"re_edit_{k}")
            
        c1, c2 = st.columns(2)
        if c1.button("Cancel", key=f"cancel_reextract_{doc_id}"):
            st.session_state[f'reextract_mode_{doc_id}'] = False
            st.rerun()
        if c2.button("Confirm & Save Information", key=f"confirm_reextract_{doc_id}"):
            # Update database
            import json
            conn = database.get_connection()
            
            # Security check: Prevent updating a verified document
            current_status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()['status']
            if current_status == 'Verified':
                st.error("Security Error: Cannot modify extracted data of a VERIFIED document.")
                st.stop()
                
            conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(updated_re_data), doc_id))
            # Activity
            from datetime import datetime
            trip_id_for_act = d['trip_id']
            if not trip_id_for_act and d['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (d['traveller_id'],)).fetchone()
                if t_cust:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], f"Document {doc_id} re-extracted and saved", datetime.now().isoformat()))
            elif trip_id_for_act:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (trip_id_for_act, f"Document {doc_id} re-extracted and saved", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            st.session_state[f'reextract_mode_{doc_id}'] = False
            st.success("Information saved.")
            st.rerun()

    else:
        data = json.loads(d['extracted_data']) if d['extracted_data'] and d['extracted_data'] != "{}" else {}
        
        if not data:
            st.warning("No extracted information is saved for this document. Re-extract information or enter details for review.")
        else:
            for k, v in data.items():
                st.text_input(k, value=v, key=f"edit_{k}", disabled=True)
                
        if status in ['Under Review', 'Rejected', 'Re-upload Required']:
            if st.button("Re-extract Information", key=f"reextract_btn_{doc_id}"):
                import document_processor
                with open(d['file_path'], 'rb') as f:
                    fb = f.read()
                res = document_processor.process_document(d['file_path'], fb)
                st.session_state[f'reextract_data_{doc_id}'] = res['extracted_fields']
                st.session_state[f'reextract_type_{doc_id}'] = res['document_type']
                st.session_state[f'reextract_mode_{doc_id}'] = True
                st.rerun()
        
    if status == 'Under Review':
        st.write("### Actions")
        c1, c2, c3 = st.columns(3)
        if c1.button("Verify Document", type="primary", key=f"verify_btn_{doc_id}"):
            try:
                verify_document(d['id'], st.session_state.get('session_token'))
                # Add activity
                conn = database.get_connection()
            except Exception as e:
                st.error(str(e))
                st.stop()
            conn = database.get_connection()
            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} verified", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} verified", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.success("Document Verified!")
            st.rerun()
        if c2.button("Reject", key=f"reject_btn_{doc_id}"):
            conn = database.get_connection()
            conn.execute("UPDATE documents SET status = 'Rejected' WHERE id = ?", (d['id'],))
            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} rejected", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} rejected", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.warning("Rejected (Demo)")
            st.rerun()
        if c3.button("Request Re-upload", key=f"reupload_btn_{doc_id}"):
            conn = database.get_connection()
            conn.execute("UPDATE documents SET status = 'Re-upload Required' WHERE id = ?", (d['id'],))
            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} re-upload requested", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} re-upload requested", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.warning("Requested Re-upload (Demo)")
            st.rerun()
    
    st.write("### Add Note")
    note = st.text_area("Internal staff note about this document")
    if st.button("Save Note", key=f"save_note_{doc_id}"):
        note_str = str(note).strip()
        if note_str:
            conn = database.get_connection()
            req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Note added: {note_str}", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.success("Note saved.")
            st.rerun()
