with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_v = '''            # Add activity
            conn = database.get_connection()
            req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} verified", datetime.now().isoformat()))
            conn.commit()'''

new_v = '''            # Add activity
            conn = database.get_connection()
            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} verified", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} verified", datetime.now().isoformat()))
            conn.commit()'''

content = content.replace(old_v, new_v)
with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
