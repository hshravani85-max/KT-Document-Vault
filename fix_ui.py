import re

with open('pages/trip_workspace.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add travellers fetching logic
fetch_old = """trip = get_trip_details(trip_id)
if not trip:
    st.error("Trip not found.")
    st.stop()"""

fetch_new = """trip = get_trip_details(trip_id)
if not trip:
    st.error("Trip not found.")
    st.stop()

conn = database.get_connection()
trip_travellers = conn.execute("SELECT t.* FROM travellers t JOIN trip_travellers tt ON t.id = tt.traveller_id WHERE tt.trip_id = ?", (trip_id,)).fetchall()
conn.close()
trip_travellers = [dict(t) for t in trip_travellers]"""

content = content.replace(fetch_old, fetch_new)

# 2. Fix the Checklist section
chk_old = """    st.markdown("<div style='background:#f1f3f4; padding:10px; border-radius:8px; margin-bottom:15px;'><strong>Amit Mehta</strong></div>", unsafe_allow_html=True)
    
    traveller_reqs = [r for r in reqs if r['type'] == 'TRAVELLER']
    for r in traveller_reqs:
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
                        st.query_params.page = "smart_upload"
                        st.rerun()
                elif status == 'Under Review':
                    if st.button("Review", key=f"rev_{r['id']}"):
                        st.query_params.doc_id = r['doc_id']
                        st.query_params.page = "document_review"
                        st.rerun()
                elif status == 'Verified':
                    if st.button("View", key=f"view_{r['id']}"):
                        st.query_params.doc_id = r['doc_id']
                        st.query_params.page = "document_review"
                        st.rerun()
                else:
                    if st.button("Replace Document", key=f"rep_{r['id']}"):
                        st.session_state['upload_req_id'] = r['id']
                        st.query_params.page = "smart_upload"
                        st.rerun()
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)"""

chk_new = """    for t in trip_travellers:
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
                            st.query_params.page = "smart_upload"
                            st.rerun()
                    elif status == 'Under Review':
                        if st.button("Review", key=f"rev_{r['id']}"):
                            st.query_params.doc_id = r['doc_id']
                            st.query_params.page = "document_review"
                            st.rerun()
                    elif status == 'Verified':
                        if st.button("View", key=f"view_{r['id']}"):
                            st.query_params.doc_id = r['doc_id']
                            st.query_params.page = "document_review"
                            st.rerun()
                    else:
                        if st.button("Replace Document", key=f"rep_{r['id']}"):
                            st.session_state['upload_req_id'] = r['id']
                            st.query_params.page = "smart_upload"
                            st.rerun()
                st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)"""

content = content.replace(chk_old, chk_new)

# 3. Add Tab 2 implementation
tabs2_old = """conn = database.get_connection()
acts = conn.execute("SELECT * FROM activity WHERE trip_id=? ORDER BY timestamp DESC", (trip_id,)).fetchall()
conn.close()

with tabs[4]:"""

tabs2_new = """conn = database.get_connection()
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
            <p style="margin:0; color:#555;">Passport: {t.get('passport_number', 'Not provided')} | DOB: {t.get('dob', 'Not provided')} | Nationality: {t.get('nationality', 'Not provided')}</p>
        </div>
        ''', unsafe_allow_html=True)

with tabs[4]:"""

content = content.replace(tabs2_old, tabs2_new)

with open('pages/trip_workspace.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed pages/trip_workspace.py!")
