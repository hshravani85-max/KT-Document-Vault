import streamlit as st
from ui_helpers import (
    inject_custom_css,
    render_top_nav,
    render_badge,
    render_kpi_card,
    render_welcome_banner
)
from services import get_all_documents_for_review, calculate_readiness
import database

inject_custom_css()
render_top_nav()

# 1. Professional Travel Photography Welcome Banner
render_welcome_banner()

# 2. Database Metrics Calculation
conn = database.get_connection()

need_review_count = conn.execute("SELECT count(*) FROM documents WHERE status = 'Under Review'").fetchone()[0]

missing_count = conn.execute('''
    SELECT count(*) FROM requirements r
    LEFT JOIN documents d ON r.id = d.requirement_id
    WHERE d.id IS NULL OR d.status IN ('Replace Required', 'Action Required')
''').fetchone()[0]

reupload_count = conn.execute("SELECT count(*) FROM documents WHERE status = 'Re-upload Required'").fetchone()[0]

readiness_trip_rows = conn.execute("SELECT id FROM trips").fetchall()

ready_for_review_count = 0
for t in readiness_trip_rows:
    _, _, _, _, _, business_status = calculate_readiness(t['id'])
    if business_status == 'READY FOR FINAL REVIEW':
        ready_for_review_count += 1

# Check for expiring soon / validity alerts from documents if available
validity_alerts_count = 0
expiring_soon_count = 0

trips = conn.execute('''
    SELECT t.*, c.name as customer_name
    FROM trips t
    LEFT JOIN customers c ON t.customer_id = c.id
    ORDER BY t.start_date ASC
''').fetchall()

conn.close()

# 3. 6 Structured KPI Cards
st.markdown('<div class="kt-section-title">📊 Document & Trip Metrics</div>', unsafe_allow_html=True)

kpi_cols = st.columns(6)
with kpi_cols[0]:
    st.markdown(render_kpi_card("Need Review", need_review_count, color="#2563EB", icon="📄"), unsafe_allow_html=True)
with kpi_cols[1]:
    st.markdown(render_kpi_card("Missing Documents", missing_count, color="#DC2626", icon="⚠️"), unsafe_allow_html=True)
with kpi_cols[2]:
    st.markdown(render_kpi_card("Validity Alerts", validity_alerts_count, color="#F59E0B", icon="🔔"), unsafe_allow_html=True)
with kpi_cols[3]:
    st.markdown(render_kpi_card("Expiring Soon", expiring_soon_count, color="#F59E0B", icon="⏳"), unsafe_allow_html=True)
with kpi_cols[4]:
    st.markdown(render_kpi_card("Re-upload Req.", reupload_count, color="#DC2626", icon="🔄"), unsafe_allow_html=True)
with kpi_cols[5]:
    st.markdown(render_kpi_card("Ready for Review", ready_for_review_count, color="#16A34A", icon="✅"), unsafe_allow_html=True)

# 4. Quick Actions
st.markdown('<div class="kt-section-title">⚡ Quick Actions</div>', unsafe_allow_html=True)
qa_cols = st.columns(4)
with qa_cols[0]:
    if st.button("➕ Add Customer", key="qa_add_cust", use_container_width=True):
        st.session_state['show_add_customer'] = True
        st.session_state['nav_page'] = "customers"
        st.query_params.page = "customers"
        st.rerun()
with qa_cols[1]:
    if st.button("✈️ View Trips", key="qa_view_trips", use_container_width=True):
        st.session_state['nav_page'] = "trips"
        st.query_params.page = "trips"
        st.rerun()
with qa_cols[2]:
    if st.button("📤 Smart Upload", key="qa_smart_upload", use_container_width=True):
        st.session_state['nav_page'] = "smart_upload"
        st.query_params.page = "smart_upload"
        st.rerun()
with qa_cols[3]:
    if st.button("🔍 Search Documents", key="qa_search_docs", use_container_width=True):
        st.session_state['nav_page'] = "vault_search"
        st.query_params.page = "vault_search"
        st.rerun()

# 5. Upcoming Trips
st.markdown('<div class="kt-section-title">✈️ Upcoming Trips</div>', unsafe_allow_html=True)

if not trips:
    st.info("No upcoming trips found.")
else:
    for t in trips:
        tot, comp, att, miss, pct, b_status = calculate_readiness(t['id'])
        dest_icon = "🏰" if "Dubai" in (t['destination'] or '') else ("🌆" if "Singapore" in (t['destination'] or '') else "✈️")
        
        with st.container(border=True):
            c_icon, c_info, c_action = st.columns([0.8, 6, 2])
            with c_icon:
                st.markdown(f"<div style='font-size:2rem; text-align:center; padding-top:6px;'>{dest_icon}</div>", unsafe_allow_html=True)
            with c_info:
                st.markdown(f"#### {t['customer_name'] or 'Unknown Customer'} — {t['name']}")
                st.markdown(f"📅 {t['start_date']} to {t['end_date']} &nbsp;|&nbsp; Trip ID: `{t['id']}` &nbsp;|&nbsp; 📍 **{t['destination']}**")
                st.markdown(f"**{comp}** of {tot} Complete &nbsp;•&nbsp; :red[{miss} Action Required] &nbsp;•&nbsp; :orange[{att} Pending Review]")
            with c_action:
                st.markdown(f"{render_badge(b_status)}", unsafe_allow_html=True)
                st.write("")
                if st.button("Open Trip", key=f"open_trip_home_{t['id']}", use_container_width=True):
                    st.query_params.trip_id = t['id']
                    st.session_state['nav_page'] = "trip_workspace"
                    st.query_params.page = "trip_workspace"
                    st.rerun()

# 6. Attention Items
st.markdown('<div class="kt-section-title">⚠️ Attention Items</div>', unsafe_allow_html=True)

docs = get_all_documents_for_review()
if docs:
    for d in docs:
        with st.container():
            c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
            with c1:
                st.markdown(f"**{d['customer_name']}**<br><span style='font-size:0.82rem; color:#64748B;'>{d['trip_name']}</span>", unsafe_allow_html=True)
            with c2:
                trav = f" ({d['traveller_name']})" if d.get('traveller_name') else ""
                st.markdown(f"**{d['req_name']}**{trav}<br><span style='font-size:0.82rem; color:#64748B;'>Doc ID: <code>{d['id']}</code></span>", unsafe_allow_html=True)
            with c3:
                st.markdown(f"<div style='padding-top:4px;'>{render_badge(d['status'])}</div>", unsafe_allow_html=True)
            with c4:
                if st.button("Review", key=f"rev_home_{d['id']}", use_container_width=True):
                    st.query_params.doc_id = d['id']
                    st.session_state['nav_page'] = "document_review"
                    st.query_params.page = "document_review"
                    st.rerun()
            st.markdown("<hr style='margin:8px 0; border:none; border-top:1px solid #E5EAF1;'>", unsafe_allow_html=True)
else:
    with st.container(border=True):
        st.markdown(
            "<div style='text-align:center; padding:16px;'>"
            "<span style='font-size:1.8rem; color:#16A34A;'>✓</span>"
            "<div style='font-weight:600; color:#0B2348; margin-top:6px;'>All caught up!</div>"
            "<div style='font-size:0.85rem; color:#64748B;'>No travel documents currently require staff attention.</div>"
            "</div>",
            unsafe_allow_html=True
        )
