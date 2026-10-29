import streamlit as st
import time
from ui_helpers import inject_custom_css, render_top_nav
from document_processor import process_document
from services import save_document
import os
import database

inject_custom_css()
render_top_nav()

req_id = st.session_state.get('upload_req_id')

req_id = st.session_state.get('upload_req_id')

conn = database.get_connection()

if not req_id:
    st.info("No requirement pre-selected.")
    st.write("### Select a Requirement")
    trip_id = st.session_state.get('upload_trip_id')
    if trip_id:
        pending_reqs = conn.execute("SELECT r.id, r.name, c.name as c_name, t.name as t_name FROM requirements r JOIN trips t ON r.trip_id=t.id JOIN customers c ON t.customer_id=c.id WHERE r.trip_id=?", (trip_id,)).fetchall()
    else:
        pending_reqs = conn.execute("SELECT r.id, r.name, c.name as c_name, t.name as t_name FROM requirements r JOIN trips t ON r.trip_id=t.id JOIN customers c ON t.customer_id=c.id").fetchall()
    
    if not pending_reqs:
        st.warning("No requirements available.")
        st.stop()
        
    req_options = {r['id']: f"{r['c_name']} - {r['t_name']} - {r['name']}" for r in pending_reqs}
    selected_req = st.selectbox("Choose Requirement to Upload:", options=list(req_options.keys()), format_func=lambda x: req_options[x])
    
    if st.button("Proceed to Upload", type="primary"):
        st.session_state['upload_req_id'] = selected_req
        st.rerun()
    st.stop()

req = conn.execute("SELECT r.*, c.name as c_name, t.name as t_name FROM requirements r JOIN trips t ON r.trip_id=t.id JOIN customers c ON t.customer_id=c.id WHERE r.id=?", (req_id,)).fetchone()
conn.close()

if st.button("← Back to Trip"):
    st.query_params.trip_id = req['trip_id']
    st.session_state['nav_page'] = "trip_workspace"
    st.query_params.page = "trip_workspace"
    st.rerun()

st.title("Smart Upload (Staff)")
st.write(f"Uploading **{req['name']}** for **{req['c_name']}** ({req['t_name']})")

col1, col2 = st.columns([2, 1])

with col2:
    st.markdown('''
    <div class="card" style="background: #f8f9fa;">
        <h4>Workflow</h4>
        <ol style="padding-left:20px;">
            <li>Upload file</li>
            <li>System detects type & extracts data</li>
            <li>Confirm details</li>
            <li>Saved as Under Review</li>
        </ol>
    </div>
    ''', unsafe_allow_html=True)

