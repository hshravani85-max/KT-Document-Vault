import re

with open('pages/customer_workspace.py', 'r', encoding='utf-8') as f:
    cw = f.read()

cw = cw.replace("tr_name.strip(, st.session_state.get('session_token')), tr_dest.strip(), start_str, end_str, tr_type, tr_srv, tr_dept, selected_travs)", 
                "tr_name.strip(), tr_dest.strip(), start_str, end_str, tr_type, tr_srv, tr_dept, selected_travs, st.session_state.get('session_token'))")

# Also let's check `pages/smart_intake.py` to see if `create_trip` replacement is mangled similarly
with open('pages/customer_workspace.py', 'w', encoding='utf-8') as f:
    f.write(cw)
print("customer_workspace.py syntax fixed.")
