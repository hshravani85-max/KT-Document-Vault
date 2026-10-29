import streamlit as st
import textwrap
from ui_helpers import inject_custom_css, render_top_nav, render_badge
import database
import services

inject_custom_css()
render_top_nav()

customer_id = st.query_params.get("customer_id", "KT-C-0001")

conn = database.get_connection()
c = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
conn.close()

if not c:
    st.error("Customer not found.")
    st.stop()
c = dict(c)

# Back Navigation Link
if st.button("← Back to Customers", key="back_to_cust_btn", icon=":material/arrow_back:"):
    st.session_state['nav_page'] = "customers"
    st.query_params.page = "customers"
    st.rerun()

# Customer Summary Header Card
contact_items = []
if 'mobile' in c.keys() and c['mobile']: contact_items.append(f"📞 {c['mobile']}")
if 'email' in c.keys() and c['email']: contact_items.append(f"✉️ {c['email']}")
contact_str = f"&nbsp;|&nbsp; {' • '.join(contact_items)}" if contact_items else ""

st.markdown(textwrap.dedent(f'''
<div style="background:#FFFFFF; border:1px solid #E5EAF1; border-radius:12px; padding:22px 24px; margin-bottom:20px; box-shadow:0 1px 3px rgba(11,35,72,0.04);">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
        <div>
            <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:1px;">
                CUSTOMER PROFILE &nbsp;•&nbsp; <code>{c['id']}</code>
            </div>
            <h2 style="margin:4px 0 0 0; color:#0B2348; font-weight:800; font-size:1.8rem;">
                {c['name']}
            </h2>
            <div style="margin-top:6px; color:#64748B; font-size:0.9rem;">
                Type: <strong>{c['customer_type']}</strong> {contact_str}
            </div>
        </div>
        <div style="text-align:right;">
            {render_badge(c['status'])}
        </div>
    </div>
</div>
'''), unsafe_allow_html=True)

tabs = st.tabs([
    "Customer Details",
    "Traveller Profiles",
    "Trips",
    "Document Vault",
    "Recent Activity",
    "Internal Notes"
])

# Tab 0: Customer Details
with tabs[0]:
    st.markdown('<div class="kt-section-title">👤 Customer Information</div>', unsafe_allow_html=True)
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Full Name:** {c['name']}")
            st.markdown(f"**Customer ID:** `{c['id']}`")
            st.markdown(f"**Customer Type:** {c['customer_type']}")
        with col2:
            st.markdown(f"**Account Status:** {render_badge(c['status'])}", unsafe_allow_html=True)
            st.markdown(f"**Mobile Number:** {c.get('mobile') or 'Not provided'}")
            st.markdown(f"**Email Address:** {c.get('email') or 'Not provided'}")

# Tab 1: Traveller Profiles
with tabs[1]:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="kt-section-title">👥 Traveller Profiles</div>', unsafe_allow_html=True)
    with c2:
        if st.button("➕ Add Traveller", type="primary", use_container_width=True, icon=":material/person_add:"):
            st.session_state['show_add_traveller'] = not st.session_state.get('show_add_traveller', False)
            
    if st.session_state.get('show_add_traveller', False):
        st.markdown('<div class="kt-card">', unsafe_allow_html=True)
        st.markdown("#### Create New Traveller Profile")
        with st.form("add_trav_form"):
            t_name = st.text_input("Full Name *")
            t_dob = st.text_input("Date of Birth (e.g. 01 Jan 1990)")
            t_type = st.selectbox("Traveller Type", ["Adult", "Child", "Infant"])
            t_rel = st.selectbox("Relationship", ["Self", "Spouse", "Son", "Daughter", "Parent", "Other"])
            t_lead = st.checkbox("Lead Traveller")
            
            sub = st.form_submit_button("Save Traveller", type="primary")
            if sub:
                if not t_name.strip():
                    st.error("Full Name is required.")
                else:
                    services.add_traveller(
                        customer_id=customer_id,
                        full_name=t_name.strip(),
                        dob=t_dob.strip() if t_dob.strip() else None,
                        traveller_type=t_type,
                        relationship=t_rel,
                        lead_traveller=t_lead,
                        session_token=st.session_state.get('session_token')
                    )
                    st.session_state['show_add_traveller'] = False
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    conn = database.get_connection()
    travs = conn.execute("SELECT * FROM travellers WHERE customer_id=?", (customer_id,)).fetchall()
    conn.close()
    
    if not travs:
        st.info("No travellers registered yet. Click 'Add Traveller' to create a profile.")
    else:
        for t in travs:
            t_dict = dict(t)
            role = t_dict.get('role', 'Standard')
            passport = t_dict.get('passport_number') or 'Not provided'
            nat = t_dict.get('nationality') or 'Not provided'
            dob = t_dict.get('dob') or 'Not provided'
            is_lead = bool(t_dict.get('lead_traveller'))
            
            with st.container(border=True):
                col_info, col_pass = st.columns([3, 1.2])
                with col_info:
                    lead_tag = " :blue-background[LEAD TRAVELLER]" if is_lead else ""
                    st.markdown(f"#### 👤 {t_dict['name']}{lead_tag}")
                    st.markdown(
                        f"**Type:** {t_dict.get('type', 'Unknown')} &nbsp;•&nbsp; "
                        f"**Relationship:** {t_dict.get('relationship', 'Self')} &nbsp;•&nbsp; "
                        f"**DOB:** {dob} &nbsp;•&nbsp; "
                        f"**Nationality:** {nat}"
                    )
                with col_pass:
                    st.caption("Passport Number")
                    if passport and passport != 'Not provided':
                        st.code(passport, language=None)
                    else:
                        st.write("Not provided")

