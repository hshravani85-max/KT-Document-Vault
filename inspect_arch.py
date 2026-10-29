import sqlite3

conn = sqlite3.connect('data/kt_vault_v3.db')
with open('db_schema.txt', 'w') as f:
    f.write('--- TABLES ---\\n')
    for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
        f.write(f"{row[0]}\\n{row[1]}\\n{'-'*20}\\n")
conn.close()

with open('services.py', 'r') as f:
    services = f.read()
    
with open('pages/document_review.py', 'r') as f:
    doc_review = f.read()

import re
print("Readiness Function:")
print(re.search(r'def calculate_readiness.*?return \([^)]*\)', services, re.DOTALL).group(0))

print("Verify Function:")
print(re.search(r'def verify_document.*?(?=\\ndef|\Z)', services, re.DOTALL).group(0))
