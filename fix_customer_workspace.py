import re

with open('pages/customer_workspace.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_display = """    if not travs:
        st.info("No travellers yet. Please add a traveller.")
    else:
        for t in travs:
            role = t['role'] if 'role' in t.keys() else 'Standard'
            st.write(f"- **{t['name']}** ({t['type']} - {role})")"""

new_display = """    if not travs:
        st.info("No travellers yet. Please add a traveller.")
    else:
        for t in travs:
            t_dict = dict(t)
            role = t_dict.get('role', 'Standard')
            passport = t_dict.get('passport_number') or 'Not provided'
            nat = t_dict.get('nationality') or 'Not provided'
            dob = t_dict.get('dob') or 'Not provided'
            st.markdown(f'''
            <div class="card" style="margin-bottom:15px; padding: 15px;">
                <h4 style="margin:0 0 5px 0;">{t_dict['name']}</h4>
                <p style="margin:0; color:#555;">Type: {t_dict.get('type', 'Unknown')} - {role} | Passport: {passport} | DOB: {dob} | Nationality: {nat}</p>
            </div>
            ''', unsafe_allow_html=True)"""

content = content.replace(old_display, new_display)

with open('pages/customer_workspace.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated customer_workspace.py")
