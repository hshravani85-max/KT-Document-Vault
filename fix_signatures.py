import re

with open('services.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix signatures
text = text.replace('def create_customer(full_name, mobile=None, email=None, customer_type="Individual", session_token):',
                    'def create_customer(full_name, mobile=None, email=None, customer_type="Individual", session_token=None):')
text = text.replace('def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None, session_token):',
                    'def add_traveller(customer_id, full_name, dob=None, traveller_type="Adult", relationship="Self", lead_traveller=False, passport_number=None, nationality=None, session_token=None):')
text = text.replace('def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids, session_token):',
                    'def create_trip(customer_id, name, destination, start_date, end_date, trip_type, service, department, traveller_ids, session_token=None):')

# Fix logic check
text = text.replace("auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])",
                    "if not session_token: raise PermissionError('Unauthenticated'); auth_services.require_role(session_token, ['Staff', 'Supervisor', 'Admin'])")

with open('services.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Signatures fixed.")
