import os
import shutil

BASE_DIR = r"C:\KT_Vault_V3"
PAGES_DIR = os.path.join(BASE_DIR, "pages")

files = {
    "app.py": """import streamlit as st
import os

st.set_page_config(page_title="Khanna Travels Vault", layout="wide")

from database import init_db
init_db()

query_params = st.query_params
page = query_params.get("page", "staff_home")

def load_page(page_name):
    page_path = os.path.join(os.path.dirname(__file__), 'pages', f"{page_name}.py")
    if os.path.exists(page_path):
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            exec(code, globals())
    else:
        st.error(f"Page {page_name} not found.")

valid_pages = [
    "staff_home", "customers", "customer_workspace", "trips", 
    "trip_workspace", "documents", "document_review", 
    "smart_upload", "vault_search"
]

if page in valid_pages:
    load_page(page)
else:
    load_page("staff_home")

st.markdown('''
<style>
    [data-testid="collapsedControl"] { display: none; }
    section[data-testid="stSidebar"] { display: none; width: 0; }
</style>
''', unsafe_allow_html=True)
""",
    
    "ui_helpers.py": """import streamlit as st

def inject_custom_css():
    st.markdown('''
    <style>
        .stApp {
            background-color: #ffffff;
            color: #0d1b2a;
        }
        .top-nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 20px;
            border-bottom: 1px solid #e0e0e0;
            margin-bottom: 20px;
        }
        .nav-links {
            display: flex;
            gap: 20px;
        }
        .nav-links a {
            text-decoration: none;
            color: #555;
            font-weight: 500;
        }
        .nav-links a:hover {
            color: #1a73e8;
        }
        .nav-profile {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .avatar {
            width: 32px; height: 32px; border-radius: 50%;
            background-color: #555; color: white;
            display: flex; align-items: center; justify-content: center;
            font-weight: bold;
        }
        .badge {
            padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;
        }
        .badge.missing { background-color: #fce8e6; color: #d93025; }
        .badge.verified { background-color: #e6f4ea; color: #1e8e3e; }
        .badge.attention { background-color: #fef7e0; color: #f29900; }
        .badge.review { background-color: #e8f0fe; color: #1a73e8; }
        
        .card {
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            background: #fff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        div.stButton > button:first-child {
            background-color: #1a73e8;
            color: white;
            border-radius: 8px;
            border: none;
            padding: 0.5rem 1rem;
        }
        div.stButton > button:first-child:hover {
            background-color: #1557b0;
            color: white;
        }
        div.stButton > button[kind="secondary"]:first-child {
            background-color: white;
            color: #1a73e8;
            border: 1px solid #1a73e8;
        }
    </style>
    ''', unsafe_allow_html=True)

def render_top_nav():
    st.markdown('''
        <div class="top-nav">
            <div style="font-weight: 800; font-size: 1.2rem; color: #1a73e8; font-style: italic;">✈️ Khanna Travels</div>
            <div class="nav-links">
                <a href="/?page=staff_home">Home</a>
                <a href="/?page=customers">Customers</a>
                <a href="/?page=trips">Trips</a>
                <a href="/?page=documents">Documents</a>
                <a href="/?page=vault_search">Vault Search</a>
            </div>
            <div class="nav-profile">
                <span>🔔</span>
                <div class="avatar">SM</div>
                <span style="font-weight: 600;">Staff Member ⌵</span>
            </div>
        </div>
    ''', unsafe_allow_html=True)

def render_badge(status):
    mapping = {
        'Missing': ('missing', 'Missing'),
        'Verified': ('verified', 'Verified'),
        'Complete': ('verified', 'Complete'),
        'Under Review': ('review', 'Under Review'),
        'Needs Attention': ('attention', 'Needs Attention'),
        'Replace Required': ('missing', 'Replace Required'),
        'Re-upload Required': ('missing', 'Re-upload Required'),
        'Action Required': ('missing', 'Action Required')
    }
    css_class, text = mapping.get(status, ('attention', status))
    return f'<span class="badge {css_class}">{text}</span>'
""",
    
    "pages/staff_home.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_all_documents_for_review

inject_custom_css()
render_top_nav()

st.markdown('''
<div style="background: linear-gradient(to right, #002B5B, #0056b3); padding: 40px; border-radius: 12px; color: white; margin-bottom: 20px;">
    <h1 style="margin:0; font-size: 2.5rem;">KHANNA TRAVELS<br>CUSTOMER TRAVEL DOCUMENT VAULT</h1>
    <p style="margin-top:10px; font-size: 1.1rem; opacity: 0.9;">Good Morning. Here's what needs your attention today.</p>
</div>
''', unsafe_allow_html=True)

docs = get_all_documents_for_review()
need_review_count = len([d for d in docs if d['status'] == 'Under Review'])
missing_count = 0

st.markdown(f'''
<div style="display:flex; gap: 20px; margin-bottom: 30px;">
    <div class="card" style="flex:1; border-top: 4px solid #1a73e8;">
        <h2 style="margin:0; color:#1a73e8;">{need_review_count}</h2>
        <p style="margin:0;">Need Review</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #d93025;">
        <h2 style="margin:0; color:#d93025;">{missing_count}</h2>
        <p style="margin:0;">Missing Documents</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #f29900;">
        <h2 style="margin:0; color:#f29900;">0</h2>
        <p style="margin:0;">Validity Alerts</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #f29900;">
        <h2 style="margin:0; color:#f29900;">0</h2>
        <p style="margin:0;">Expiring Soon</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #d93025;">
        <h2 style="margin:0; color:#d93025;">0</h2>
        <p style="margin:0;">Re-upload Required</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #1e8e3e;">
        <h2 style="margin:0; color:#1e8e3e;">0</h2>
        <p style="margin:0;">Ready for Final Review</p>
    </div>
</div>
''', unsafe_allow_html=True)

st.subheader("UPCOMING TRIPS")

col1, col2, col3 = st.columns([1, 4, 1])
with col1:
    st.markdown(f'<div class="card" style="height:100%; text-align:center; background:#f8f9fa;">🏰<br>Dubai</div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'''
    <div style="padding: 10px 0;">
        <h3 style="margin:0;">Amit Mehta</h3>
        <p style="margin:0;">Dubai Holiday</p>
        <p style="color:#666; margin: 5px 0;">📅 12 Dec 2026 - 18 Dec 2026</p>
        <p style="color:#666; margin: 5px 0;">9 Documents Received | {need_review_count} Awaiting Review | {missing_count} Missing</p>
    </div>
    ''', unsafe_allow_html=True)
with col3:
    if st.button("Open Trip", key="open_trip_home", use_container_width=True):
        st.query_params.trip_id = "KT-T-0001"
        st.query_params.page = "trip_workspace"
        st.rerun()

st.subheader("ATTENTION ITEMS")
if docs:
    for d in docs:
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
            c1.write(f"**{d['customer_name']}**")
            c2.write(d['req_name'])
            c3.markdown(render_badge(d['status']), unsafe_allow_html=True)
            if c4.button("Review", key=f"rev_home_{d['id']}"):
                st.query_params.doc_id = d['id']
                st.query_params.page = "document_review"
                st.rerun()
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
else:
    st.info("No items require attention.")
""",

    "pages/customers.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav
import database

inject_custom_css()
render_top_nav()

st.title("Customers")

st.text_input("Search Customer (Name, ID)", placeholder="e.g. Amit Mehta")

conn = database.get_connection()
customers = conn.execute("SELECT * FROM customers").fetchall()
conn.close()

for c in customers:
    with st.container():
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
        c1.write(f"**{c['id']}**")
        c2.write(f"**{c['name']}**")
        c3.write(c['customer_type'])
        c4.write(c['status'])
        if c5.button("Open Customer", key=f"open_cust_{c['id']}"):
            st.query_params.customer_id = c['id']
            st.query_params.page = "customer_workspace"
            st.rerun()
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
""",

    "pages/customer_workspace.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav
import database

inject_custom_css()
render_top_nav()

customer_id = st.query_params.get("customer_id", "KT-C-0001")

conn = database.get_connection()
c = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
conn.close()

if not c:
    st.error("Customer not found.")
    st.stop()

if st.button("← Back to Customers"):
    st.query_params.page = "customers"
    st.rerun()

st.markdown(f'''
<div style="background: #f8f9fa; padding: 20px; border-radius: 12px; margin-bottom: 20px; border: 1px solid #e0e0e0;">
    <h2 style="margin:0; color: #0d1b2a; text-transform: uppercase;">{c['name']}</h2>
    <p style="margin: 5px 0 0 0; color: #666;">{c['id']} | {c['customer_type']} | {c['status']}</p>
</div>
''', unsafe_allow_html=True)

tabs = st.tabs(["Customer Details", "Traveller Profiles", "Trips", "Reusable Documents", "Recent Activity", "Internal Notes"])

with tabs[0]:
    st.write("### Customer Details")
    st.write("Basic contact and profile information for this customer record.")

with tabs[1]:
    st.write("### Traveller Profiles")
    conn = database.get_connection()
    travs = conn.execute("SELECT * FROM travellers WHERE customer_id=?", (customer_id,)).fetchall()
    conn.close()
    for t in travs:
        st.write(f"- {t['name']} ({t['type']} - {t['role']})")

with tabs[2]:
    st.write("### Trips")
    conn = database.get_connection()
    trips = conn.execute("SELECT * FROM trips WHERE customer_id=?", (customer_id,)).fetchall()
    conn.close()
    for t in trips:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{t['name']}** ({t['id']}) - {t['destination']}")
        with col2:
            if st.button("Open Trip", key=f"ot_{t['id']}"):
                st.query_params.trip_id = t['id']
                st.query_params.page = "trip_workspace"
                st.rerun()

with tabs[3]:
    st.write("### Reusable Documents")
    st.write("Verified Passport / Profiles")

with tabs[4]:
    st.write("### Recent Activity")
    st.write("Customer record created.")

with tabs[5]:
    st.write("### Internal Notes")
    st.text_area("Add a note about this customer")
    st.button("Save Note")
""",

    "pages/trips.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav
from services import calculate_readiness
import database

inject_custom_css()
render_top_nav()

st.title("Trips")

st.text_input("Search Trip (ID, Customer, Destination)", placeholder="e.g. Dubai")

conn = database.get_connection()
trips = conn.execute('''
    SELECT t.*, c.name as customer_name
    FROM trips t JOIN customers c ON t.customer_id = c.id
''').fetchall()
conn.close()

for t in trips:
    total, comp, att, miss, pct, _ = calculate_readiness(t['id'])
    with st.container():
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
        c1.write(f"**{t['id']}**<br>{t['name']}", unsafe_allow_html=True)
        c2.write(f"Customer:<br>{t['customer_name']}", unsafe_allow_html=True)
        c3.write(f"Destination:<br>{t['destination']}", unsafe_allow_html=True)
        c4.write(f"Readiness: {pct}%")
        if c5.button("Open Trip", key=f"open_trip_{t['id']}"):
            st.query_params.trip_id = t['id']
            st.query_params.page = "trip_workspace"
            st.rerun()
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
""",

    "pages/trip_workspace.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_trip_details, get_requirements, calculate_readiness
import database

inject_custom_css()
render_top_nav()

trip_id = st.query_params.get('trip_id', 'KT-T-0001')

if st.button("← Back to Trips", key="back"):
    st.query_params.page = "trips"
    st.rerun()

trip = get_trip_details(trip_id)
if not trip:
    st.error("Trip not found.")
    st.stop()
    
reqs = get_requirements(trip_id)
_, comp, att, miss, pct, _ = calculate_readiness(trip_id)

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
    <div style="flex: 1; background: white; border: 1px solid #e0e0e0; padding: 20px; border-radius: 12px; display:flex; align-items:center; justify-content:space-between;">
        <div>
            <h4 style="margin:0;">Travel Readiness</h4>
            <p style="margin:5px 0; font-size:0.9rem; color:#1e8e3e;">✅ {comp} Complete</p>
            <p style="margin:5px 0; font-size:0.9rem; color:#f29900;">⚠️ {att} Pending / Attention</p>
            <p style="margin:5px 0; font-size:0.9rem; color:#d93025;">❌ {miss} Action Required</p>
        </div>
        <h1 style="margin:0; color:#1a73e8;">{pct}%</h1>
    </div>
</div>
''', unsafe_allow_html=True)

tabs = st.tabs(["Document Checklist", "Trip Itinerary", "Traveller", "Trip Details", "Notes", "Activity"])

with tabs[0]:
    st.markdown("### TRAVELLER DOCUMENTS")
    st.markdown("<div style='background:#f1f3f4; padding:10px; border-radius:8px; margin-bottom:15px;'><strong>Amit Mehta</strong></div>", unsafe_allow_html=True)
    
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
                        pass
                else:
                    if st.button("Replace Document", key=f"rep_{r['id']}"):
                        st.session_state['upload_req_id'] = r['id']
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
                        st.query_params.page = "smart_upload"
                        st.rerun()
                elif status == 'Under Review':
                    if st.button("Review", key=f"rev_{r['id']}"):
                        st.query_params.doc_id = r['doc_id']
                        st.query_params.page = "document_review"
                        st.rerun()
                elif status == 'Verified':
                    if st.button("View", key=f"view_{r['id']}"):
                        pass
                else:
                    if st.button("Replace Document", key=f"rep_{r['id']}"):
                        st.session_state['upload_req_id'] = r['id']
                        st.query_params.page = "smart_upload"
                        st.rerun()
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

with tabs[4]:
    st.write("### Internal Notes")
    note = st.text_area("Add internal staff note for this trip")
    if st.button("Save Note"):
        conn = database.get_connection()
        conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (trip_id, f"Note added: {note}"))
        conn.commit()
        conn.close()
        st.success("Note saved.")
    
    st.write("#### Existing Notes")
    conn = database.get_connection()
    acts = conn.execute("SELECT * FROM activity WHERE trip_id=? ORDER BY timestamp DESC", (trip_id,)).fetchall()
    conn.close()
    for a in acts:
        st.write(f"- {a['timestamp']}: {a['description']}")