# Tab 2: Trips
with tabs[2]:
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="kt-section-title">✈️ Customer Trips</div>', unsafe_allow_html=True)
    with c2:
        if st.button("➕ Create Trip", type="primary", use_container_width=True, icon=":material/flight_takeoff:"):
            st.session_state['show_create_trip'] = not st.session_state.get('show_create_trip', False)

    if st.session_state.get('show_create_trip', False):
        st.markdown('<div class="kt-card">', unsafe_allow_html=True)
        st.markdown("#### Create New Trip")
        if not travs:
            st.error("You must add at least one traveller before creating a trip.")
        else:
            with st.form("create_trip_form"):
                tr_name = st.text_input("Trip Name *")
                tr_dest = st.text_input("Destination *")
                
                cc1, cc2 = st.columns(2)
                with cc1:
                    tr_start = st.date_input("Departure Date *")
                with cc2:
                    tr_end = st.date_input("Return Date *")
                    
                tr_type = st.selectbox("Trip Type", ["Holiday", "Business", "Visa Only", "Group", "Other"])
                tr_srv = st.selectbox("Service Type", ["International Package", "Domestic Package", "Flight Only", "Hotel Only", "Visa Service", "Corporate Travel", "Other"])
                tr_dept = st.selectbox("Department / Owner", ["Operations", "Sales", "Visa", "Ticketing", "Other"])
                
                st.write("**Traveller Selection**")
                trav_options = {t['id']: f"{t['name']} ({t['type']})" for t in travs}
                selected_travs = st.multiselect("Select Travellers", options=list(trav_options.keys()), format_func=lambda x: trav_options[x])
                
                sub_trip = st.form_submit_button("Save Trip", type="primary")
                if sub_trip:
                    if not tr_name.strip() or not tr_dest.strip():
                        st.error("Trip Name and Destination are required.")
                    elif tr_end < tr_start:
                        st.error("Return date must be on or after departure date.")
                    elif not selected_travs:
                        st.error("At least one traveller must be selected.")
                    else:
                        start_str = tr_start.strftime("%Y-%m-%d")
                        end_str = tr_end.strftime("%Y-%m-%d")
                        new_trip_id = services.create_trip(customer_id, tr_name.strip(), tr_dest.strip(), start_str, end_str, tr_type, tr_srv, tr_dept, selected_travs, st.session_state.get('session_token'))
                        st.session_state['show_create_trip'] = False
                        st.query_params.trip_id = new_trip_id
                        st.session_state['nav_page'] = "trip_workspace"
                        st.query_params.page = "trip_workspace"
                        st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    conn = database.get_connection()
    trips = conn.execute("SELECT * FROM trips WHERE customer_id=? ORDER BY id DESC", (customer_id,)).fetchall()
    conn.close()
    
    if not trips:
        st.info("No trips created yet for this customer.")
    else:
        for t in trips:
            tot, comp, att, miss, pct, b_status = services.calculate_readiness(t['id'])
            with st.container(border=True):
                col1, col2 = st.columns([4, 1.5])
                with col1:
                    st.markdown(f"#### ✈️ {t['name']} `({t['id']})`")
                    st.markdown(f"📍 **{t['destination']}** &nbsp;•&nbsp; 📅 {t['start_date']} to {t['end_date']}")
                    st.markdown(f"**Readiness: {pct}%** ({comp} complete, {miss} missing) &nbsp;•&nbsp; {render_badge(b_status)}", unsafe_allow_html=True)
                with col2:
                    st.write("")
                    if st.button("Open Trip Workspace", key=f"ot_{t['id']}", use_container_width=True):
                        st.query_params.trip_id = t['id']
                        st.session_state['nav_page'] = "trip_workspace"
                        st.query_params.page = "trip_workspace"
                        st.rerun()

