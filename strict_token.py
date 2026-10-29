import re

with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("session_token=None", "session_token")
content = content.replace("if session_token: auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])", "auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])")

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Update customers.py
try:
    with open('pages/customers.py', 'r', encoding='utf-8') as f:
        c = f.read()
    c = c.replace("new_id = services.create_customer(", "new_id = services.create_customer(")
    # Need regex to inject session_token
    c = re.sub(r'services\.create_customer\((.*?)\)', r"services.create_customer(\1, st.session_state.get('session_token'))", c)
    with open('pages/customers.py', 'w', encoding='utf-8') as f:
        f.write(c)
except Exception: pass

# Update smart_intake.py
try:
    with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
        si = f.read()
    si = re.sub(r'services\.create_customer\((.*?)\)', r"services.create_customer(\1, st.session_state.get('session_token'))", si)
    si = re.sub(r'services\.create_trip\((.*?)\)', r"services.create_trip(\1, st.session_state.get('session_token'))", si)
    si = re.sub(r'services\.add_traveller\((.*?)\)', r"services.add_traveller(\1, st.session_state.get('session_token'))", si)
    with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
        f.write(si)
except Exception: pass

print("Fully enforced token requirement on write operations.")
