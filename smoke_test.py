import streamlit as st
from streamlit.testing.v1 import AppTest

def test_login_and_navigate():
    at = AppTest.from_file("app.py")
    at.run()
    
    # Check if we are on login
    print("Initial title:", at.title)
    
    # Enter credentials
    at.text_input[0].input("admin")
    at.text_input[1].input("admin123")
    at.button[0].click()
    at.run()
    
    # We should be on staff_home now
    print("Session State after login:", at.session_state)
    print("Query Params after login:", at.query_params)
    
    # Now click 'Customers'
    # The 'Customers' button is likely at index 1 or so in ui_helpers top nav
    for i, b in enumerate(at.button):
        if b.label == "Customers":
            print(f"Clicking Customers button {i}")
            b.click()
            break
            
    at.run()
    
    print("Session State after Customers click:", at.session_state)
    print("Query Params after Customers click:", at.query_params)

if __name__ == "__main__":
    test_login_and_navigate()
