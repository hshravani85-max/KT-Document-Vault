import re

with open('ui_helpers.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_nav = """def render_top_nav():
    full_name = st.session_state.get('user_full_name', 'Guest')
    role = st.session_state.get('user_role', '')
    
    st.markdown(f'''
        <div class="top-nav">
            <div style="font-weight: 800; font-size: 1.2rem; color: #1a73e8; font-style: italic;">✈️ Khanna Travels</div>
            <div class="nav-links">
                <a href="/?page=staff_home">Home</a>
                <a href="/?page=customers">Customers</a>
                <a href="/?page=trips">Trips</a>
                <a href="/?page=documents">Documents</a>
                <a href="/?page=vault_search">Vault Search</a>
            </div>
            <div class="nav-profile">
                <span>🔔</span>
                <span style="font-weight: 600; color: #555; background: #f1f3f4; padding: 4px 10px; border-radius: 12px; font-size: 0.9rem;">{full_name} ({role})</span>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    col1, col2 = st.columns([9, 1])
    with col2:
        if st.button("Logout"):
            import auth_services
            auth_services.logout(st.session_state.get('session_token'))
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
"""

content = re.sub(r'def render_top_nav\(\):.*?</div>\s*</div>\s*\'\'\', unsafe_allow_html=True\)', new_nav, content, flags=re.DOTALL)

with open('ui_helpers.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("ui_helpers.py updated.")
