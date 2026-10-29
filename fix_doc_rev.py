import re

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix the sqlite3.Row .get() issue
text = text.replace("veri_act.get('actor', 'Staff')", "veri_act['actor'] if 'actor' in veri_act.keys() else 'Staff'")
text = text.replace("veri_act.get('timestamp')", "veri_act['timestamp'] if 'timestamp' in veri_act.keys() else ''")

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("document_review.py sqlite3.Row get() bug fixed.")
