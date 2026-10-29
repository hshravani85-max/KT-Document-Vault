with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

old_match = """    # Matching logic
    conn = database.get_connection()
    matches = conn.execute("SELECT id, name, customer_type FROM customers WHERE name LIKE ?", (f"%{ext['Full Name']}%",)).fetchall()

    st.write(f"**Extracted Traveller Name**: {ext['Full Name']}")
    st.write(f"**Passport Number**: {ext.get('Passport Number', '')}")"""

new_match = """    # Matching logic
    conn = database.get_connection()
    
    # 1. By Passport Number (via travellers table)
    # 2. By Full Name + DOB (via travellers table)
    # 3. By Name (via customers table)
    matches_dict = {}
    
    pn = ext.get('Passport Number', '')
    if pn:
        # Match traveller by passport
        t_rows = conn.execute("SELECT c.id, c.name, c.customer_type FROM customers c JOIN travellers t ON c.id = t.customer_id WHERE t.passport_number = ?", (pn,)).fetchall()
        for r in t_rows: matches_dict[r['id']] = r
        
    dob = ext.get('Date of Birth', '')
    if dob and ext.get('Full Name'):
        t_rows = conn.execute("SELECT c.id, c.name, c.customer_type FROM customers c JOIN travellers t ON c.id = t.customer_id WHERE t.name LIKE ? AND t.dob = ?", (f"%{ext['Full Name']}%", dob)).fetchall()
        for r in t_rows: matches_dict[r['id']] = r
        
    if ext.get('Full Name'):
        c_rows = conn.execute("SELECT id, name, customer_type FROM customers WHERE name LIKE ?", (f"%{ext['Full Name']}%",)).fetchall()
        for r in c_rows: matches_dict[r['id']] = r
        
    matches = list(matches_dict.values())

    st.write(f"**Extracted Traveller Name**: {ext.get('Full Name', '')}")
    st.write(f"**Passport Number**: {ext.get('Passport Number', '')}")"""

content = content.replace(old_match, new_match)
with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(content)
