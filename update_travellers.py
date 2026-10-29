import sqlite3
import json

conn = sqlite3.connect('data/kt_vault_v3.db')
cursor = conn.execute('SELECT id FROM travellers')
travellers = cursor.fetchall()

for (tr_id,) in travellers:
    doc_cursor = conn.execute('''
        SELECT d.extracted_data 
        FROM documents d 
        JOIN requirements r ON d.requirement_id = r.id 
        WHERE r.traveller_id = ? AND r.type = 'TRAVELLER_VAULT' AND d.extracted_data IS NOT NULL
        ORDER BY d.uploaded_at DESC LIMIT 1
    ''', (tr_id,))
    doc = doc_cursor.fetchone()
    
    if not doc:
        # Check regular TRAVELLER documents if no VAULT document
        doc_cursor = conn.execute('''
            SELECT d.extracted_data 
            FROM documents d 
            JOIN requirements r ON d.requirement_id = r.id 
            WHERE r.traveller_id = ? AND r.name = 'Passport' AND d.extracted_data IS NOT NULL
            ORDER BY d.uploaded_at DESC LIMIT 1
        ''', (tr_id,))
        doc = doc_cursor.fetchone()
        
    if doc:
        try:
            data = json.loads(doc[0])
            passport = data.get('Passport Number')
            nat = data.get('Nationality')
            dob = data.get('Date of Birth')
            
            updates = []
            params = []
            if passport:
                updates.append('passport_number = ?')
                params.append(passport)
            if nat:
                updates.append('nationality = ?')
                params.append(nat)
            if dob:
                updates.append('dob = ?')
                params.append(dob)
                
            if updates:
                params.append(tr_id)
                query = "UPDATE travellers SET " + ", ".join(updates) + " WHERE id = ?"
                conn.execute(query, tuple(params))
                print(f"Updated {tr_id}: {updates} -> {params}")
        except Exception as e:
            print(f"Error updating {tr_id}: {e}")

conn.commit()
conn.close()
