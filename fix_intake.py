with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """    if st.button("Upload & Extract", type="primary", disabled=not uploaded_file):
        # Fake extraction for prototype
        st.session_state['intake_file_name'] = uploaded_file.name
        
        # Simulate extraction results (realistic demo data, usually would come from a service)
        st.session_state['intake_extracted'] = {
            "Full Name": "Neha Kapoor",
            "Date of Birth": "14 May 1988",
            "Nationality": "Indian",
            "Passport Number": "Z1234567",
            "Issue Date": "10 Jan 2020",
            "Expiry Date": "09 Jan 2030",
            "Place of Issue": "New Delhi"
        }
        st.session_state['intake_step'] = 2
        st.rerun()"""

new_block = """    if st.button("Upload & Extract", type="primary", disabled=not uploaded_file):
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
        st.rerun()"""

content = content.replace(old_block, new_block)
with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(content)