# Tab 3: Customer Document Vault
with tabs[3]:
    st.markdown('<div class="kt-section-title">📁 Customer Document Vault</div>', unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#64748B; margin-top:-6px; margin-bottom:18px; font-size:0.92rem;'>"
        "Secure customer-wise document archive. Preview and download original travel documents "
        "across all trips and travellers."
        "</p>",
        unsafe_allow_html=True
    )

    session_token = st.session_state.get('session_token')
    try:
        cust_docs = services.get_customer_documents(customer_id, session_token)
    except Exception as e:
        st.error(f"Error loading document vault: {e}")
        cust_docs = []

    if not cust_docs:
        st.info("No documents found in vault for this customer.")
    else:
        # Search & Filter Controls
        f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
        with f_col1:
            vault_search_text = st.text_input("Search Documents", placeholder="e.g. Passport, Ticket, Dubai...", key=f"v_search_{customer_id}").strip().lower()
        with f_col2:
            unique_trips = ["All Trips"]
            for d in cust_docs:
                t_name = d.get('trip_name') or "Traveller Vault (Reusable)"
                if t_name not in unique_trips:
                    unique_trips.append(t_name)
            selected_trip_filter = st.selectbox("Filter by Trip", unique_trips, key=f"v_trip_filter_{customer_id}")
        with f_col3:
            unique_statuses = ["All Statuses"] + sorted(list(set(d['status'] for d in cust_docs)))
            selected_status_filter = st.selectbox("Filter by Status", unique_statuses, key=f"v_status_filter_{customer_id}")

        filtered_docs = []
        for d in cust_docs:
            t_name = d.get('trip_name') or "Traveller Vault (Reusable)"
            if selected_trip_filter != "All Trips" and t_name != selected_trip_filter:
                continue
            if selected_status_filter != "All Statuses" and d['status'] != selected_status_filter:
                continue
            if vault_search_text:
                searchable = f"{d['req_name']} {d.get('traveller_name') or ''} {t_name} {d['status']} {d.get('file_format', '')}".lower()
                if vault_search_text not in searchable:
                    continue
            filtered_docs.append(d)

        if not filtered_docs:
            st.info("No documents match your filter criteria.")
        else:
            st.caption(f"Showing {len(filtered_docs)} of {len(cust_docs)} total customer documents.")
            st.markdown("<hr style='margin:10px 0; border:none; border-top:1px solid #E5EAF1;'>", unsafe_allow_html=True)

            active_preview_doc = st.session_state.get(f'vault_preview_doc_{customer_id}')

            for d in filtered_docs:
                doc_id = d['doc_id']
                doc_name = d['req_name']
                trav_name = d.get('traveller_name') or "All Travellers / Shared"
                trip_label = d.get('trip_name') or "Traveller Vault (Reusable)"
                status = d['status']
                fmt = d.get('file_format', 'PDF')
                size_str = d.get('file_size_str', '0 KB')
                upload_date = d.get('uploaded_at', '')[:10]

                icon = "📄" if fmt == "PDF" else "🖼️"

                with st.container():
                    c_info, c_actions = st.columns([3, 2])
                    with c_info:
                        st.markdown(
                            f"<div style='display:flex; align-items:center; gap:8px;'>"
                            f"<span style='font-size:1.3rem;'>{icon}</span>"
                            f"<strong style='color:#0B2348; font-size:1.0rem;'>{doc_name}</strong>"
                            f"{render_badge(status)}"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            f"<div style='font-size:0.83rem; color:#64748B; margin-left:30px; margin-top:2px;'>"
                            f"👤 <strong>{trav_name}</strong> &nbsp;|&nbsp; ✈️ {trip_label}<br>"
                            f"📅 {upload_date} &nbsp;|&nbsp; 💾 {size_str} ({fmt})"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    with c_actions:
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if not d.get('file_exists', False):
                                st.caption("⚠️ File Missing")
                            else:
                                is_currently_previewed = (active_preview_doc == doc_id)
                                prev_label = "✖ Close" if is_currently_previewed else "👁️ Preview"
                                if st.button(prev_label, key=f"btn_prev_{doc_id}_{customer_id}", use_container_width=True):
                                    if is_currently_previewed:
                                        st.session_state.pop(f'vault_preview_doc_{customer_id}', None)
                                    else:
                                        st.session_state[f'vault_preview_doc_{customer_id}'] = doc_id
                                    st.rerun()

                        with col_btn2:
                            if d.get('file_exists', False):
                                try:
                                    dl_data = services.get_document_for_download_or_preview(
                                        doc_id=doc_id,
                                        customer_id=customer_id,
                                        session_token=session_token,
                                        action='download'
                                    )
                                    st.download_button(
                                        label="📥 Download",
                                        data=dl_data['file_bytes'],
                                        file_name=dl_data['file_name'],
                                        mime=dl_data['mime_type'],
                                        key=f"dl_doc_{doc_id}_{customer_id}",
                                        use_container_width=True
                                    )
                                except Exception as dl_err:
                                    st.caption(f"Error: {dl_err}")

                    # Inline Preview Panel
                    if active_preview_doc == doc_id and d.get('file_exists', False):
                        st.markdown(
                            f"<div style='background:#FFFFFF; border:2px solid #0875B8; border-radius:10px; padding:16px; margin:14px 0 18px 0; box-shadow:0 2px 8px rgba(8,117,184,0.1);'>"
                            f"<div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;'>"
                            f"<strong style='color:#0B2348;'>Preview: {doc_name} ({trav_name})</strong>"
                            f"<span style='font-size:0.82rem; color:#64748B;'>Format: {fmt}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                        try:
                            prev_data = services.get_document_for_download_or_preview(
                                doc_id=doc_id,
                                customer_id=customer_id,
                                session_token=session_token,
                                action='preview'
                            )
                            if fmt == "PDF":
                                import base64
                                b64_pdf = base64.b64encode(prev_data['file_bytes']).decode('utf-8')
                                pdf_iframe = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="550" style="border:1px solid #E5EAF1; border-radius:6px;" type="application/pdf"></iframe>'
                                st.markdown(pdf_iframe, unsafe_allow_html=True)
                            elif fmt in ("JPG", "JPEG", "PNG"):
                                st.image(prev_data['file_bytes'], use_column_width=True)
                            else:
                                st.info(f"Inline preview is not supported for {fmt} files. Please use the Download option.")
                        except Exception as p_err:
                            st.error(f"Failed to preview document: {p_err}")
                        st.markdown("</div>", unsafe_allow_html=True)

                    st.markdown("<hr style='margin:10px 0; border:none; border-top:1px solid #E5EAF1;'>", unsafe_allow_html=True)

# Tab 4: Recent Activity
with tabs[4]:
    st.markdown('<div class="kt-section-title">⏱️ Activity History</div>', unsafe_allow_html=True)
    conn = database.get_connection()
    acts = conn.execute("SELECT * FROM activity WHERE customer_id=? ORDER BY id DESC", (customer_id,)).fetchall()
    conn.close()
    if not acts:
        st.info("No activity recorded for this customer.")
    else:
        for a in acts:
            ts = a['timestamp'][:19].replace('T', ' ')
            st.markdown(f"⏱️ **{ts}** &nbsp;—&nbsp; {a['description']}")

# Tab 5: Internal Notes
with tabs[5]:
    st.markdown('<div class="kt-section-title">📝 Internal Notes</div>', unsafe_allow_html=True)
    st.text_area("Add an internal staff note about this customer", placeholder="Type notes here...")
    st.button("Save Note", key=f"save_cust_note_{customer_id}")
