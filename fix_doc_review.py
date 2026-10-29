import re

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the Extracted Information block
old_info_block = """    st.write("### Extracted Information")
    data = json.loads(d['extracted_data']) if d['extracted_data'] else {}
    for k, v in data.items():
        st.text_input(k, value=v, key=f"edit_{k}")"""

new_info_block = """    st.write("### Extracted Information")
    
    if st.session_state.get(f'reextract_mode_{doc_id}'):
        st.info("Please correct any missing or incorrect fields below before saving.")
        re_data = st.session_state.get(f'reextract_data_{doc_id}', {})
        
        updated_re_data = {}
        for k, v in re_data.items():
            updated_re_data[k] = st.text_input(k, value=v, key=f"re_edit_{k}")
            
        c1, c2 = st.columns(2)
        if c1.button("Cancel"):
            st.session_state[f'reextract_mode_{doc_id}'] = False
            st.rerun()
        if c2.button("Confirm & Save Information"):
            # Update database
            import json
            conn = database.get_connection()
            conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(updated_re_data), doc_id))
            # Activity
            from datetime import datetime
            trip_id_for_act = d['trip_id']
            if not trip_id_for_act and d['traveller_id']:
                t_cust = conn.execute("SELECT customer_id FROM travellers WHERE id=?", (d['traveller_id'],)).fetchone()
                if t_cust:
                    conn.execute("INSERT INTO activity (customer_id, description, timestamp) VALUES (?, ?, ?)", (t_cust['customer_id'], f"Document {doc_id} re-extracted and saved", datetime.now().isoformat()))
            elif trip_id_for_act:
                conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", (trip_id_for_act, f"Document {doc_id} re-extracted and saved", datetime.now().isoformat()))
            conn.commit()
            conn.close()
            
            st.session_state[f'reextract_mode_{doc_id}'] = False
            st.success("Information saved.")
            st.rerun()

    else:
        data = json.loads(d['extracted_data']) if d['extracted_data'] and d['extracted_data'] != "{}" else {}
        
        if not data:
            st.warning("No extracted information is saved for this document. Re-extract information or enter details for review.")
        else:
            for k, v in data.items():
                st.text_input(k, value=v, key=f"edit_{k}", disabled=True)
                
        if status in ['Under Review', 'Verified', 'Rejected', 'Re-upload Required']:
            if st.button("Re-extract Information"):
                import document_processor
                with open(d['file_path'], 'rb') as f:
                    fb = f.read()
                res = document_processor.process_document(d['file_path'], fb)
                st.session_state[f'reextract_data_{doc_id}'] = res['extracted_fields']
                st.session_state[f'reextract_mode_{doc_id}'] = True
                st.rerun()"""

content = content.replace(old_info_block, new_info_block)

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated document_review.py")
