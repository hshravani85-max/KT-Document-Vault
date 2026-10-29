import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
import database
import services

inject_custom_css()
render_top_nav()

# Page Header
head_col, btn_col1, btn_col2 = st.columns([3, 1.5, 1.5])
with head_col:
    st.markdown('<h1 style="color:#0B2348; margin:0; font-size:2rem; font-weight:800;">Customers</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color:#64748B; margin:4px 0 16px 0; font-size:0.95rem;">Manage customer accounts, traveller profiles, and document vaults.</p>', unsafe_allow_html=True)
with btn_col1:
    if st.button("➕ New from Document", type="primary", use_container_width=True, icon=":material/person_add:"):
        st.session_state['nav_page'] = "smart_intake"
        st.query_params.page = "smart_intake"
        st.rerun()
with btn_col2:
    if st.button("➕ Add Manually", use_container_width=True, icon=":material/edit:"):
        st.session_state['show_add_customer'] = True

if st.session_state.get('show_add_customer', False):
    st.markdown('<div class="kt-card">', unsafe_allow_html=True)
    st.markdown("### Create New Customer")
    with st.form("add_customer_form"):
        name = st.text_input("Full Name *")
        mobile = st.text_input("Mobile Number")
        email = st.text_input("Email Address")
        ctype = st.selectbox("Customer Type", ["Individual", "Family", "Corporate", "Group"])
        
        col1, col2 = st.columns(2)
        with col1:
            submit = st.form_submit_button("Save Customer", type="primary")
        with col2:
            cancel = st.form_submit_button("Cancel")
            
        if submit:
            if not name.strip():
                st.error("Full Name is required.")
            else:
                new_id = services.create_customer(
                    full_name=name.strip(),
                    mobile=mobile.strip() if mobile.strip() else None,
                    email=email.strip() if email.strip() else None,
                    customer_type=ctype,
                    session_token=st.session_state.get('session_token')
                )
                st.session_state['show_add_customer'] = False
                st.query_params.customer_id = new_id
                st.session_state['nav_page'] = "customer_workspace"
                st.query_params.page = "customer_workspace"
                st.rerun()
        if cancel:
            st.session_state['show_add_customer'] = False
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

search_term = st.text_input("Search Customer (Name, ID, Mobile, Email)", placeholder="e.g. Amit Mehta or KT-C-0001", key="customer_search_term").strip()

session_token = st.session_state.get('session_token')
if search_term:
    try:
        customers = services.search_customers(search_term, session_token)
    except Exception as e:
        st.error(f"Search error: {e}")
        customers = []
else:
    conn = database.get_connection()
    customers = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    conn.close()
    customers = [dict(c) for c in customers]

if not customers:
    if search_term:
        st.info(f"No customers found matching '{search_term}'.")
    else:
        st.info("No customers found.")
else:
    st.markdown(f"<div style='font-size:0.85rem; color:#64748B; margin-bottom:12px;'>Showing <strong>{len(customers)}</strong> customer accounts</div>", unsafe_allow_html=True)
    for c in customers:
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 4, 2, 2])
            with c1:
                st.markdown(f"**<code>{c['id']}</code>**", unsafe_allow_html=True)
            with c2:
                contact_info = []
                if c.get('mobile'): contact_info.append(f"📞 {c['mobile']}")
                if c.get('email'): contact_info.append(f"✉️ {c['email']}")
                contact_str = f"<span style='font-size:0.8rem; color:#64748B;'>{' • '.join(contact_info)}</span>" if contact_info else ""
                st.markdown(f"<div style='font-weight:700; font-size:1.05rem; color:#0B2348;'>{c['name']}</div>{contact_str}", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div style='margin-bottom:4px;'><span style='font-size:0.82rem; color:#64748B; font-weight:600;'>{c['customer_type']}</span></div>{render_badge(c['status'])}", unsafe_allow_html=True)
            with c4:
                if st.button("Open Workspace", key=f"open_cust_{c['id']}", use_container_width=True):
                    st.query_params.customer_id = c['id']
                    st.session_state['nav_page'] = "customer_workspace"
                    st.query_params.page = "customer_workspace"
                    st.rerun()
            st.markdown("<hr style='margin:10px 0; border:none; border-top:1px solid #E5EAF1;'>", unsafe_allow_html=True)
