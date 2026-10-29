import sqlite3
import os

conn = sqlite3.connect('C:/KT_Vault_V3/data/kt_vault_v3.db')
conn.row_factory = sqlite3.Row
docs = conn.execute('''
    SELECT d.id, d.file_path, r.name 
    FROM documents d
    JOIN requirements r ON d.requirement_id = r.id
    WHERE r.trip_id = 'KT-T-0001'
''').fetchall()

for d in docs:
    exists = os.path.exists(d['file_path'])
    print(f"{d['name']}: {d['file_path']} - Exists: {exists}")
