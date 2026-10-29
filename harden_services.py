import re

with open('services.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add token checking to save_document
old_save = "def save_document(requirement_id, file_path, extracted_data):"
new_save = """def save_document(requirement_id, file_path, extracted_data, session_token):
    import auth_services
    user = auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])"""
if "def save_document(requirement_id, file_path, extracted_data):" in content:
    content = content.replace(old_save, new_save)

# Add token checking to create_customer
old_cust = "def create_customer(full_name, mobile=None, email=None, customer_type=\"Individual\"):"
new_cust = """def create_customer(full_name, mobile=None, email=None, customer_type="Individual", session_token=None):
    import auth_services
    if session_token: auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])"""
if old_cust in content:
    content = content.replace(old_cust, new_cust)

# Add token checking to add_traveller
old_trav = "def add_traveller(customer_id, full_name, dob=None, traveller_type=\"Adult\", relationship=\"Self\", lead_traveller=False, passport_number=None, nationality=None):"
new_trav = """def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None, session_token=None):
    import auth_services
    if session_token: auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])"""
if old_trav in content:
    content = content.replace(old_trav, new_trav)

# Add token checking to create_trip
old_trip = "def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids):"
new_trip = """def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids, session_token=None):
    import auth_services
    if session_token: auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])"""
if old_trip in content:
    content = content.replace(old_trip, new_trip)

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("services.py hardened.")
