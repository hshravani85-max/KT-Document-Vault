import streamlit as st
import os
import time
import json
import logging
import auth_services
import ui_helpers

st.set_page_config(
    page_title="Khanna Travels Vault",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

from database import init_db
init_db()

import storage_service

# Initialize and verify document encryption key provider (Windows DPAPI)
try:
    _key_prov = storage_service.init_default_key_provider()
    if _key_prov.has_key("ktv_2026_v1"):
        logging.info("Document encryption key provider initialized with 'ktv_2026_v1'.")
    else:
        logging.warning("Document encryption key 'ktv_2026_v1' not found in key provider.")
except Exception as _e:
    logging.error(f"Failed to initialize document encryption key provider: {_e}")
if storage_service.is_maintenance_mode():
    st.error("### 🔒 System Under Maintenance\n\nKT Vault V3 is currently undergoing planned database and document encryption maintenance.\n\nAll user sessions, uploads, document modifications, PDF generation, and OCR processing are temporarily suspended.\n\nPlease check back shortly or contact the System Administrator.")
    st.stop()

# Non-sensitive navigation audit log (SEC-CRIT-01 hardened: strict allowlist, zero tokens or query params)
try:
    ALLOWED_LOG_PAGES = {
        "staff_home", "customers", "customer_workspace", "trips", 
        "trip_workspace", "documents", "document_review", 
        "smart_upload", "vault_search", "smart_intake", "login"
    }
    raw_page = str(st.session_state.get('nav_page', ''))
    if not raw_page:
        raw_page = str(st.query_params.get("page", "staff_home"))
    safe_page_id = raw_page if raw_page in ALLOWED_LOG_PAGES else "other"
    
    safe_log_entry = {
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "event": "navigation",
        "page": safe_page_id,
        "authenticated": bool(st.session_state.get('session_token'))
    }
    with open('nav_trace.log', 'a', encoding='utf-8') as f:
        f.write(json.dumps(safe_log_entry) + "\n")
except Exception:
    pass

# Initialize internal routing state from URL if missing
if 'nav_page' not in st.session_state:
    st.session_state['nav_page'] = st.query_params.get("page", "staff_home")

page = st.session_state['nav_page']

def load_page(page_name):
    page_path = os.path.join(os.path.dirname(__file__), 'pages', f"{page_name}.py")
    if os.path.exists(page_path):
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            page_globals = {"__name__": "__main__", "st": st, "os": os, "__file__": page_path}
            exec(code, page_globals)
    else:
        st.error(f"Page {page_name} not found.")

valid_pages = [
    "staff_home", "customers", "customer_workspace", "trips", 
    "trip_workspace", "documents", "document_review", 
    "smart_upload", "vault_search", "smart_intake"
]

logging.basicConfig(level=logging.INFO)
token = st.session_state.get('session_token')
active_user = auth_services.get_user_by_token(token) if token else None

# Hide Streamlit default auto-file-nav
st.markdown('''
<style>
    [data-testid="stSidebarNav"] { display: none !important; }
</style>
''', unsafe_allow_html=True)

if not active_user:
    st.session_state.pop('session_token', None)
    # Hide sidebar completely on login page
    st.markdown('''
    <style>
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebar"] { display: none !important; width: 0 !important; }
    </style>
    ''', unsafe_allow_html=True)
    load_page('login')
else:
    st.session_state['user_full_name'] = active_user['full_name']
    st.session_state['user_role'] = active_user['role']
    ui_helpers.inject_custom_css()
    ui_helpers.render_sidebar(active_user, page)
    
    if page in valid_pages:
        load_page(page)
    else:
        load_page("staff_home")
