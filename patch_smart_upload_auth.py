import re

with open('pages/smart_upload.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_save = "save_document(req_id, safe_path, updated_fields)"
new_save = "save_document(req_id, safe_path, updated_fields, st.session_state.get('session_token'))"

content = content.replace(old_save, new_save)

with open('pages/smart_upload.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("smart_upload.py updated with auth token.")
