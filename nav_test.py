import streamlit as st
import os
import auth_services
import sys

# Mock state
st.session_state['session_token'] = 'mock-admin-token'
st.session_state['user_full_name'] = 'Test Admin'
st.session_state['user_role'] = 'Admin'

valid_pages = [
    "staff_home", "customers", "customer_workspace", "trips", 
    "trip_workspace", "documents", "document_review", 
    "smart_upload", "vault_search", "smart_intake", "login"
]

results = {}

# We need to monkeypatch st.rerun to prevent the script from stopping
def mock_rerun():
    pass
st.rerun = mock_rerun
st.stop = mock_rerun

for page in valid_pages:
    print(f"Testing {page}...")
    try:
        if page == "customer_workspace":
            st.query_params.customer_id = "KT-C-0001"
        if page == "trip_workspace":
            st.query_params.trip_id = "KT-T-0001"
        if page == "document_review":
            st.query_params.doc_id = "DOC-4c9a4d78"
            
        page_path = os.path.join(os.path.dirname(__file__), 'pages', f"{page}.py")
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            page_globals = {"__name__": "__main__", "st": st, "os": os}
            exec(code, page_globals)
        results[page] = "PASS"
    except Exception as e:
        results[page] = f"FAIL: {str(e)}"
        print(f"Error in {page}: {e}")

print("\n--- Navigation Audit Matrix ---")
for p, res in results.items():
    print(f"{p}: {res}")
