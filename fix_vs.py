with open('pages/vault_search.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_vsearch = '''    SELECT d.*, r.name as req_name, c.name as customer_name, t.name as trip_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    JOIN customers c ON t.customer_id = c.id
    WHERE 1=1'''

new_vsearch = '''    SELECT d.*, r.name as req_name, 
           COALESCE(c.name, c2.name) as customer_name, 
           t.name as trip_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    LEFT JOIN trips t ON r.trip_id = t.id
    LEFT JOIN customers c ON t.customer_id = c.id
    LEFT JOIN travellers tr ON r.traveller_id = tr.id
    LEFT JOIN customers c2 ON tr.customer_id = c2.id
    WHERE 1=1'''

content = content.replace(old_vsearch, new_vsearch)

old_name = '''if cust_query:
    query += " AND c.name LIKE ?"
    params.append(f"%{cust_query}%")'''

new_name = '''if cust_query:
    query += " AND (c.name LIKE ? OR c2.name LIKE ?)"
    params.extend([f"%{cust_query}%", f"%{cust_query}%"])'''

content = content.replace(old_name, new_name)

with open('pages/vault_search.py', 'w', encoding='utf-8') as f:
    f.write(content)
