import re

with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

debug_block = """
if not active_user:
    st.error(f"DEBUG: active_user is None. token={token}")
    if token:
        try:
            conn = database.get_connection()
            sess = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
            st.error(f"DEBUG: Session in DB: {dict(sess) if sess else 'NOT FOUND'}")
        except Exception as e:
            st.error(f"DEBUG DB EXCEPTION: {e}")
    st.session_state.pop('session_token', None)
    load_page("login")
    st.stop()
"""

# Replace the current if not active_user block
text = re.sub(r"if not active_user:.*?load_page\(\"login\"\)", debug_block, text, flags=re.DOTALL)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Added visible debug box to app.py")
