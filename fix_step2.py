with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """elif step == 2:
    st.markdown("### Step 2: Confirm Details")
    st.success(f"**DOCUMENT DETECTED**: Passport")
    st.markdown("Please confirm the extracted information before saving.")"""

new_block = """elif step == 2:
    st.markdown("### Step 2: Confirm Details")
    st.success(f"**DOCUMENT DETECTED**: Passport")
    
    if st.session_state.get('intake_warnings'):
        for w in st.session_state['intake_warnings']:
            st.warning(w)
            
    st.markdown("Please confirm the extracted information before saving.")"""

content = content.replace(old_block, new_block)
with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(content)
