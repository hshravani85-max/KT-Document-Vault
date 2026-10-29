with open('pages/smart_upload.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

old_upload = """        if uploaded_file is not None:
            st.session_state['uploaded_filename'] = uploaded_file.name
            st.session_state['upload_step'] = 2
            st.rerun()"""

new_upload = """        import uuid
        if uploaded_file is not None:
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            safe_filename = f"trip_upload_{uuid.uuid4().hex}{ext}"
            safe_path = os.path.join("documents", safe_filename)
            with open(safe_path, "wb") as f_out:
                f_out.write(uploaded_file.getvalue())
                
            st.session_state['uploaded_filename'] = uploaded_file.name
            st.session_state['upload_safe_path'] = safe_path
            st.session_state['upload_step'] = 2
            st.rerun()"""
content = content.replace(old_upload, new_upload)

old_process = """        file_path = os.path.join("documents", st.session_state['uploaded_filename'])
        try:
            with open(file_path, 'rb') as fp:
                file_bytes = fp.read()
        except:
            file_bytes = b''
        result = process_document(st.session_state['uploaded_filename'], file_bytes)"""

new_process = """        file_path = st.session_state.get('upload_safe_path')
        try:
            with open(file_path, 'rb') as fp:
                file_bytes = fp.read()
        except:
            file_bytes = b''
        result = process_document(st.session_state['uploaded_filename'], file_bytes)"""
content = content.replace(old_process, new_process)

old_save = """        if col_s.button("Confirm & Save Document"):
            fake_path = os.path.join("documents", st.session_state['uploaded_filename'])
            save_document(req_id, fake_path, updated_fields)"""

new_save = """        if col_s.button("Confirm & Save Document"):
            safe_path = st.session_state.get('upload_safe_path')
            save_document(req_id, safe_path, updated_fields)"""
content = content.replace(old_save, new_save)

with open('pages/smart_upload.py', 'w', encoding='utf-8') as f:
    f.write(content)
