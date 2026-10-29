with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_call = """        trav_id = services.add_traveller(
            customer_id=cust_id,
            full_name=ext['Full Name'],
            dob=ext['Date of Birth'],
            traveller_type="Adult",
            relationship="Self",
            lead_traveller=True
        )"""

new_call = """        trav_id = services.add_traveller(
            customer_id=cust_id,
            full_name=ext.get('Full Name', ''),
            dob=ext.get('Date of Birth'),
            traveller_type="Adult",
            relationship="Self",
            lead_traveller=True,
            passport_number=ext.get('Passport Number'),
            nationality=ext.get('Nationality')
        )"""

if old_call in content:
    content = content.replace(old_call, new_call)
    with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed smart_intake.py")
else:
    print("Could not find call in smart_intake.py")
