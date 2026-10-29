import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_trip_details, get_requirements, calculate_readiness
import database
from datetime import datetime

inject_custom_css()
render_top_nav()

trip_id = st.query_params.get('trip_id', 'KT-T-0001')

if st.button("← Back to Trips", key="back"):
    st.session_state['nav_page'] = "trips"
    st.query_params.page = "trips"
    st.rerun()

trip = get_trip_details(trip_id)
if not trip:
    st.error("Trip not found.")
    st.stop()

conn = database.get_connection()
trip_travellers = conn.execute("SELECT t.* FROM travellers t JOIN trip_travellers tt ON t.id = tt.traveller_id WHERE tt.trip_id = ?", (trip_id,)).fetchall()
conn.close()
trip_travellers = [dict(t) for t in trip_travellers]
    
reqs = get_requirements(trip_id)
_, comp, att, miss, pct, business_status = calculate_readiness(trip_id)

conn = database.get_connection()
c = conn.execute("SELECT name FROM customers WHERE id=?", (trip['customer_id'],)).fetchone()
customer_name = c['name'] if c else "Unknown"
conn.close()

st.markdown(f'''
<div style="display: flex; gap: 20px; margin-bottom: 20px;">
    <div style="flex: 2; background: #f8f9fa; padding: 30px; border-radius: 12px; border: 1px solid #e0e0e0;">
        <h2 style="margin:0; color: #0d1b2a;">{trip['id']} - {trip['name']}</h2>
        <p style="margin: 10px 0 0 0; color: #555;">Customer: {customer_name} | 📍 {trip['destination']} | 📅 {trip['start_date']} - {trip['end_date']}</p>
        <p style="margin: 5px 0 0 0; color: #555;">Service: {trip['service']} | Dept: {trip['department']}</p>
    </div>
    <div style="flex: 1; background: white; border: 1px solid #e0e0e0; padding: 20px; border-radius: 12px; display:flex; flex-direction:column; justify-content:space-between;">
        <div style="display:flex; justify-content:space-between;">
            <div>
                <h4 style="margin:0;">Travel Readiness</h4>
                <p style="margin:5px 0; font-size:0.9rem; color:#1e8e3e;">✅ {comp} Complete</p>
                <p style="margin:5px 0; font-size:0.9rem; color:#f29900;">⚠️ {att} Pending / Attention</p>
                <p style="margin:5px 0; font-size:0.9rem; color:#d93025;">❌ {miss} Action Required</p>
            </div>
            <h1 style="margin:0; color:#1a73e8;">{pct}%</h1>
        </div>
        <div style="margin-top:15px; padding-top:15px; border-top:1px solid #eee;">
            <strong style="font-size:0.9rem; color:#666;">Status:</strong><br>
            <span style="font-size:1.1rem; font-weight:bold; color:{'#1e8e3e' if business_status == 'READY FOR FINAL REVIEW' else '#1a73e8' if business_status == 'TRAVEL FILE READY' else '#d93025'};">{business_status}</span>
        </div>
    </div>
</div>
''', unsafe_allow_html=True)