with tabs[5]:
    st.write("### Activity History")
    for a in acts:
        st.write(f"{a['timestamp']}: {a['description']}")
""",

    "pages/documents.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
import database

inject_custom_css()
render_top_nav()

st.title("Documents")

st.markdown("Filter: [Need Review] | [Verified] | [Needs Attention] | [All Documents]")

conn = database.get_connection()
docs = conn.execute('''
    SELECT d.*, r.name as req_name, r.type as req_type, c.name as customer_name, t.name as trip_name, tr.name as traveller_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    JOIN customers c ON t.customer_id = c.id
    LEFT JOIN travellers tr ON r.traveller_id = tr.id
    ORDER BY d.uploaded_at DESC
''').fetchall()
conn.close()

for d in docs:
    with st.container():
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
        c1.write(f"**{d['customer_name']}**<br>{d['trip_name']}", unsafe_allow_html=True)
        c2.write(f"{d['req_name']}<br><small>{d['traveller_name'] or 'Trip Level'}</small>", unsafe_allow_html=True)
        c3.markdown(render_badge(d['status']), unsafe_allow_html=True)
        c4.write(d['uploaded_at'][:10] if d['uploaded_at'] else '')
        if d['status'] == 'Under Review':
            if c5.button("Review", key=f"rev_doc_{d['id']}"):
                st.query_params.doc_id = d['id']
                st.query_params.page = "document_review"
                st.rerun()
        else:
            if c5.button("View", key=f"view_doc_{d['id']}"):
                pass
        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
""",

    "pages/document_review.py": """import streamlit as st
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

if st.button("← Back"):
    st.query_params.page = "documents"
    st.rerun()

conn = database.get_connection()
d = conn.execute('''
    SELECT d.*, r.name as req_name, c.name as customer_name, t.name as trip_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    JOIN customers c ON t.customer_id = c.id
    WHERE d.id = ?
''', (doc_id,)).fetchone()
conn.close()

if not d:
    st.error("Document not found.")
    st.stop()

st.markdown(f"<h2>Review: {d['req_name']} for {d['customer_name']}</h2>", unsafe_allow_html=True)
st.write(f"Trip: {d['trip_name']}")

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"<div class='card' style='height:400px; display:flex; align-items:center; justify-content:center; background:#f1f3f4;'>[Document Preview: {d['file_path']}]</div>", unsafe_allow_html=True)
with col2:
    st.write("### Extracted Information")
    data = json.loads(d['extracted_data']) if d['extracted_data'] else {}
    for k, v in data.items():
        st.text_input(k, value=v, key=f"edit_{k}")
        
    c1, c2, c3 = st.columns(3)
    if c1.button("Verify Document", type="primary"):
        verify_document(d['id'])
        # Add activity
        conn = database.get_connection()
        req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
        conn.execute("INSERT INTO activity (trip_id, description) VALUES (?, ?)", (req['trip_id'], f"Document {d['id']} verified"))
        conn.commit()
        conn.close()
        st.success("Document Verified!")
    if c2.button("Reject"):
        st.warning("Rejected (Demo)")
    if c3.button("Request Re-upload"):
        st.warning("Requested Re-upload (Demo)")
    
    st.write("### Add Note")
    st.text_area("Internal staff note about this document")
    st.button("Save Note")
""",

    "pages/smart_upload.py": """import streamlit as st
import time
from ui_helpers import inject_custom_css, render_top_nav
from document_processor import process_document
from services import save_document
import os
import database

inject_custom_css()
render_top_nav()

req_id = st.session_state.get('upload_req_id')

if not req_id:
    st.error("No requirement selected. Please start from a Trip Workspace.")
    st.stop()

conn = database.get_connection()
req = conn.execute("SELECT r.*, c.name as c_name, t.name as t_name FROM requirements r JOIN trips t ON r.trip_id=t.id JOIN customers c ON t.customer_id=c.id WHERE r.id=?", (req_id,)).fetchone()
conn.close()

if st.button("← Back to Trip"):
    st.query_params.trip_id = req['trip_id']
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
            
        if uploaded_file is not None:
            st.session_state['uploaded_filename'] = uploaded_file.name
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
            
        result = process_document(st.session_state['uploaded_filename'], {})
        st.session_state['extracted_result'] = result
        st.session_state['upload_step'] = 3
        st.rerun()

    elif st.session_state['upload_step'] == 3:
        result = st.session_state['extracted_result']
        st.success(f"{result['document_type']} Detected ✓")
        
        st.write("### Review Extracted Information")
        fields = result['extracted_fields']
        
        updated_fields = {}
        c1, c2 = st.columns(2)
        idx = 0
        for k, v in fields.items():
            if idx % 2 == 0:
                with c1: updated_fields[k] = st.text_input(k, value=v)
            else:
                with c2: updated_fields[k] = st.text_input(k, value=v)
            idx += 1
            
        col_c, col_s = st.columns(2)
        if col_c.button("Cancel"):
            st.session_state['upload_step'] = 1
            st.rerun()
            
        if col_s.button("Confirm & Save Document"):
            fake_path = os.path.join("documents", st.session_state['uploaded_filename'])
            save_document(req_id, fake_path, updated_fields)
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
            st.query_params.page = "trip_workspace"
            st.rerun()
""",

    "pages/vault_search.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
