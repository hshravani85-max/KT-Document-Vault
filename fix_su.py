with open('pages/smart_upload.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

old_process = """        result = process_document(st.session_state['uploaded_filename'], {})"""

new_process = """        file_path = os.path.join("documents", st.session_state['uploaded_filename'])
        try:
            with open(file_path, 'rb') as fp:
                file_bytes = fp.read()
        except:
            file_bytes = b''
        result = process_document(st.session_state['uploaded_filename'], file_bytes)"""

if old_process in content:
    content = content.replace(old_process, new_process)
    with open('pages/smart_upload.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed smart_upload.py process_document call")
else:
    print("old_process not found")
