import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

debug_code = """
import logging
logging.basicConfig(level=logging.INFO)
logging.info(f"--- APP RERUN ---")
logging.info(f"Session Keys: {list(st.session_state.keys())}")
logging.info(f"Query Params: {st.query_params.to_dict()}")

token = st.session_state.get('session_token')
logging.info(f"Token: {token}")

active_user = auth_services.get_user_by_token(token) if token else None
logging.info(f"Active User: {active_user}")
"""

text = text.replace("import auth_services", "import auth_services\n" + debug_code)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Debug added to app.py")
