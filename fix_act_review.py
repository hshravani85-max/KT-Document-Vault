with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

def replace_block(old, new):
    global content
    content = content.replace(old, new)

# In reject
replace_block(
'''            req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} rejected", datetime.now().isoformat()))''',
'''            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} rejected", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} rejected", datetime.now().isoformat()))'''
)

# In re-upload
replace_block(
'''            req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} re-upload requested", datetime.now().isoformat()))''',
'''            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Document {d['id']} re-upload requested", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Document {d['id']} re-upload requested", datetime.now().isoformat()))'''
)

# In notes
replace_block(
'''            req = conn.execute("SELECT trip_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Note added to {d['id']}: {note_str}", datetime.now().isoformat()))''',
'''            req = conn.execute("SELECT trip_id, traveller_id FROM requirements WHERE id=?", (d['requirement_id'],)).fetchone()
            from datetime import datetime
            if req['trip_id']:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (req['trip_id'], f"Note added to {d['id']}: {note_str}", datetime.now().isoformat()))
            elif req['traveller_id']:
                cust_id = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (req['traveller_id'],)).fetchone()['customer_id']
                conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (cust_id, f"Note added to {d['id']}: {note_str}", datetime.now().isoformat()))'''
)

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
