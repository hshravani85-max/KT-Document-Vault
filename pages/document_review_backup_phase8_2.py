import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import (
    verify_document, reopen_document, reject_document,
    request_reupload_document, save_extracted_information,
    add_document_note, get_safe_document_path, get_document
)
import auth_services
import os
import json
import database

# 1. Page-level authentication gate
session_token = st.session_state.get('session_token')
current_user = None
try:
    current_user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])
except PermissionError:
    st.error("Authentication required: Invalid, missing, or expired session. Please log in.")
    st.stop()

if not current_user:
    st.stop()

user_role = current_user.get('role', 'Staff')
user_full_name = current_user.get('full_name', 'Staff')

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
           COALESCE(t.customer_id, tr.customer_id) as customer_id,
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
        WHERE description LIKE ? 
          AND (
              (trip_id IS NOT NULL AND trip_id = ?) 
              OR (customer_id IS NOT NULL AND customer_id = ?)
              OR (trip_id IS NULL AND customer_id IS NULL)
          )
        ORDER BY timestamp DESC LIMIT 1
    ''', (f"%Document {d['id']} verified%", d['trip_id'], d['customer_id'])).fetchone()

conn.close()

if not d:
    st.error("Document not found.")
    st.stop()

st.markdown(f"<h2>Review: {d['req_name']} for {d['customer_name']}</h2>", unsafe_allow_html=True)
st.write(f"Trip: {d['trip_name']}")

col1, col2 = st.columns([1, 1])
with col1:
    import base64
    safe_path, err_msg = get_safe_document_path(d['file_path'])
    if err_msg:
        st.warning(f"Preview unavailable: {err_msg}")
    else:
        if safe_path.lower().endswith('.pdf'):
            try:
                with open(safe_path, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" style="border:1px solid #ccc; border-radius:8px;" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception:
                st.info("Preview unavailable for this file.")
        elif safe_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            st.image(safe_path, use_column_width=True)
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
        if status == 'Verified' and veri_act:
            verified_ts = veri_act['timestamp'][:19].replace('T', ' ')
            actor_line = ""
            if 'actor' in veri_act.keys() and veri_act['actor']:
                actor_line = f"<br><small>Actor: {veri_act['actor']}</small>"
            st.markdown(f'''
<div style="background:#f8f9fa; padding:12px; border-radius:6px; border:1px solid #e0e0e0; margin-bottom:10px;">
    <strong>Legacy Verification Record</strong><br>
    <small>Verified on: {verified_ts}</small>{actor_line}<br>
    <small>Source: Historical Activity Log</small><br>
    <small style="color:#666;"><em>This verification predates the current document history system.</em></small>
