import re

with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Make sure we can import auth_services
if "import auth_services" not in content:
    content = "import auth_services\n" + content

# Replace verify_document
old_verify = """def verify_document(doc_id, actor="Staff Member (Demo)"):
    import json
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT status, extracted_data, requirement_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc: raise ValueError("Document not found.")
        if doc['status'] == 'Verified': return"""

new_verify = """def verify_document(doc_id, session_token):
    import json
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']
    
    conn = database.get_connection()
    try:
        doc = conn.execute("SELECT status, extracted_data, requirement_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not doc: raise ValueError("Document not found.")
        if doc['status'] == 'Verified': return"""

content = content.replace(old_verify, new_verify)

# Replace reopen_document
old_reopen = """def reopen_document(doc_id, reason, actor):
    if not reason or not reason.strip():
        raise ValueError("Correction reason is required.")
    if actor in [None, 'Staff Member (Demo)', '']:
        raise PermissionError("Unauthorized: Valid authenticated staff identity required with proper RBAC roles.")
        
    conn = database.get_connection()"""

new_reopen = """def reopen_document(doc_id, reason, session_token):
    if not reason or not reason.strip():
        raise ValueError("Correction reason is required.")
        
    user = auth_services.require_role(session_token, ['Supervisor', 'Admin'])
    actor = user['full_name']
        
    conn = database.get_connection()"""

content = content.replace(old_reopen, new_reopen)

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("services.py patched with authentication logic.")
