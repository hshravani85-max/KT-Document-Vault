import re

with open('ui_helpers.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the render_top_nav HTML and add Streamlit buttons for navigation
new_nav = """def render_top_nav():
    full_name = st.session_state.get('user_full_name', 'Guest')
    role = st.session_state.get('user_role', '')
    
    st.markdown(f'''
        <div class="top-nav">
            <div style="font-weight: 800; font-size: 1.2rem; color: #1a73e8; font-style: italic;">✈️ Khanna Travels</div>
            <div class="nav-profile">
                <span>🔔</span>
                <span style="font-weight: 600; color: #555; background: #f1f3f4; padding: 4px 10px; border-radius: 12px; font-size: 0.9rem;">{full_name} ({role})</span>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    cols = st.columns([1, 1, 1, 1, 1, 4, 1])
    with cols[0]:
        if st.button("Home", use_container_width=True):
            st.query_params.page = "staff_home"
            st.rerun()
    with cols[1]:
        if st.button("Customers", use_container_width=True):
            st.query_params.page = "customers"
            st.rerun()
    with cols[2]:
        if st.button("Trips", use_container_width=True):
            st.query_params.page = "trips"
            st.rerun()
    with cols[3]:
        if st.button("Documents", use_container_width=True):
            st.query_params.page = "documents"
            st.rerun()
    with cols[4]:
        if st.button("Vault Search", use_container_width=True):
            st.query_params.page = "vault_search"
            st.rerun()
    with cols[6]:
        if st.button("Logout", use_container_width=True):
            import auth_services
            auth_services.logout(st.session_state.get('session_token'))
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
            
    st.markdown("<hr style='margin-top:0px;'>", unsafe_allow_html=True)
"""

# Apply the regex substitution
text = re.sub(r"def render_top_nav\(\):.*?(?=\n\ndef render_badge)", new_nav, text, flags=re.DOTALL)

with open('ui_helpers.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("ui_helpers.py updated for Streamlit native routing.")
