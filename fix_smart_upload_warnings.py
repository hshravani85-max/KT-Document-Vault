import re

with open('pages/smart_upload.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = """        st.write("### Review Extracted Information")
        fields = result['extracted_fields']"""

new_code = """        st.write("### Review Extracted Information")
        
        warnings_list = result.get('warnings', [])
        for w in warnings_list:
            st.warning(w)
            
        st.info("Please fill or correct any missing or incorrect fields below before saving.")
        fields = result['extracted_fields']"""

content = content.replace(old_code, new_code)

with open('pages/smart_upload.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated smart_upload.py UI")
