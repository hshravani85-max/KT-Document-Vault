with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_query = """    veri_act = conn.execute('''
        SELECT * FROM activity
        WHERE trip_id = ? AND description LIKE ?
        ORDER BY timestamp DESC LIMIT 1
    ''', (d['trip_id'], f"%Document {d['id']} verified%")).fetchone()"""

new_query = """    if d['trip_id']:
        veri_act = conn.execute('''
            SELECT * FROM activity
            WHERE trip_id = ? AND description LIKE ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (d['trip_id'], f"%Document {d['id']} verified%")).fetchone()
    elif d['traveller_id']:
        cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (d['traveller_id'],)).fetchone()['customer_id']
        veri_act = conn.execute('''
            SELECT * FROM activity
            WHERE customer_id = ? AND description LIKE ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (cust_id, f"%Document {d['id']} verified%")).fetchone()"""

content = content.replace(old_query, new_query)

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
