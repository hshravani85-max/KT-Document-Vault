import re

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace hardcoded 'Staff Member (Demo)' for reopen
content = content.replace(
    "services.reopen_document(doc_id, reason, 'Staff Member (Demo)')", 
    "services.reopen_document(doc_id, reason, st.session_state.get('session_token'))"
)

# Update verify_document call
content = content.replace(
    "verify_document(d['id'])", 
    "verify_document(d['id'], st.session_state.get('session_token'))"
)

# Remove the 'Verified by: Staff Member (Demo)' hardcoding from UI rendering
old_verified_html = "<p style=\"margin:0; color:#333;\"><strong>Verified by:</strong> Staff Member (Demo)</p>"
new_verified_html = f"<p style=\"margin:0; color:#333;\"><strong>Verified by:</strong> {{veri_act.get('actor', 'Staff')}}</p>"
# Wait, `veri_act` might not have `actor` if it's querying the `activity` table. But the history now comes from `document_history` which has `actor`.
# Let's just fix the template.
content = content.replace(old_verified_html, new_verified_html)

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_review.py updated for auth.")
