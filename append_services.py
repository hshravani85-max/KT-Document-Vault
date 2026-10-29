with open('services.py', 'a', encoding='utf-8') as f:
    f.write("""
def generate_next_id(conn, table, prefix):
    prefix_len = len(prefix) + 1
    cursor = conn.cursor()
    query = f"SELECT MAX(CAST(SUBSTR(id, ?) AS INTEGER)) FROM {table} WHERE id LIKE ?"
    cursor.execute(query, (prefix_len, f"{prefix}%"))
    result = cursor.fetchone()[0]
    next_num = 1 if result is None else result + 1
    return f"{prefix}{next_num:04d}"

def create_customer(name, mobile, email, type):
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
        ''', (new_id, f"Customer created: {name}"))
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def add_traveller(customer_id, name, dob, type, relationship, is_lead):
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
        ''', (customer_id, f"Traveller added: {name}"))
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()

def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids):
    conn = database.get_connection()
    try:
        import uuid
        new_id = generate_next_id(conn, 'trips', 'KT-T-')
        
        conn.execute('''
            INSERT INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NOT READY')
        ''', (new_id, customer_id, name, destination, start_date, end_date, trip_type, service, department))
        
        for tr_id in traveller_ids:
            conn.execute("INSERT INTO trip_travellers (trip_id, traveller_id) VALUES (?, ?)", (new_id, tr_id))
            
            conn.execute('''
                INSERT INTO requirements (id, trip_id, traveller_id, name, type) 
                VALUES (?, ?, ?, ?, 'TRAVELLER')
            ''', (f"REQ-TR-{uuid.uuid4().hex[:6]}", new_id, tr_id, "Passport"))
            
            conn.execute('''
                INSERT INTO requirements (id, trip_id, traveller_id, name, type) 
                VALUES (?, ?, ?, ?, 'TRAVELLER')
            ''', (f"REQ-TR-{uuid.uuid4().hex[:6]}", new_id, tr_id, "Visa / Entry Document"))
            
        trip_reqs = [
            'Flight Ticket', 'Hotel Voucher', 'Travel Insurance', 
            'Transfer Voucher', 'Sightseeing Voucher', 'Arrival / Entry Document', 'Itinerary'
        ]
        for tr in trip_reqs:
            conn.execute('''
                INSERT INTO requirements (id, trip_id, traveller_id, name, type)
                VALUES (?, ?, NULL, ?, 'TRIP')
            ''', (f"REQ-T-{uuid.uuid4().hex[:6]}", new_id, tr))
            
        conn.execute('''
            INSERT INTO activity (trip_id, description, timestamp)
            VALUES (?, ?, datetime('now'))
        ''', (new_id, f"Trip created: {name}"))
        
        conn.commit()
        return new_id
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        raise e
    finally:
        conn.close()
""")
