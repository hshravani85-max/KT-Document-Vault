import streamlit as st
import os

st.set_page_config(page_title="Khanna Travels Vault", layout="wide")

from database import init_db
init_db()

import time
import json

with open('nav_trace.log', 'a') as f:
    f.write(f"\n--- {time.time()} ---\n")
    f.write(f"Query Params: {dict(st.query_params)}\n")
    
    # Dump session state safely
    safe_state = {}
    for k, v in st.session_state.items():
        if isinstance(v, (str, int, float, bool)):
            safe_state[k] = v
    f.write(f"Session State: {json.dumps(safe_state)}\n")



# Initialize internal routing state from URL if missing
if 'nav_page' not in st.session_state:
    st.session_state['nav_page'] = st.query_params.get("page", "staff_home")

page = st.session_state['nav_page']


def load_page(page_name):
    page_path = os.path.join(os.path.dirname(__file__), 'pages', f"{page_name}.py")
    if os.path.exists(page_path):
        with open(page_path, 'r', encoding='utf-8') as f:
            code = f.read()
            page_globals = {"__name__": "__main__", "st": st, "os": os}
            exec(code, page_globals)
    else:
        st.error(f"Page {page_name} not found.")

valid_pages = [
    "staff_home", "customers", "customer_workspace", "trips", 
    "trip_workspace", "documents", "document_review", 
    "smart_upload", "vault_search", "smart_intake"
]


import auth_services

import logging
logging.basicConfig(level=logging.INFO)
logging.info(f"--- APP RERUN ---")
logging.info(f"Session Keys: {list(st.session_state.keys())}")
logging.info(f"Query Params: {st.query_params.to_dict()}")

token = st.session_state.get('session_token')
logging.info(f"Token: {token}")

active_user = auth_services.get_user_by_token(token) if token else None
logging.info(f"Active User: {active_user}")

token = st.session_state.get('session_token')
active_user = auth_services.get_user_by_token(token) if token else None


if not active_user:
    st.session_state.pop('session_token', None)
    load_page('login')

else:
    st.session_state['user_full_name'] = active_user['full_name']
    st.session_state['user_role'] = active_user['role']
    if page in valid_pages:
        load_page(page)
    else:
        load_page("staff_home")


st.markdown('''
<style>
    [data-testid="collapsedControl"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    section[data-testid="stSidebar"] { display: none !important; width: 0 !important; }
</style>
''', unsafe_allow_html=True)
