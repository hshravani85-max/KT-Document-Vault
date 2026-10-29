import re

with open('pages/trip_workspace.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace hardcoded Staff Member Demo in approval
old_approval = """            staff_identity = "Staff Member (Demo)"
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", 
                         (trip_id, f"Travel File Approved by {staff_identity}", datetime.now().isoformat()))"""

new_approval = """            import auth_services
            user = auth_services.require_role(st.session_state.get('session_token'), ['Supervisor', 'Admin'])
            staff_identity = user['full_name']
            
            conn.execute("INSERT INTO activity (trip_id, description, timestamp) VALUES (?, ?, ?)", 
                         (trip_id, f"Travel File Approved by {staff_identity}", datetime.now().isoformat()))"""

content = content.replace(old_approval, new_approval)

# Add PDF Download block if status is TRAVEL FILE READY
old_ready = "elif business_status == 'TRAVEL FILE READY':\n    st.success(\"Travel File is Approved and Ready.\")"

new_ready = """elif business_status == 'TRAVEL FILE READY':
    st.success("Travel File is Approved and Ready.")
    
    if st.session_state.get('user_role') in ['Supervisor', 'Admin']:
        if st.button("Generate Consolidated PDF", type="primary"):
            import travel_file_generator
            try:
                pdf_path = travel_file_generator.generate_consolidated_travel_file(trip_id)
                with open(pdf_path, "rb") as pdf_file:
                    st.download_button(
                        label="Download Travel File",
                        data=pdf_file,
                        file_name=pdf_path.split("/")[-1].split("\\\\")[-1],
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
"""

content = content.replace(old_ready, new_ready)

with open('pages/trip_workspace.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("trip_workspace.py updated for auth and PDF generation.")
