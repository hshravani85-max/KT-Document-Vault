import os
import re

with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update reset_intake to clean up temp file
old_reset = '''def reset_intake():
    for k in ['intake_step', 'intake_file_name', 'intake_extracted', 'intake_selected_customer', 'intake_match_found']:
        if k in st.session_state:
            del st.session_state[k]'''

new_reset = '''def reset_intake():
    # Cleanup temp file
    if 'intake_safe_path' in st.session_state:
        safe_path = st.session_state['intake_safe_path']
        if os.path.exists(safe_path):
            try: os.remove(safe_path)
            except: pass
    
    for k in ['intake_step', 'intake_file_name', 'intake_safe_path', 'intake_extracted', 'intake_warnings', 'intake_confidence', 'intake_doc_type', 'intake_selected_customer', 'intake_match_found']:
        if k in st.session_state:
            del st.session_state[k]'''
content = content.replace(old_reset, new_reset)

# 2. Update step 1 file upload logic
old_step1 = '''    if st.button("Upload & Extract", type="primary", disabled=not uploaded_file):
        import document_processor
        st.session_state['intake_file_name'] = uploaded_file.name
        
        import os
        file_path = os.path.join("documents", uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getvalue())
            
        result = document_processor.process_document(uploaded_file.name, uploaded_file.getvalue())
        
        st.session_state['intake_extracted'] = result['extracted_fields']
        st.session_state['intake_warnings'] = result['warnings']
        st.session_state['intake_step'] = 2
        st.rerun()'''

new_step1 = '''    if st.button("Upload & Extract", type="primary", disabled=not uploaded_file):
        import document_processor
        import uuid
        import os
        
        st.session_state['intake_file_name'] = uploaded_file.name
        
        # Secure filename
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        safe_filename = f"intake_{uuid.uuid4().hex}{ext}"
        safe_path = os.path.join("documents", safe_filename)
        
        with open(safe_path, "wb") as f:
            f.write(uploaded_file.getvalue())
            
        st.session_state['intake_safe_path'] = safe_path
            
        result = document_processor.process_document(uploaded_file.name, uploaded_file.getvalue())
        
        st.session_state['intake_extracted'] = result.get('extracted_fields', {})
        st.session_state['intake_warnings'] = result.get('warnings', [])
        st.session_state['intake_confidence'] = result.get('confidence', {})
        st.session_state['intake_doc_type'] = result.get('document_type', 'Needs Review')
        
        st.session_state['intake_step'] = 2
        st.rerun()'''
content = content.replace(old_step1, new_step1)

# 3. Update step 2 UI
old_step2 = '''elif step == 2:
    st.markdown("### Step 2: Confirm Details")
    st.success(f"**DOCUMENT DETECTED**: Passport")
    
    if st.session_state.get('intake_warnings'):
        for w in st.session_state['intake_warnings']:
            st.warning(w)
            
    st.markdown("Please confirm the extracted information before saving.")
    
    ext = st.session_state['intake_extracted']
    
    with st.form("confirm_details_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name", value=ext.get("Full Name", ""))
            dob = st.text_input("Date of Birth", value=ext.get("Date of Birth", ""))
            nationality = st.text_input("Nationality", value=ext.get("Nationality", ""))
        with col2:
            pass_num = st.text_input("Passport Number", value=ext.get("Passport Number", ""))
            issue = st.text_input("Issue Date", value=ext.get("Issue Date", ""))
            expiry = st.text_input("Expiry Date", value=ext.get("Expiry Date", ""))
            place = st.text_input("Place of Issue", value=ext.get("Place of Issue", ""))'''

new_step2 = '''elif step == 2:
    st.markdown("### Step 2: Confirm Details")
    doc_type = st.session_state.get('intake_doc_type', 'Needs Review')
    if doc_type == 'Passport':
        st.success(f"**DOCUMENT DETECTED**: {doc_type}")
    else:
        st.warning(f"**DOCUMENT DETECTED**: {doc_type}")
    
    if st.session_state.get('intake_warnings'):
        for w in st.session_state['intake_warnings']:
            st.warning(w)
            
    st.markdown("Please confirm the extracted information before saving.")
    
    ext = st.session_state.get('intake_extracted', {})
    conf = st.session_state.get('intake_confidence', {})
    
    def render_field(label, key):
        val = ext.get(key, "")
        c = conf.get(key, "low")
        help_text = "Please confirm this field." if c == "low" or not val else None
        return st.text_input(label, value=val, help=help_text)
    
    with st.form("confirm_details_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = render_field("Full Name", "Full Name")
            dob = render_field("Date of Birth", "Date of Birth")
            nationality = render_field("Nationality", "Nationality")
        with col2:
            pass_num = render_field("Passport Number", "Passport Number")
            issue = render_field("Issue Date", "Issue Date")
            expiry = render_field("Expiry Date", "Expiry Date")
            place = render_field("Place of Issue", "Place of Issue")'''
content = content.replace(old_step2, new_step2)

# 4. Update step 4 save logic (safe_path, and Activity log)
old_step4 = '''        doc_id = f"DOC-{uuid.uuid4().hex[:8]}"
        file_path = os.path.join("documents", st.session_state.get('intake_file_name', 'passport.pdf'))
        
        conn.execute(\'''
            INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at)
            VALUES (?, ?, 'Under Review', ?, ?, ?)
        \''', (doc_id, req_id, json.dumps(ext), file_path, datetime.now().isoformat()))
        
        # Log activity
        conn.execute("INSERT INTO activity (customer_id, description) VALUES (?, ?)", (cust_id, f"Passport uploaded for {ext['Full Name']}"))'''

new_step4 = '''        doc_id = f"DOC-{uuid.uuid4().hex[:8]}"
        file_path = st.session_state.get('intake_safe_path', os.path.join("documents", st.session_state.get('intake_file_name', 'passport.pdf')))
        
        conn.execute(\'''
            INSERT INTO documents (id, requirement_id, status, extracted_data, file_path, uploaded_at)
            VALUES (?, ?, 'Under Review', ?, ?, ?)
        \''', (doc_id, req_id, json.dumps(ext), file_path, datetime.now().isoformat()))
        
        # Log activity (Do not expose passport number, just name)
        conn.execute("INSERT INTO activity (customer_id, description) VALUES (?, ?)", (cust_id, f"Passport uploaded for traveller"))
        
        # Remove from session so it won't be deleted by reset_intake
        if 'intake_safe_path' in st.session_state:
            del st.session_state['intake_safe_path']'''
content = content.replace(old_step4, new_step4)

with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(content)
