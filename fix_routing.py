import re

# 1. Patch app.py to use session state for routing
with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Remove my earlier tracer block
text = re.sub(r"import time\nimport json.*?Session State: \{json\.dumps\(safe_state\)}\\n\"\n", "", text, flags=re.DOTALL)
text = re.sub(r"init_db\(\)\n+", "init_db()\n\n", text)
text = re.sub(r"if not active_user:.*?st\.stop\(\)\n", "if not active_user:\n    st.session_state.pop('session_token', None)\n    load_page('login')\n", text, flags=re.DOTALL)

# Add session-state-based routing
routing_logic = """
# Initialize internal routing state from URL if missing
if 'nav_page' not in st.session_state:
    st.session_state['nav_page'] = st.query_params.get("page", "staff_home")

page = st.session_state['nav_page']
"""
text = re.sub(r"query_params = st\.query_params\npage = query_params\.get\(\"page\", \"staff_home\"\)", routing_logic, text)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

# 2. Patch ui_helpers.py to use session state
with open('ui_helpers.py', 'r', encoding='utf-8') as f:
    ui_text = f.read()

ui_text = ui_text.replace('st.query_params.page = "staff_home"', 'st.session_state["nav_page"] = "staff_home"\n            st.query_params.page = "staff_home"')
ui_text = ui_text.replace('st.query_params.page = "customers"', 'st.session_state["nav_page"] = "customers"\n            st.query_params.page = "customers"')
ui_text = ui_text.replace('st.query_params.page = "trips"', 'st.session_state["nav_page"] = "trips"\n            st.query_params.page = "trips"')
ui_text = ui_text.replace('st.query_params.page = "documents"', 'st.session_state["nav_page"] = "documents"\n            st.query_params.page = "documents"')
ui_text = ui_text.replace('st.query_params.page = "vault_search"', 'st.session_state["nav_page"] = "vault_search"\n            st.query_params.page = "vault_search"')

with open('ui_helpers.py', 'w', encoding='utf-8') as f:
    f.write(ui_text)

# 3. Patch login.py to use session state
with open('pages/login.py', 'r', encoding='utf-8') as f:
    login_text = f.read()

login_text = login_text.replace('st.query_params.page = "staff_home"', 'st.session_state["nav_page"] = "staff_home"\n                    st.query_params.page = "staff_home"')

with open('pages/login.py', 'w', encoding='utf-8') as f:
    f.write(login_text)

print("Navigation decoupled from query params.")
