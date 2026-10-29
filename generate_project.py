import os

BASE_DIR = r"C:\KT_Vault_V3"

files = {
    "requirements.txt": """streamlit
""",
    
    "database.py": """import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT,
            customer_type TEXT,
            status TEXT
        );
        CREATE TABLE IF NOT EXISTS travellers (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            name TEXT,
            type TEXT,
            role TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            name TEXT,
            destination TEXT,
            start_date TEXT,
            end_date TEXT,
            trip_type TEXT,
            service TEXT,
            department TEXT,
            status TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS trip_travellers (
            trip_id TEXT,
            traveller_id TEXT,
            PRIMARY KEY(trip_id, traveller_id),
            FOREIGN KEY(trip_id) REFERENCES trips(id),
            FOREIGN KEY(traveller_id) REFERENCES travellers(id)
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            trip_id TEXT,
            traveller_id TEXT,
            name TEXT,
            type TEXT,
            UNIQUE(trip_id, traveller_id, name)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            requirement_id TEXT,
            status TEXT,
            extracted_data TEXT,
            file_path TEXT,
            uploaded_at TEXT,
            FOREIGN KEY(requirement_id) REFERENCES requirements(id)
        );
        CREATE TABLE IF NOT EXISTS user_profile (
            customer_id TEXT PRIMARY KEY,
            full_name TEXT,
            dob TEXT,
            nationality TEXT,
            passport_number TEXT,
            passport_expiry TEXT
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    c.execute("INSERT OR IGNORE INTO customers (id, name, customer_type, status) VALUES (?, ?, ?, ?)",
              ('KT-C-0001', 'Amit Mehta', 'Individual', 'Active'))
    
    c.execute("INSERT OR IGNORE INTO travellers (id, customer_id, name, type, role) VALUES (?, ?, ?, ?, ?)",
              ('KT-TR-0001', 'KT-C-0001', 'Amit Mehta', 'Adult', 'Lead Traveller'))
              
    c.execute("INSERT OR IGNORE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              ('KT-T-0001', 'KT-C-0001', 'Dubai Holiday', 'Dubai, UAE', '2026-12-12', '2026-12-18', 'Holiday', 'International Package', 'Operations', 'Documents In Progress'))
              
    c.execute("INSERT OR IGNORE INTO trip_travellers (trip_id, traveller_id) VALUES (?, ?)",
              ('KT-T-0001', 'KT-TR-0001'))
              
    reqs = [
        ('REQ-TR-01', 'KT-T-0001', 'KT-TR-0001', 'Passport', 'TRAVELLER'),
        ('REQ-TR-02', 'KT-T-0001', 'KT-TR-0001', 'Visa / Entry Document', 'TRAVELLER'),
        ('REQ-T-01', 'KT-T-0001', None, 'Flight Ticket', 'TRIP'),
        ('REQ-T-02', 'KT-T-0001', None, 'Hotel Voucher', 'TRIP'),
        ('REQ-T-03', 'KT-T-0001', None, 'Travel Insurance', 'TRIP'),
        ('REQ-T-04', 'KT-T-0001', None, 'Transfer Voucher', 'TRIP'),
        ('REQ-T-05', 'KT-T-0001', None, 'Sightseeing Voucher', 'TRIP'),
        ('REQ-T-06', 'KT-T-0001', None, 'Arrival / Entry Document', 'TRIP'),
        ('REQ-T-07', 'KT-T-0001', None, 'Itinerary', 'TRIP')
    ]
    for r in reqs:
        c.execute("INSERT OR IGNORE INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, ?, ?, ?, ?)", r)
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
""",

    "ui_helpers.py": """import streamlit as st
import base64

def inject_custom_css():
    st.markdown('''
    <style>
        .stApp {
            background-color: #ffffff;
            color: #0d1b2a;
        }
        /* Top Navigation styling */
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
            background-color: #1a73e8; color: white;
            display: flex; align-items: center; justify-content: center;
            font-weight: bold;
        }
        /* Badges */
        .badge {
            padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600;
        }
        .badge.missing { background-color: #fce8e6; color: #d93025; }
        .badge.verified { background-color: #e6f4ea; color: #1e8e3e; }
        .badge.attention { background-color: #fef7e0; color: #f29900; }
        .badge.review { background-color: #fef7e0; color: #f29900; }
        .badge.upcoming { background-color: #e8f0fe; color: #1a73e8; }
        
        /* Cards */
        .card {
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
            background: #fff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        /* Buttons overriding Streamlit default */
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

def render_top_nav(is_staff=False):
    if not is_staff:
        st.markdown('''
            <div class="top-nav">
                <div style="font-weight: 800; font-size: 1.2rem; color: #1a73e8; font-style: italic;">✈️ Khanna Travels</div>
                <div class="nav-links">
                    <a href="/?page=customer_home">Home</a>
                    <a href="/?page=customer_trip">My Trips</a>
                    <a href="/?page=customer_documents">My Documents</a>
                    <a href="/?page=customer_profile">Profile</a>
                </div>
                <div class="nav-profile">
                    <span>🔔</span>
                    <div class="avatar">AM</div>
                    <span style="font-weight: 600;">Amit Mehta ⌵</span>
                </div>
            </div>
        ''', unsafe_allow_html=True)
    else:
        st.markdown('''
            <div class="top-nav">
                <div style="font-weight: 800; font-size: 1.2rem; color: #1a73e8; font-style: italic;">✈️ Khanna Travels</div>
                <div class="nav-links">
                    <a href="/?page=staff_home">Home</a>
                    <a href="/?page=staff_customers">Customers</a>
                    <a href="/?page=staff_trips">Trips</a>
                    <a href="/?page=staff_review">Document Review</a>
                    <a href="#">Reports</a>
                </div>
                <div class="nav-profile">
                    <span>🔔</span>
                    <div class="avatar" style="background:#555;">SA</div>
                    <span style="font-weight: 600;">Staff Admin ⌵</span>
                </div>
            </div>
        ''', unsafe_allow_html=True)

def render_badge(status):
    mapping = {
        'Missing': ('missing', 'Missing'),
        'Verified': ('verified', 'Verified'),
        'Under Review': ('review', 'Under Review'),
        'Needs Attention': ('attention', 'Needs Attention'),
        'Replace Required': ('missing', 'Replace Required'),
        'Complete': ('verified', 'Complete'),
    }
    css_class, text = mapping.get(status, ('attention', status))
    return f'<span class="badge {css_class}">{text}</span>'
""",

    "services.py": """import database
import json

def get_trip_details(trip_id):
    conn = database.get_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    conn.close()
    return dict(trip) if trip else None

def get_requirements(trip_id):
    conn = database.get_connection()
    reqs = conn.execute('''
        SELECT r.*, d.id as doc_id, d.status as doc_status
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
        SELECT d.*, r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id, t.name as traveller_name, tr.name as trip_name, tr.customer_id, c.name as customer_name
        FROM documents d
        JOIN requirements r ON d.requirement_id = r.id
        LEFT JOIN travellers t ON r.traveller_id = t.id
        JOIN trips tr ON r.trip_id = tr.id
        JOIN customers c ON tr.customer_id = c.id
        WHERE d.status = 'Under Review'
    ''').fetchall()
    conn.close()
    return [dict(d) for d in docs]

def calculate_readiness(trip_id):
    reqs = get_requirements(trip_id)
    total = len(reqs)
    if total == 0: return 0, 0, 0, 0
    complete = 0
    attention = 0
    missing = 0
    for r in reqs:
        status = r.get('doc_status')
        if not status:
            missing += 1
        elif status == 'Verified':
            complete += 1
        else:
            attention += 1
    return total, complete, attention, missing, int((complete/total)*100)

def save_document(requirement_id, file_path, extracted_data):
    import uuid
    from datetime import datetime
    doc_id = 'DOC-' + str(uuid.uuid4())[:8]
    conn = database.get_connection()
    # Check if doc exists for req
    existing = conn.execute("SELECT id FROM documents WHERE requirement_id = ?", (requirement_id,)).fetchone()
    if existing:
        conn.execute("UPDATE documents SET status = ?, file_path = ?, extracted_data = ?, uploaded_at = ? WHERE id = ?",
                     ('Under Review', file_path, json.dumps(extracted_data), datetime.now().isoformat(), existing['id']))
    else:
        conn.execute("INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (doc_id, requirement_id, 'Under Review', json.dumps(extracted_data), file_path, datetime.now().isoformat()))
    
    # Also save to profile if passport
    req = conn.execute("SELECT name FROM requirements WHERE id = ?", (requirement_id,)).fetchone()
    if req and req['name'] == 'Passport':
        conn.execute("INSERT OR REPLACE INTO user_profile (customer_id, full_name, dob, nationality, passport_number, passport_expiry) VALUES (?, ?, ?, ?, ?, ?)",
                     ('KT-C-0001', extracted_data.get('Full Name'), extracted_data.get('Date of Birth'), extracted_data.get('Nationality'), extracted_data.get('Passport Number'), extracted_data.get('Expiry Date')))
    
    conn.commit()
    conn.close()
    return doc_id

def verify_document(doc_id):
    conn = database.get_connection()
    conn.execute("UPDATE documents SET status = 'Verified' WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
""",

    "document_processor.py": """import time

def process_document(file_path, context):
    time.sleep(1) # simulate processing
    
    # DEMO LOGIC based on context
    is_passport = 'passport' in file_path.lower() or 'demo' in file_path.lower()
    
    if is_passport:
        return {
            'document_type': 'Passport',
            'document_type_confidence': 0.99,
            'extracted_fields': {
                'Full Name': 'Amit Mehta',
                'Passport Number': 'P9002001-DEMO',
                'Date of Birth': '08 Feb 1991',
                'Nationality': 'Indian',
                'Issue Date': '15 Mar 2023',
                'Expiry Date': '14 Mar 2033'
            },
            'field_confidences': {'Expiry Date': 0.98},
            'suggested_customer': 'KT-C-0001',
            'suggested_traveller': 'KT-TR-0001',
            'suggested_trip': 'KT-T-0001',
            'warnings': []
        }
    else:
        return {
            'document_type': 'Unknown',
            'document_type_confidence': 0.5,
            'extracted_fields': {},
            'field_confidences': {},
            'suggested_customer': 'KT-C-0001',
            'suggested_traveller': None,
            'suggested_trip': 'KT-T-0001',
            'warnings': ['Could not detect document type confidently.']
        }
""",

    "app.py": """import streamlit as st
import os
import sys

# Ensure layout is wide
st.set_page_config(page_title="Khanna Travels Vault", layout="wide")

# Init DB idempotently
from database import init_db
init_db()

# Simple router
query_params = st.query_params
page = query_params.get("page", "customer_home")

def load_page(page_name):
    page_path = os.path.join(os.path.dirname(__file__), 'pages', f"{page_name}.py")
    if os.path.exists(page_path):
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            exec(code, globals())
    else:
        st.error(f"Page {page_name} not found.")

if page == "customer_home":
    load_page("customer_home")
elif page == "customer_trip":
    load_page("customer_trip")
elif page == "smart_upload":
    load_page("smart_upload")
elif page == "customer_documents":
    load_page("customer_documents")
elif page == "customer_profile":
    load_page("customer_profile")
elif page == "staff_home":
    load_page("staff_home")
elif page == "staff_customers":
    st.write("Staff Customers")
elif page == "staff_trips":
    st.write("Staff Trips")
elif page == "staff_review":
    load_page("staff_review")
else:
    load_page("customer_home")

# Provide a hidden dev toggle
with st.sidebar.expander("Development", expanded=False):
    st.write("Navigation")
    if st.button("Customer Home"): st.query_params.page = "customer_home"; st.rerun()
    if st.button("Staff Action Center"): st.query_params.page = "staff_review"; st.rerun()

# Hide sidebar for users via CSS
st.markdown('''
<style>
    [data-testid="collapsedControl"] { display: none; }
    section[data-testid="stSidebar"] { display: none; width: 0; }
</style>
''', unsafe_allow_html=True)
""",

    "pages/customer_home.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_trip_details, calculate_readiness

inject_custom_css()
render_top_nav(is_staff=False)

st.markdown('''
<div style="background: linear-gradient(to right, #002B5B, #0056b3); padding: 40px; border-radius: 12px; color: white; margin-bottom: 20px;">
    <h1 style="margin:0; font-size: 2.5rem;">Good Morning,<br>Amit Mehta</h1>
    <p style="margin-top:10px; font-size: 1.1rem; opacity: 0.9;">Your journeys, our support - always with you.</p>
</div>
''', unsafe_allow_html=True)

st.subheader("My Trips")

# Get trip
trip = get_trip_details('KT-T-0001')
if trip:
    _, comp, att, miss, pct, _ = calculate_readiness(trip['id'])
    
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        st.markdown(f'<div class="card" style="height:100%; text-align:center; background:#f8f9fa;">🏰<br>Dubai</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'''
        <div style="padding: 10px 0;">
            <div style="display:flex; align-items:center; gap: 10px;">
                <h3 style="margin:0;">{trip['name']}</h3>
                {render_badge('Upcoming')}
            </div>
            <p style="color:#666; margin: 5px 0;">📅 {trip['start_date']} - {trip['end_date']}</p>
            <p style="color:#666; margin: 0;">📍 {trip['destination']}</p>
            <p style="color:#666; margin: 5px 0;">👥 1 Traveller (Amit)</p>
        </div>
        ''', unsafe_allow_html=True)
    with col3:
        st.markdown(f'''
        <div style="text-align:center; padding: 20px 0;">
            <h2 style="margin:0; color: #1a73e8;">{pct}%</h2>
            <p style="font-size:0.8rem; color:#666;">Travel Readiness</p>
        </div>
        ''', unsafe_allow_html=True)
        if st.button("Open", key="open_trip", use_container_width=True):
            st.query_params.page = "customer_trip"
            st.rerun()
""",

    "pages/customer_trip.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_trip_details, get_requirements, calculate_readiness

inject_custom_css()
render_top_nav(is_staff=False)

if st.button("← Back to My Trips", key="back"):
    st.query_params.page = "customer_home"
    st.rerun()

trip = get_trip_details('KT-T-0001')
reqs = get_requirements('KT-T-0001')
_, comp, att, miss, pct, _ = calculate_readiness('KT-T-0001')

st.markdown(f'''
<div style="display: flex; gap: 20px; margin-bottom: 20px;">
    <div style="flex: 2; background: linear-gradient(to right, #0056b3, #007bff); padding: 30px; border-radius: 12px; color: white;">
        <h1 style="margin:0;">{trip['name']}</h1>
        <p style="margin: 10px 0 0 0;">📅 {trip['start_date']} - {trip['end_date']} | 📍 {trip['destination']}</p>
    </div>
    <div style="flex: 1; background: white; border: 1px solid #e0e0e0; padding: 20px; border-radius: 12px; display:flex; align-items:center; justify-content:space-between;">
        <div>
            <h4 style="margin:0;">Travel Readiness</h4>
            <p style="margin:5px 0; font-size:0.9rem;">✅ {comp} Complete</p>
            <p style="margin:5px 0; font-size:0.9rem; color:#f29900;">⚠️ {att} Need Attention</p>
            <p style="margin:5px 0; font-size:0.9rem; color:#d93025;">❌ {miss} Missing</p>
        </div>
        <h1 style="margin:0; color:#1a73e8;">{pct}%</h1>
    </div>
</div>
''', unsafe_allow_html=True)

tabs = st.tabs(["Document Checklist", "Trip Itinerary", "Traveller", "Trip Details", "Notes"])

with tabs[0]:
    st.markdown("### TRAVELLER DOCUMENTS")
    st.markdown("<div style='background:#f8f9fa; padding:15px; border-radius:8px; margin-bottom:15px;'><strong>AMIT MEHTA</strong><br><small>Lead Traveller</small></div>", unsafe_allow_html=True)
    
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
                        st.query_params.page = "smart_upload"
                        st.rerun()
                else:
                    if st.button("View", key=f"view_{r['id']}"):
                        pass
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
                        st.query_params.page = "smart_upload"
                        st.rerun()
                else:
                    if st.button("View", key=f"view_{r['id']}"):
                        pass
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
""",

    "pages/smart_upload.py": """import streamlit as st
import time
from ui_helpers import inject_custom_css, render_top_nav
from document_processor import process_document
from services import save_document
import os

inject_custom_css()
render_top_nav(is_staff=False)

req_id = st.session_state.get('upload_req_id', 'REQ-TR-01')

st.title("Smart Upload")
st.markdown("<p style='color:#666;'>Just upload your document and we'll do the rest.</p>", unsafe_allow_html=True)

col1, col2 = st.columns([2, 1])

with col2:
    st.markdown('''
    <div class="card" style="background: #f8f9fa;">
        <h4>How it works</h4>
        <ol style="padding-left:20px;">
            <li style="margin-bottom:10px;"><b>Upload your document</b><br><small>Drag & drop or select a file</small></li>
            <li style="margin-bottom:10px;"><b>We detect the document type</b><br><small>Using our smart system</small></li>
            <li style="margin-bottom:10px;"><b>Review the extracted information</b><br><small>Confirm or edit if needed</small></li>
            <li><b>Document is saved to your trip</b><br><small>Automatically linked and organized</small></li>
        </ol>
    </div>
    ''', unsafe_allow_html=True)

with col1:
    if 'upload_step' not in st.session_state:
        st.session_state['upload_step'] = 1

    if st.session_state['upload_step'] == 1:
        uploaded_file = st.file_uploader("Drag & drop your document here", type=['pdf', 'jpg', 'png'])
        # Provide a demo button to simulate file upload
        if st.button("Simulate Upload Demo Passport"):
            st.session_state['uploaded_filename'] = "demo_passport.pdf"
            st.session_state['upload_step'] = 2
            st.rerun()
            
        if uploaded_file is not None:
            st.session_state['uploaded_filename'] = uploaded_file.name
            # Save file somewhere if needed
            st.session_state['upload_step'] = 2
            st.rerun()

    elif st.session_state['upload_step'] == 2:
        st.write("Processing your document...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Simulate processing steps
        steps = [
            "Reading your document...",
            "✓ Checking file",
            "✓ Detecting document type",
            "→ Extracting information",
            "→ Matching traveller",
            "→ Matching trip",
            "→ Checking quality"
        ]
        
        for i, step in enumerate(steps):
            status_text.text(step)
            progress_bar.progress((i + 1) * 14)
            time.sleep(0.5)
            
        # Process using demo OCR
        result = process_document(st.session_state['uploaded_filename'], {})
        st.session_state['extracted_result'] = result
        st.session_state['upload_step'] = 3
        st.rerun()

    elif st.session_state['upload_step'] == 3:
        result = st.session_state['extracted_result']
        st.success(f"{result['document_type']} Detected ✓")
        
        st.write("### Review Extracted Information")
        fields = result['extracted_fields']
        
        # Display editable fields
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
            st.query_params.page = "customer_trip"
            st.rerun()
            
        if col_s.button("Confirm & Save Document"):
            # Save Document
            fake_path = os.path.join("documents", st.session_state['uploaded_filename'])
            save_document(req_id, fake_path, updated_fields)
            st.session_state['upload_step'] = 4
            st.rerun()

    elif st.session_state['upload_step'] == 4:
        st.success("Document successfully added ✓")
        st.info("Travel Readiness updated.")
        if st.button("Return to Trip"):
            st.session_state['upload_step'] = 1
            st.query_params.page = "customer_trip"
            st.rerun()
""",

    "pages/staff_review.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
from services import get_all_documents_for_review, verify_document
import json

inject_custom_css()
render_top_nav(is_staff=True)

st.title("Action Center")

st.markdown('''
<div style="display:flex; gap: 20px; margin-bottom: 30px;">
    <div class="card" style="flex:1; border-top: 4px solid #d93025;">
        <h2 style="margin:0; color:#d93025;">1</h2>
        <p style="margin:0;">Need Review</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #f29900;">
        <h2 style="margin:0; color:#f29900;">0</h2>
        <p style="margin:0;">Expiring Soon</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #1a73e8;">
        <h2 style="margin:0; color:#1a73e8;">0</h2>
        <p style="margin:0;">Re-upload Required</p>
    </div>
    <div class="card" style="flex:1; border-top: 4px solid #1e8e3e;">
        <h2 style="margin:0; color:#1e8e3e;">0</h2>
        <p style="margin:0;">Verified Today</p>
    </div>
</div>
''', unsafe_allow_html=True)

docs = get_all_documents_for_review()

if not docs:
    st.info("No documents currently need review.")
else:
    for d in docs:
        with st.container():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 2, 2])
            c1.write(f"**{d['customer_name']}**<br><small>{d['trip_name']}</small>", unsafe_allow_html=True)
            c2.write(f"**{d['req_name']}**")
            c3.write(f"{d['traveller_name'] or '-'}")
            c4.markdown(render_badge(d['status']), unsafe_allow_html=True)
            c5.write(d['uploaded_at'][:10])
            if c6.button("Review", key=f"rev_{d['id']}"):
                st.session_state['review_doc'] = d
                st.rerun()
            st.markdown("<hr>", unsafe_allow_html=True)

if 'review_doc' in st.session_state:
    st.markdown("---")
    st.subheader("Document Review")
    d = st.session_state['review_doc']
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"<div class='card' style='height:400px; display:flex; align-items:center; justify-content:center; background:#f1f3f4;'>[Document Preview: {d['file_path']}]</div>", unsafe_allow_html=True)
    with col2:
        st.write("### Extracted Information")
        data = json.loads(d['extracted_data'])
        for k, v in data.items():
            st.text_input(k, value=v, key=f"edit_{k}")
            
        c1, c2, c3 = st.columns(3)
        if c1.button("Verify Document", type="primary"):
            verify_document(d['id'])
            del st.session_state['review_doc']
            st.rerun()
        if c2.button("Reject"):
            st.warning("Rejected (Demo)")
        if c3.button("Request Re-upload"):
            st.warning("Requested Re-upload (Demo)")
""",

    "pages/customer_profile.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav
import database

inject_custom_css()
render_top_nav(is_staff=False)

st.title("Profile: Amit Mehta")
st.write("### Verified Travel Information")

conn = database.get_connection()
profile = conn.execute("SELECT * FROM user_profile WHERE customer_id = 'KT-C-0001'").fetchone()
conn.close()

if profile:
    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Full Name", value=profile['full_name'], disabled=True)
        st.text_input("Date of Birth", value=profile['dob'], disabled=True)
        st.text_input("Nationality", value=profile['nationality'], disabled=True)
    with c2:
        st.text_input("Passport Number", value=profile['passport_number'], disabled=True)
        st.text_input("Passport Expiry", value=profile['passport_expiry'], disabled=True)
else:
    st.info("No verified travel information available yet. Please upload and verify your passport.")
""",

    "pages/customer_documents.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav, render_badge
import database

inject_custom_css()
render_top_nav(is_staff=False)

st.title("My Documents")

conn = database.get_connection()
docs = conn.execute('''
    SELECT d.*, r.name as req_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    WHERE t.customer_id = 'KT-C-0001'
''').fetchall()
conn.close()

if not docs:
    st.info("You haven't uploaded any documents yet.")
else:
    for d in docs:
        with st.container():
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.markdown("📄")
            c2.markdown(f"**{d['req_name']}**<br>{render_badge(d['status'])}", unsafe_allow_html=True)
            c3.button("View", key=f"view_{d['id']}")
            st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
""",

    "rules.py": """# Contains logic for document validity
def check_passport_validity(expiry_date_str, trip_end_date_str):
    # Demo logic
    return True
""",

    "pages/staff_home.py": """import streamlit as st
from ui_helpers import inject_custom_css, render_top_nav
inject_custom_css()
render_top_nav(is_staff=True)
st.title("Staff Dashboard")
st.write("Welcome, Staff Admin")
""",
    "pages/staff_customers.py": "",
    "pages/staff_trips.py": "",
}

for filepath, content in files.items():
    full_path = os.path.join(BASE_DIR, filepath)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

print("All files generated successfully.")
