from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py")
at.run()

# 1. Login
username_input = at.text_input[0]
password_input = at.text_input[1]
username_input.input("admin").run()
password_input.input("admin123").run()

login_btn = at.button[0]
login_btn.click().run()

# 2. Go to Customers
# The top nav has several buttons. "Customers" is usually index 1
for b in at.button:
    if getattr(b, 'label', '') == 'Customers':
        b.click().run()
        break

print("Current Page after Customers click:", at.session_state.get('nav_page'))

# 3. Find and click 'Open Customer' for KT-C-0002
clicked = False
for b in at.button:
    if getattr(b, 'label', '') == 'Open Customer' and 'KT-C-0002' in getattr(b, 'key', ''):
        b.click().run()
        clicked = True
        break

if not clicked:
    print("Could not find Open Customer button for KT-C-0002")
else:
    print("Current Page after Open Customer click:", at.session_state.get('nav_page'))
    print("Query Params after Open Customer click:", at.query_params)
