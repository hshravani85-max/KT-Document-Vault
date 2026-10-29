with open('pages/trip_workspace.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """        with st.container():
            c1, c2, c3 = st.columns([1, 4, 2])
            c1.markdown("")
            c2.markdown(f"**{r['name']}**<br>{render_badge(status)}", unsafe_allow_html=True)
            with c3:"""

new_block = """        with st.container():
            c1, c2, c3 = st.columns([1, 4, 2])
            c1.markdown("")
            
            badge_html = render_badge(status)
            if r['name'] == 'Passport' and status != 'Missing' and r.get('extracted_data'):
                try:
                    import json
                    ext = json.loads(r['extracted_data'])
                    if 'Expiry Date' in ext:
                        expiry_date = ext['Expiry Date']
                        badge_html += f"<br><span style='font-size:0.8rem; color:#666;'>Passport Expiry: {expiry_date}</span>"
                        badge_html += f"<br><span style='font-size:0.8rem; font-weight:600; color:#e67e22;'>Validity: Needs Review</span>"
                except:
                    pass
                    
            c2.markdown(f"**{r['name']}**<br>{badge_html}", unsafe_allow_html=True)
            with c3:"""

content = content.replace(old_block, new_block)
with open('pages/trip_workspace.py', 'w', encoding='utf-8') as f:
    f.write(content)
