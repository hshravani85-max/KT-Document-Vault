import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add authentication wrapping
auth_wrapper = """
import auth_services
token = st.session_state.get('session_token')
active_user = auth_services.get_user_by_token(token) if token else None

if not active_user:
    st.session_state.pop('session_token', None)
    load_page("login")
else:
    st.session_state['user_full_name'] = active_user['full_name']
    st.session_state['user_role'] = active_user['role']
    if page in valid_pages:
        load_page(page)
    else:
        load_page("staff_home")
"""

old_routing = """if page in valid_pages:
    load_page(page)
else:
    load_page("staff_home")"""

content = content.replace(old_routing, auth_wrapper)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("app.py wrapped with authentication.")
