import re

with open('pages/customer_workspace.py', 'r', encoding='utf-8') as f:
    cw = f.read()

cw = re.sub(r'services\.add_traveller\((.*?)\)', r"services.add_traveller(\1, st.session_state.get('session_token'))", cw)
cw = re.sub(r'services\.create_trip\((.*?)\)', r"services.create_trip(\1, st.session_state.get('session_token'))", cw)

with open('pages/customer_workspace.py', 'w', encoding='utf-8') as f:
    f.write(cw)
print("customer_workspace.py strictly patched.")