with col1:
    if 'upload_step' not in st.session_state:
        st.session_state['upload_step'] = 1

    if st.session_state['upload_step'] == 1:
        uploaded_file = st.file_uploader("Drag & drop document here", type=['pdf', 'jpg', 'png'])
        if st.button("Simulate Upload Demo Passport"):
            st.session_state['uploaded_filename'] = "demo_passport.pdf"
            st.session_state['upload_step'] = 2
            st.rerun()
            
        import uuid
        if uploaded_file is not None:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            safe_filename = f"trip_upload_{uuid.uuid4().hex}{ext}"
            safe_path = os.path.join("documents", safe_filename)
            with open(safe_path, "wb") as f_out:
                f_out.write(uploaded_file.getvalue())
                
            st.session_state['uploaded_filename'] = uploaded_file.name
            st.session_state['upload_safe_path'] = safe_path
            st.session_state['upload_step'] = 2
            st.rerun()

    elif st.session_state['upload_step'] == 2:
        st.write("Processing document...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        steps = [
            "Reading document...", "✓ Checking file", "✓ Detecting type",
            "→ Extracting information", "→ Matching traveller/trip", "→ Checking quality"
        ]
        
        for i, step in enumerate(steps):
            status_text.text(step)
            progress_bar.progress((i + 1) * 16)
            time.sleep(0.3)
            
        file_path = st.session_state.get('upload_safe_path')
        try:
            with open(file_path, 'rb') as fp:
                file_bytes = fp.read()
        except:
            file_bytes = b''
        result = process_document(st.session_state['uploaded_filename'], file_bytes)
        st.session_state['extracted_result'] = result
        st.session_state['upload_step'] = 3
        st.rerun()

    elif st.session_state['upload_step'] == 3:
        result = st.session_state['extracted_result']
        doc_type = result.get('document_type', 'Needs Review')
        type_conf = result.get('type_confidence', 'low')
        
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
            'Visa / Entry Document': ['Traveller Name', 'Visa Number / Reference', 'Destination', 'Purpose', 'Travel Dates', 'Issue Date', 'Expiry Date / Valid Until'],
            'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class'],
            'Hotel Voucher': ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address'],
            'Travel Insurance': ['Insured Name', 'Policy Number', 'Insurance Provider', 'Valid From', 'Valid Until', 'Destination / Coverage Area'],
            'Transfer Voucher': ['Passenger Name', 'Booking Reference', 'Pickup Location', 'Dropoff Location', 'Transfer Date', 'Transfer Time'],
            'Sightseeing Voucher': ['Guest Name', 'Booking Reference', 'Tour / Activity Name', 'Activity Date', 'Number of Guests'],
            'Arrival / Entry Document': ['Traveller Name', 'Trip Name', 'Destination', 'Arrival Date', 'Departure Date', 'Reference Number'],
            'Itinerary': ['Trip Destination', 'Start Date', 'End Date', 'Schedule Summary'],
            'Needs Review': ['Document Details']
        }
        
        # Determine suggestion for uncertain classification based on linked requirement
        req_name_hint = req['name'].lower()
        fallback_suggestion = 'Needs Review'
        # Check exact full type containment first
        for stype in SUPPORTED_TYPES:
            if stype == 'Needs Review': continue
            if stype.lower() in req_name_hint:
                fallback_suggestion = stype
                break
        if fallback_suggestion == 'Needs Review':
            # Distinctive keyword fallback
            KEYWORD_MAP = {
                'hotel': 'Hotel Voucher',
                'flight': 'Flight Ticket',
                'passport': 'Passport',
                'visa': 'Visa / Entry Document',
                'insurance': 'Travel Insurance',
                'transfer': 'Transfer Voucher',
                'sightseeing': 'Sightseeing Voucher',
                'arrival': 'Arrival / Entry Document',
                'itinerary': 'Itinerary'
            }
            for kw, target_type in KEYWORD_MAP.items():
                if kw in req_name_hint:
                    fallback_suggestion = target_type
                    break

        if doc_type != 'Needs Review' and type_conf == 'high':
            st.success(f"{doc_type} Detected ✓")
            confirmed_type = st.session_state.get('smart_upload_confirmed_type', doc_type)
        else:
            st.warning("⚠️ Document type could not be confidently identified. Please review and confirm the document type.")
            # Suggest matching requirement type if available, otherwise Needs Review
            suggested_type = doc_type if doc_type in SUPPORTED_TYPES and doc_type != 'Needs Review' else fallback_suggestion
            default_idx = SUPPORTED_TYPES.index(suggested_type) if suggested_type in SUPPORTED_TYPES else SUPPORTED_TYPES.index('Needs Review')
            
            # Retrieve currently confirmed type or initialize with suggestion
            confirmed_type = st.session_state.get('smart_upload_confirmed_type', suggested_type)
            sel_idx = SUPPORTED_TYPES.index(confirmed_type) if confirmed_type in SUPPORTED_TYPES else default_idx
            
            selected_type = st.selectbox(
                "Please confirm or select the correct Document Type:",
                options=SUPPORTED_TYPES,
                index=sel_idx,
                key="confirm_doc_type_select"
            )
            
            # If user changes type, switch fields schema immediately and clear stale widget keys
            if selected_type != confirmed_type:
                st.session_state['smart_upload_confirmed_type'] = selected_type
                confirmed_type = selected_type
                schema_fields = SCHEMAS.get(confirmed_type, ['Document Details'])
                curr_fields = result.get('extracted_fields', {})
                FIELD_ALIASES = {
                    'Passenger Name': ['Traveller Name', 'Guest Name', 'Insured Name', 'Full Name'],
                    'Traveller Name': ['Passenger Name', 'Guest Name', 'Insured Name', 'Full Name'],
                    'Guest Name': ['Traveller Name', 'Passenger Name', 'Insured Name', 'Full Name'],
                    'Insured Name': ['Traveller Name', 'Passenger Name', 'Guest Name', 'Full Name'],
                    'Full Name': ['Traveller Name', 'Passenger Name', 'Guest Name', 'Insured Name'],
                    'Booking Reference': ['PNR/Booking Reference', 'Booking Confirmation Number', 'Reference Number', 'Visa Number / Reference', 'Policy Number'],
                    'PNR/Booking Reference': ['Booking Reference', 'Booking Confirmation Number', 'Reference Number'],
                    'Booking Confirmation Number': ['Booking Reference', 'PNR/Booking Reference', 'Reference Number']
                }
                new_fields = {}
                for sf in schema_fields:
                    val = curr_fields.get(sf, '')
                    if not val and sf in FIELD_ALIASES:
                        for alias in FIELD_ALIASES[sf]:
                            if curr_fields.get(alias):
                                val = curr_fields[alias]
                                break
                    new_fields[sf] = val
                
                # Clear all previous smart_up widget states to avoid stale values
                for k in list(st.session_state.keys()):
                    if str(k).startswith("smart_up_"):
                        del st.session_state[k]
                
                st.session_state['extracted_result']['document_type'] = confirmed_type
                st.session_state['extracted_result']['extracted_fields'] = new_fields
                st.rerun()

        st.write("### Review Extracted Information")
        
        warnings_list = result.get('warnings', [])
        for w in warnings_list:
            st.warning(w)
            
        st.info("Please fill or correct any missing or incorrect fields below before saving. Information requires human confirmation.")
        
        # Ensure schema matches confirmed type
        schema_fields = SCHEMAS.get(confirmed_type, ['Document Details'])
        curr_fields = result.get('extracted_fields', {})
        fields = {sf: curr_fields.get(sf, '') for sf in schema_fields}
        
        updated_fields = {}
        c1, c2 = st.columns(2)
        idx = 0
        for k, v in fields.items():
            widget_key = f"smart_up_{confirmed_type}_{k}"
            if idx % 2 == 0:
                with c1: updated_fields[k] = st.text_input(k, value=v, key=widget_key)
            else:
                with c2: updated_fields[k] = st.text_input(k, value=v, key=widget_key)
            idx += 1
            
        col_c, col_s = st.columns(2)
        if col_c.button("Cancel"):
            st.session_state['upload_step'] = 1
            st.rerun()
            
        if col_s.button("Confirm & Save Document"):
            safe_path = st.session_state.get('upload_safe_path')
            save_document(req_id, safe_path, updated_fields, st.session_state.get('session_token'))
            # Add activity
            conn = database.get_connection()
            conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (req['trip_id'], f"Document {req['name']} uploaded via Smart Upload"))
            conn.commit()
            conn.close()
            
            st.session_state['upload_step'] = 4
            st.rerun()

    elif st.session_state['upload_step'] == 4:
        st.success("Document successfully saved ✓")
        st.info("Workflow status set to Under Review.")
        if st.button("Return to Trip"):
            st.session_state['upload_step'] = 1
            st.query_params.trip_id = req['trip_id']
            st.session_state['nav_page'] = "trip_workspace"
            st.query_params.page = "trip_workspace"
            st.rerun()
