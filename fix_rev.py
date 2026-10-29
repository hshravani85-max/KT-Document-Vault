with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_rev = '''    docs = conn.execute(\'\'\'
        SELECT d.*, r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id, t.name as traveller_name, tr.name as trip_name, tr.customer_id, c.name as customer_name
        FROM documents d
        JOIN requirements r ON d.requirement_id = r.id
        LEFT JOIN travellers t ON r.traveller_id = t.id
        JOIN trips tr ON r.trip_id = tr.id
        JOIN customers c ON tr.customer_id = c.id
        WHERE d.status = 'Under Review'
    \'\'\').fetchall()'''

new_rev = '''    docs = conn.execute(\'\'\'
        SELECT d.*, r.name as req_name, r.type as req_type, r.trip_id, r.traveller_id, 
               t.name as traveller_name, tr.name as trip_name, 
               COALESCE(tr.customer_id, t.customer_id) as customer_id, 
               COALESCE(c.name, c2.name) as customer_name
        FROM documents d
        JOIN requirements r ON d.requirement_id = r.id
        LEFT JOIN travellers t ON r.traveller_id = t.id
        LEFT JOIN trips tr ON r.trip_id = tr.id
        LEFT JOIN customers c ON tr.customer_id = c.id
        LEFT JOIN customers c2 ON t.customer_id = c2.id
        WHERE d.status = 'Under Review'
    \'\'\').fetchall()'''

content = content.replace(old_rev, new_rev)

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)