</div>
''', unsafe_allow_html=True)
        else:
            st.write("<small>No verification history available.</small>", unsafe_allow_html=True)

    if status == 'Verified':
        if user_role in ['Supervisor', 'Admin']:
            if st.session_state.get(f'reopen_mode_{doc_id}'):
                st.warning("You are requesting to reopen a VERIFIED document. This will invalidate its current verification and recalculate trip readiness.")
                reason = st.text_input("Mandatory Correction Reason (Required)", key=f"reopen_reason_input_{doc_id}")
                cr1, cr2 = st.columns(2)
                if cr1.button("Cancel", key=f"cancel_reopen_{doc_id}"):
                    st.session_state[f'reopen_mode_{doc_id}'] = False
                    st.rerun()
                if cr2.button("Confirm Reopen", key=f"confirm_reopen_{doc_id}"):
                    if not reason.strip():
                        st.error("Correction reason is required.")
                    else:
                        try:
                            reopen_document(doc_id, reason, session_token)
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
        req_n = d['req_name'].lower()
        fallback_type = 'Needs Review'
        for stype in ['Passport', 'Visa / Entry Document', 'Flight Ticket', 'Hotel Voucher', 'Travel Insurance', 'Transfer Voucher', 'Sightseeing Voucher', 'Arrival / Entry Document', 'Itinerary']:
            if stype.lower() in req_n:
                fallback_type = stype
                break
        if fallback_type == 'Needs Review':
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
                if kw in req_n:
                    fallback_type = target_type
                    break
        detected_t = st.session_state.get(f'reextract_type_{doc_id}', fallback_type)
        def_idx = SUPPORTED_TYPES.index(detected_t) if detected_t in SUPPORTED_TYPES else 0
        chosen_type = st.selectbox("Confirm Document Type Form:", options=SUPPORTED_TYPES, index=def_idx, key=f"re_type_select_{doc_id}")
        if chosen_type != detected_t:
            st.session_state[f'reextract_type_{doc_id}'] = chosen_type
            target_fields = SCHEMAS.get(chosen_type, ['Document Details'])
            # Clear or safely map fields, discarding stale fields from previous type
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
            new_re_data = {}
            for tf in target_fields:
                val = re_data.get(tf, '')
                if not val and tf in FIELD_ALIASES:
                    for alias in FIELD_ALIASES[tf]:
                        if re_data.get(alias):
                            val = re_data[alias]
                            break
                new_re_data[tf] = val
            
            # Clear stale review widget states
            for k in list(st.session_state.keys()):
                if str(k).startswith(f"re_edit_"):
                    del st.session_state[k]

            st.session_state[f'reextract_data_{doc_id}'] = new_re_data
            st.rerun()
            
        target_fields = SCHEMAS.get(chosen_type, ['Document Details'])
        re_data = {tf: re_data.get(tf, '') for tf in target_fields}
        updated_re_data = {}
        for k, v in re_data.items():
            updated_re_data[k] = st.text_input(k, value=v, key=f"re_edit_{chosen_type}_{k}")
            
        c1, c2 = st.columns(2)
        if c1.button("Cancel", key=f"cancel_reextract_{doc_id}"):
            st.session_state[f'reextract_mode_{doc_id}'] = False
            st.rerun()
        if c2.button("Confirm & Save Information", key=f"confirm_reextract_{doc_id}"):
            try:
                save_extracted_information(doc_id, updated_re_data, session_token)
                st.session_state[f'reextract_mode_{doc_id}'] = False
                st.success("Information saved.")
                st.rerun()
            except PermissionError as pe:
                st.error(str(pe))
            except ValueError as ve:
                st.error(str(ve))
            except Exception as e:
                st.error(f"Error saving information: {str(e)}")

    else:
        data = json.loads(d['extracted_data']) if d['extracted_data'] and d['extracted_data'] != "{}" else {}
        
        if not data:
            if status == 'Verified':
                st.markdown("**Extracted Information Not Available**")
                st.info("This document was saved before the current extraction workflow. Its original file is preserved, but structured extracted information was not stored.")
                
                is_preview_active = st.session_state.get(f'preview_mode_{doc_id}', False)
                if not is_preview_active:
                    if st.button("Preview Extracted Information", key=f"preview_btn_{doc_id}"):
                        st.session_state[f'preview_mode_{doc_id}'] = True
                        st.rerun()
                else:
                    st.markdown('''
<div style="background:#fff8e1; border:1px solid #ffe082; padding:12px; border-radius:6px; margin-bottom:12px;">
    <strong style="color:#b78103; font-size:1.05rem;">Extracted Preview — Not Saved or Verified</strong><br>
    <small style="color:#555;">This is a read-only preview generated from the stored document file. Extracted data has not been saved to the database and this does not modify the document's Verified status, audit history, or trip readiness.</small>
