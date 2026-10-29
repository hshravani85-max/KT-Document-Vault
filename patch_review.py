import re

with open('pages/document_review.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the display of the Re-extract Information button
old_button_check = "if status in ['Under Review', 'Verified', 'Rejected', 'Re-upload Required']:"
new_button_check = "if status in ['Under Review', 'Rejected', 'Re-upload Required']:"
content = content.replace(old_button_check, new_button_check)

# Add backend security check in "Confirm & Save Information"
old_save_block = """        if c2.button("Confirm & Save Information"):
            # Update database
            import json
            conn = database.get_connection()
            conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(updated_re_data), doc_id))"""

new_save_block = """        if c2.button("Confirm & Save Information"):
            # Update database
            import json
            conn = database.get_connection()
            
            # Security check: Prevent updating a verified document
            current_status = conn.execute("SELECT status FROM documents WHERE id = ?", (doc_id,)).fetchone()['status']
            if current_status == 'Verified':
                st.error("Security Error: Cannot modify extracted data of a VERIFIED document.")
                st.stop()
                
            conn.execute("UPDATE documents SET extracted_data = ? WHERE id = ?", (json.dumps(updated_re_data), doc_id))"""

if old_save_block in content:
    content = content.replace(old_save_block, new_save_block)
else:
    print("WARNING: Could not find old_save_block in document_review.py")

with open('pages/document_review.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_review.py patched for VERIFIED security.")
