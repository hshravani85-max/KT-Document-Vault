import streamlit as st
import textwrap
import auth_services
import ui_helpers

# Self-healing resolution in case of long-running process module caching
if not hasattr(ui_helpers, 'render_logo_html'):
    import importlib
    try:
        importlib.reload(ui_helpers)
    except Exception:
        pass

render_logo_html = getattr(ui_helpers, 'render_logo_html', None)
inject_custom_css = getattr(ui_helpers, 'inject_custom_css', lambda: None)

def render_login():
    inject_custom_css()
    
    col1, col2, col3 = st.columns([1.2, 1.6, 1.2])
    with col2:
        logo_html = render_logo_html(max_width="320px") if render_logo_html else None
        if logo_html:
            st.markdown(textwrap.dedent(f"""
            <div style="background:#FFFFFF; border:1px solid #E5EAF1; border-radius:14px; padding:32px 32px 24px 32px; margin-top:40px; margin-bottom:20px; box-shadow:0 4px 12px rgba(11,35,72,0.06); text-align:center;">
                {logo_html}
                <h2 style="margin:12px 0 0 0; color:#0B2348; font-weight:800; font-size:1.5rem;">Document Vault</h2>
                <p style="margin:4px 0 0 0; color:#64748B; font-size:0.88rem;">Staff & Supervisor Portal Authentication</p>
            </div>
            """), unsafe_allow_html=True)
        else:
            st.markdown(textwrap.dedent("""
            <div style="background:#FFFFFF; border:1px solid #E5EAF1; border-radius:14px; padding:36px 32px 28px 32px; margin-top:50px; margin-bottom:20px; box-shadow:0 4px 12px rgba(11,35,72,0.06); text-align:center;">
                <div style="font-size:0.8rem; font-weight:700; letter-spacing:2px; color:#0875B8; text-transform:uppercase;">KHANNA TRAVELS</div>
                <h2 style="margin:4px 0 0 0; color:#0B2348; font-weight:800; font-size:1.6rem;">Document Vault</h2>
                <p style="margin:6px 0 0 0; color:#64748B; font-size:0.88rem;">Staff & Supervisor Portal Authentication</p>
                <div style="font-size:0.7rem; color:#94A3B8; background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:6px; padding:4px 8px; margin:14px auto 0 auto; max-width:280px;">
                    ℹ️ Official logo asset required. Using neutral placeholder.
                </div>
            </div>
            """), unsafe_allow_html=True)
        
        with st.container():
            username = st.text_input("Username", key="login_username_input")
            password = st.text_input("Password", type="password", key="login_password_input")
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            if st.button("Sign In to KT Vault", type="primary", use_container_width=True, key="login_submit_btn", icon=":material/login:"):
                if not username or not password:
                    st.error("Please provide both username and password.")
                else:
                    clean_username = username.strip()
                    try:
                        session = auth_services.authenticate_user(clean_username, password)
                        if session:
                            st.session_state['session_token'] = session['token']
                            st.session_state['user_full_name'] = session['full_name']
                            st.session_state['user_role'] = session['role']
                            st.success("Login successful. Redirecting...")
                            st.session_state["nav_page"] = "staff_home"
                            st.query_params.page = "staff_home"
                            st.rerun()
                        else:
                            st.error("Invalid username or password.")
                    except PermissionError as pe:
                        st.error(str(pe))

render_login()