</div>
''', unsafe_allow_html=True)
                    
                    if st.button("Close Preview", key=f"close_preview_btn_{doc_id}"):
                        st.session_state[f'preview_mode_{doc_id}'] = False
                        st.rerun()

                    raw_file_path = d['file_path'] if d['file_path'] else ""
                    full_file_path, path_err = get_safe_document_path(raw_file_path)
                    
                    if path_err:
                        st.error(path_err)
                    else:
                        file_bytes = None
                        try:
                            with open(full_file_path, "rb") as f:
                                file_bytes = f.read()
                        except Exception as e:
                            st.error(f"Error reading file from disk: {str(e)}")
                            
                        if file_bytes is not None:
                            import document_processor
                            extracted_text = ""
                            if full_file_path.lower().endswith('.pdf'):
                                extracted_text = document_processor.simple_pdf_extract(file_bytes)
                                
                            if not extracted_text or len(extracted_text.strip()) <= 30:
                                st.warning("This document requires OCR processing. External cloud OCR is disabled for this preview without explicit authorization.")
                            else:
                                preview_data, preview_conf, detected_type, type_conf = document_processor.parse_passport_text(extracted_text)
                                
                                # Check detected type vs requirement
                                req_n = d['req_name'] if ('req_name' in d.keys() and d['req_name']) else ''
                                expected_type = 'Needs Review'
                                for stype in SUPPORTED_TYPES:
                                    if stype.lower() in req_n.lower():
                                        expected_type = stype
                                        break
                                if expected_type == 'Needs Review':
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
                                        if kw in req_n.lower():
                                            expected_type = target_type
                                            break
                                
                                st.markdown(f"**Detected Document Type:** `{detected_type}` &nbsp; *(Confidence: **{type_conf}**)*")
                                
                                if expected_type != 'Needs Review' and detected_type != 'Needs Review' and detected_type != expected_type:
                                    st.warning(f"Detected Document Type Mismatch: Engine identified this document as '{detected_type}' (Confidence: {type_conf}), which differs from the expected requirement '{req_n}'.")
                                    
                                active_schema_type = detected_type if detected_type in SCHEMAS and detected_type != 'Needs Review' else (expected_type if expected_type in SCHEMAS else 'Needs Review')
                                target_schema = SCHEMAS.get(active_schema_type, ['Document Details'])
                                
                                missing_fields = []
                                ambiguous_fields = []
                                for fld in target_schema:
                                    val = preview_data.get(fld, '')
                                    if not val or not str(val).strip():
                                        missing_fields.append(fld)
                                    elif preview_conf.get(fld) == 'low':
                                        ambiguous_fields.append(fld)
                                        
                                if missing_fields:
                                    st.markdown(f"<div style='margin-bottom:6px;'><small style='color:#c5221f;'><strong>Missing Fields ({len(missing_fields)}):</strong> {', '.join(missing_fields)}</small></div>", unsafe_allow_html=True)
                                if ambiguous_fields:
                                    st.markdown(f"<div style='margin-bottom:6px;'><small style='color:#b06000;'><strong>Ambiguous / Low Confidence Fields ({len(ambiguous_fields)}):</strong> {', '.join(ambiguous_fields)}</small></div>", unsafe_allow_html=True)
                                    
                                for fld in target_schema:
                                    val = preview_data.get(fld, "")
                                    if not val or not str(val).strip():
                                        label = f"{fld} [Missing]"
                                        disp = "[Not Extracted / Missing in Document]"
                                    elif preview_conf.get(fld) == 'low':
                                        label = f"{fld} [Low Confidence / Ambiguous]"
                                        disp = str(val)
                                    else:
                                        label = f"{fld} [Extracted]"
                                        disp = str(val)
                                    st.text_input(label, value=disp, key=f"preview_field_{doc_id}_{fld}", disabled=True)
                                    
                                extra_fields = [k for k, v in preview_data.items() if v and str(v).strip() and k not in target_schema]
                                for fld in extra_fields:
                                    st.text_input(f"{fld} [Additional Field]", value=str(preview_data[fld]), key=f"preview_field_{doc_id}_{fld}", disabled=True)
            else:
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
        if user_role in ['Supervisor', 'Admin']:
            if st.session_state.get(f'reject_mode_{doc_id}'):
                st.warning("You are rejecting this document. Please provide a mandatory reason.")
                reject_reason = st.text_input("Mandatory Rejection Reason (Required)", key=f"reject_reason_{doc_id}")
                rc1, rc2 = st.columns(2)
                if rc1.button("Cancel", key=f"cancel_reject_{doc_id}"):
                    st.session_state[f'reject_mode_{doc_id}'] = False
                    st.rerun()
                if rc2.button("Confirm Rejection", type="primary", key=f"confirm_reject_{doc_id}"):
                    if not reject_reason.strip():
                        st.error("Rejection reason is required.")
                    else:
                        try:
                            reject_document(doc_id, reject_reason, session_token)
                            st.session_state[f'reject_mode_{doc_id}'] = False
                            st.warning("Document Rejected.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            elif st.session_state.get(f'reupload_mode_{doc_id}'):
                st.warning("You are requesting a re-upload for this document. Please provide a mandatory reason.")
                reupload_reason = st.text_input("Mandatory Re-upload Reason (Required)", key=f"reupload_reason_{doc_id}")
                ruc1, ruc2 = st.columns(2)
                if ruc1.button("Cancel", key=f"cancel_reupload_{doc_id}"):
                    st.session_state[f'reupload_mode_{doc_id}'] = False
                    st.rerun()
                if ruc2.button("Confirm Re-upload Request", type="primary", key=f"confirm_reupload_{doc_id}"):
                    if not reupload_reason.strip():
                        st.error("Re-upload reason is required.")
                    else:
                        try:
                            request_reupload_document(doc_id, reupload_reason, session_token)
                            st.session_state[f'reupload_mode_{doc_id}'] = False
                            st.warning("Re-upload Requested.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
            else:
                c1, c2, c3 = st.columns(3)
                if c1.button("Verify Document", type="primary", key=f"verify_btn_{doc_id}"):
                    try:
                        verify_document(d['id'], session_token)
                        st.success("Document Verified!")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
                if c2.button("Reject", key=f"reject_btn_{doc_id}"):
                    st.session_state[f'reject_mode_{doc_id}'] = True
                    st.rerun()
                if c3.button("Request Re-upload", key=f"reupload_btn_{doc_id}"):
                    st.session_state[f'reupload_mode_{doc_id}'] = True
                    st.rerun()
        else:
            st.info("ℹ️ Document verification and status management actions (Verify, Reject, Re-upload) require Supervisor or Admin privileges.")
    
    st.write("### Add Note")
    note = st.text_area("Internal staff note about this document")
    if st.button("Save Note", key=f"save_note_{doc_id}"):
        note_str = str(note).strip()
        if note_str:
            try:
                add_document_note(doc_id, note_str, session_token)
                st.success("Note saved.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
