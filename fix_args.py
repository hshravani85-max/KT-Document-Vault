with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_customer = """def create_customer(name, mobile, email, type):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'customers', 'KT-C-')
        conn.execute('''
            INSERT INTO customers (id, name, mobile, email, customer_type, status)
            VALUES (?, ?, ?, ?, ?, 'Active')
        ''', (new_id, name, mobile, email, type))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (new_id, f"Customer created: {name}"))"""

new_customer = """def create_customer(full_name, mobile=None, email=None, customer_type="Individual"):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'customers', 'KT-C-')
        conn.execute('''
            INSERT INTO customers (id, name, mobile, email, customer_type, status)
            VALUES (?, ?, ?, ?, ?, 'Active')
        ''', (new_id, full_name, mobile, email, customer_type))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (new_id, f"Customer created: {full_name}"))"""

content = content.replace(old_customer, new_customer)

old_traveller = """def add_traveller(customer_id, name, dob, type, relationship, is_lead):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'travellers', 'KT-TR-')
        conn.execute('''
            INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, customer_id, name, dob, type, relationship, 'Lead Traveller' if is_lead else 'Standard'))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (customer_id, f"Traveller added: {name}"))"""

new_traveller = """def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False):
    conn = database.get_connection()
    try:
        new_id = generate_next_id(conn, 'travellers', 'KT-TR-')
        conn.execute('''
            INSERT INTO travellers (id, customer_id, name, dob, type, relationship, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (new_id, customer_id, full_name, dob, traveller_type, relationship, 'Lead Traveller' if lead_traveller else 'Standard'))
        conn.execute('''
            INSERT INTO activity (customer_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (customer_id, f"Traveller added: {full_name}"))"""

content = content.replace(old_traveller, new_traveller)

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)
