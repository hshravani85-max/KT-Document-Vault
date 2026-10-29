import re

with open('pages/smart_intake.py', 'r', encoding='utf-8') as f:
    content = f.read()

pattern = r"trav_id = services\.add_traveller\(\s*customer_id=cust_id,\s*full_name=ext\['Full Name'\],\s*dob=ext\['Date of Birth'\],\s*traveller_type=\"Adult\",\s*relationship=\"Self\",\s*lead_traveller=True\s*\)"
replacement = """trav_id = services.add_traveller(
            customer_id=cust_id,
            full_name=ext.get('Full Name', ''),
            dob=ext.get('Date of Birth'),
            traveller_type="Adult",
            relationship="Self",
            lead_traveller=True,
            passport_number=ext.get('Passport Number'),
            nationality=ext.get('Nationality')
        )"""

content = re.sub(pattern, replacement, content)

with open('pages/smart_intake.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Regex replace successful.")
