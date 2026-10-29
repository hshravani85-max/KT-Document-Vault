with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

old_add = """def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'travellers', 'KT-TR-')
        conn.execute('''
            INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, customer_id, full_name, dob, traveller_type, relationship, 'Lead Traveller' if lead_traveller else 'Standard'))"""

new_add = """def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'travellers', 'KT-TR-')
        conn.execute('''
            INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role, passport_number, nationality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, customer_id, full_name, dob, traveller_type, relationship, 'Lead Traveller' if lead_traveller else 'Standard', passport_number, nationality))"""

if old_add in content:
    content = content.replace(old_add, new_add)
    with open('services.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed services.py")
else:
    print("Failed to replace in services.py")