import database

inject_custom_css()
render_top_nav()

st.title("Vault Search")

col1, col2, col3 = st.columns(3)
with col1:
    st.text_input("Customer Name")
with col2:
    st.text_input("Document Type")
with col3:
    st.selectbox("Status", ["All", "Under Review", "Verified", "Missing", "Re-upload Required"])

st.button("Search", type="primary")

st.markdown("<hr>", unsafe_allow_html=True)

conn = database.get_connection()
docs = conn.execute('''
    SELECT d.*, r.name as req_name, c.name as customer_name, t.name as trip_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    JOIN customers c ON t.customer_id = c.id
    ORDER BY d.uploaded_at DESC
''').fetchall()
conn.close()

if docs:
    for d in docs:
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
            c1.write(f"**{d['customer_name']}**<br>{d['trip_name']}", unsafe_allow_html=True)
            c2.write(d['req_name'])
            c3.markdown(render_badge(d['status']), unsafe_allow_html=True)
            if c4.button("Open", key=f"search_open_{d['id']}"):
                st.query_params.doc_id = d['id']
                st.query_params.page = "document_review"
                st.rerun()
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
"""
}

for filepath, content in files.items():
    full_path = os.path.join(BASE_DIR, filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

# Delete old files
old_files = [
    "pages/customer_home.py", "pages/customer_trip.py", 
    "pages/customer_documents.py", "pages/customer_profile.py",
    "pages/staff_customers.py", "pages/staff_trips.py", "pages/staff_review.py"
]

for f in old_files:
    fp = os.path.join(BASE_DIR, f)
    if os.path.exists(fp):
        os.remove(fp)

print("Refactoring complete.")
