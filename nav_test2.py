import streamlit as st
import os
import auth_services

st.session_state['session_token'] = 'mock-admin-token'
st.session_state['user_full_name'] = 'Test Admin'
st.session_state['user_role'] = 'Admin'

valid_pages = [
    "staff_home", "customers", "customer_workspace", "trips", 
    "trip_workspace", "documents", "document_review", 
    "smart_upload", "vault_search", "smart_intake", "login"
]

results = {}

class StopException(Exception): pass
class RerunException(Exception): pass

def mock_stop(): raise StopException()
def mock_rerun(): raise RerunException()
st.rerun = mock_rerun
st.stop = mock_stop

for page in valid_pages:
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
    except StopException:
        results[page] = "PASS (Stopped)"
    except RerunException:
        results[page] = "PASS (Rerun)"
    except Exception as e:
        results[page] = f"FAIL: {type(e).__name__} - {str(e)}"

print("\n--- Navigation Audit Matrix ---")
for p, res in results.items():
    print(f"{p}: {res}")