if business_status == 'READY FOR FINAL REVIEW':
    st.info("All documents are verified. This trip is ready for final approval.")
    if st.button("Approve Travel File", type="primary"):
        st.session_state['confirm_approval'] = True

    if st.session_state.get('confirm_approval'):
        st.warning("Are you sure you want to approve this travel file?")
        c1, c2 = st.columns(2)
        if c1.button("Confirm Approval", type="primary"):
            conn = database.get_connection()
            conn.execute("UPDATE trips SET status = 'TRAVEL FILE READY' WHERE id = ?", (trip_id,))
            import auth_services
            user = auth_services.require_role(st.session_state.get('session_token'), ['Supervisor', 'Admin'])
            staff_identity = user['full_name']
            
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", 
                         (trip_id, f"Travel File Approved by {staff_identity}", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.session_state['confirm_approval'] = False
            st.rerun()
        if c2.button("Cancel"):
            st.session_state['confirm_approval'] = False
            st.rerun()

elif business_status == 'TRAVEL FILE READY':
    st.success("Travel File is Approved and Ready.")
    
    if st.session_state.get('user_role') in ['Supervisor', 'Admin']:
        if st.button("Generate Consolidated PDF", type="primary"):
            import travel_file_generator
            try:
                pdf_path = travel_file_generator.generate_consolidated_travel_file(trip_id)
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(
                        label="Download Travel File",
                        data=pdf_file,
                        file_name=pdf_path.split("/")[-1].split("\\")[-1],
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")



st.markdown("<hr>", unsafe_allow_html=True)
c_pdf1, c_pdf2 = st.columns([3, 1])
with c_pdf2:
    if st.button("Generate Travel PDF", use_container_width=True):
        import travel_file_generator, base64
        try:
            pdf_path = travel_file_generator.generate_consolidated_travel_file(trip_id)
            st.success("Travel PDF generated successfully.")
            with open(pdf_path, "rb") as pdf_file:
                b64_pdf = base64.b64encode(pdf_file.read()).decode('utf-8')
            filename = pdf_path.split("/")[-1].split("\\")[-1]
            href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" target="_blank" style="display:inline-block; width:100%; text-align:center; padding:8px 16px; background:#1e8e3e; color:white; text-decoration:none; border-radius:4px; font-weight:600;">Open Generated PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error generating PDF: {str(e)}")

tabs = st.tabs(["Document Checklist", "Trip Itinerary", "Traveller", "Trip Details", "Notes", "Activity"])


with tabs[0]:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown("### TRAVELLER DOCUMENTS")
    with c2:
        if st.button("Smart Upload", key="trip_smart_upload", use_container_width=True, type="primary"):
            if 'upload_req_id' in st.session_state:
                del st.session_state['upload_req_id']
            st.session_state['upload_trip_id'] = trip_id
            st.session_state['nav_page'] = "smart_upload"
            st.query_params.page = "smart_upload"
            st.rerun()

    for t in trip_travellers:
        st.markdown(f"<div style='background:#f1f3f4; padding:10px; border-radius:8px; margin-bottom:15px;'><strong>{t['name']}</strong></div>", unsafe_allow_html=True)
        
        t_reqs = [r for r in reqs if r['type'] == 'TRAVELLER' and r['traveller_id'] == t['id']]
        if not t_reqs:
            st.write("No traveller documents required.")
        for r in t_reqs:
            status = r.get('doc_status') or 'Missing'
            with st.container():
                c1, c2, c3 = st.columns([1, 4, 2])
                c1.markdown("📄")
                c2.markdown(f"**{r['name']}**<br>{render_badge(status)}", unsafe_allow_html=True)
                with c3:
                    if status == 'Missing':
                        if st.button("Add Document", key=f"add_{r['id']}"):
                            st.session_state['upload_req_id'] = r['id']
                            st.session_state['upload_trip_id'] = trip_id
                            st.session_state['nav_page'] = "smart_upload"
                            st.query_params.page = "smart_upload"
                            st.rerun()
                    elif status == 'Under Review':
                        if st.button("Review", key=f"rev_{r['id']}"):
                            st.query_params.doc_id = r['doc_id']
                            st.session_state['nav_page'] = "document_review"
                            st.query_params.page = "document_review"
                            st.rerun()
                    elif status == 'Verified':
                        if st.button("View", key=f"view_{r['id']}"):
                            st.query_params.doc_id = r['doc_id']
                            st.session_state['nav_page'] = "document_review"
                            st.query_params.page = "document_review"
                            st.rerun()
                    else:
                        if st.button("Replace Document", key=f"rep_{r['id']}"):
                            st.session_state['upload_req_id'] = r['id']
                            st.session_state['nav_page'] = "smart_upload"
                            st.query_params.page = "smart_upload"
                            st.rerun()
                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    st.markdown("### TRIP DOCUMENTS")
    trip_reqs = [r for r in reqs if r['type'] == 'TRIP']
    for r in trip_reqs:
        status = r.get('doc_status') or 'Missing'
        with st.container():
            c1, c2, c3 = st.columns([1, 4, 2])
            c1.markdown("🎫")
            c2.markdown(f"**{r['name']}**<br>{render_badge(status)}", unsafe_allow_html=True)
            with c3:
                if status == 'Missing':
                    if st.button("Add Document", key=f"add_{r['id']}"):
                        st.session_state['upload_req_id'] = r['id']
                        st.session_state['upload_trip_id'] = trip_id
                        st.session_state['nav_page'] = "smart_upload"
                        st.query_params.page = "smart_upload"
                        st.rerun()
                elif status == 'Under Review':
                    if st.button("Review", key=f"rev_{r['id']}"):
                        st.query_params.doc_id = r['doc_id']
                        st.session_state['nav_page'] = "document_review"
                        st.query_params.page = "document_review"
                        st.rerun()
                elif status == 'Verified':
                    if st.button("View", key=f"view_{r['id']}"):
                        st.query_params.doc_id = r['doc_id']
                        st.session_state['nav_page'] = "document_review"
                        st.query_params.page = "document_review"
                        st.rerun()
                else:
                    if st.button("Replace Document", key=f"rep_{r['id']}"):
                        st.session_state['upload_req_id'] = r['id']
                        st.session_state['nav_page'] = "smart_upload"
                        st.query_params.page = "smart_upload"
                        st.rerun()
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

conn = database.get_connection()
acts = conn.execute("SELECT * FROM activity WHERE trip_id=? ORDER BY timestamp DESC", (trip_id,)).fetchall()
conn.close()

with tabs[2]:
    st.write("### Travellers on this Trip")
    if not trip_travellers:
        st.write("No travellers assigned.")
    for t in trip_travellers:
        st.markdown(f'''
        <div class="card" style="margin-bottom:15px;">
            <h4 style="margin:0 0 5px 0;">{t['name']}</h4>
            <p style="margin:0; color:#555;">Passport: {t.get('passport_number') or 'Not provided'} | DOB: {t.get('dob') or 'Not provided'} | Nationality: {t.get('nationality') or 'Not provided'}</p>
        </div>
        ''', unsafe_allow_html=True)

with tabs[4]:
    st.write("### Internal Notes")
    note = st.text_area("Add internal staff note for this trip")
    if st.button("Save Note"):
        note_str = str(note).strip()
        if note_str:
            conn = database.get_connection()
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", 
                         (trip_id, f"Note added: {note_str}", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            st.success("Note saved.")
            st.rerun()
        else:
            st.error("Cannot save an empty note.")
    
    st.write("#### Existing Notes")
    for a in acts:
        st.write(f"- {a['timestamp'][:19]}: {a['description']}")

with tabs[5]:
    st.write("### Activity History")
    for a in acts:
        st.write(f"{a['timestamp'][:19]}: {a['description']}")
