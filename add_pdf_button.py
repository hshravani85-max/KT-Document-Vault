import re

with open("pages/trip_workspace.py", "r", encoding="utf-8") as f:
    content = f.read()

new_block = '''
st.markdown("<hr>", unsafe_allow_html=True)
c_pdf1, c_pdf2 = st.columns([3, 1])
with c_pdf2:
    if st.button("Generate Travel PDF", use_container_width=True):
        import travel_file_generator, base64
        try:
            pdf_path = travel_file_generator.generate_consolidated_travel_file(trip_id)
            st.success("Travel PDF generated successfully.")
            with open(pdf_path, "rb") as pdf_file:
                b64_pdf = base64.b64encode(pdf_file.read()).decode('utf-8')
            filename = pdf_path.split("/")[-1].split("\\\\")[-1]
            href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}" target="_blank" style="display:inline-block; width:100%; text-align:center; padding:8px 16px; background:#1e8e3e; color:white; text-decoration:none; border-radius:4px; font-weight:600;">Open Generated PDF</a>'
            st.markdown(href, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error generating PDF: {str(e)}")

tabs = st.tabs(["Document Checklist", "Trip Itinerary", "Traveller", "Trip Details", "Notes", "Activity"])
'''

# Find tabs = st.tabs and replace
content = content.replace('tabs = st.tabs(["Document Checklist", "Trip Itinerary", "Traveller", "Trip Details", "Notes", "Activity"])', new_block)

with open("pages/trip_workspace.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated trip_workspace.py")
