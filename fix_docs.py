with open('pages/documents.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_docs = '''    SELECT d.*, r.name as req_name, r.type as req_type, c.name as customer_name, t.name as trip_name, tr.name as traveller_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    JOIN trips t ON r.trip_id = t.id
    JOIN customers c ON t.customer_id = c.id
    LEFT JOIN travellers tr ON r.traveller_id = tr.id
    ORDER BY d.uploaded_at DESC'''

new_docs = '''    SELECT d.*, r.name as req_name, r.type as req_type, 
           COALESCE(c.name, c2.name) as customer_name, 
           t.name as trip_name, tr.name as traveller_name
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    LEFT JOIN trips t ON r.trip_id = t.id
    LEFT JOIN customers c ON t.customer_id = c.id
    LEFT JOIN travellers tr ON r.traveller_id = tr.id
    LEFT JOIN customers c2 ON tr.customer_id = c2.id
    ORDER BY d.uploaded_at DESC'''

content = content.replace(old_docs, new_docs)
with open('pages/documents.py', 'w', encoding='utf-8') as f:
    f.write(content)
