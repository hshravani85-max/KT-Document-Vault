import re

with open('pages/trip_workspace.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_p = "<p style=\"margin:0; color:#555;\">Passport: {t.get('passport_number', 'Not provided')} | DOB: {t.get('dob', 'Not provided')} | Nationality: {t.get('nationality', 'Not provided')}</p>"
new_p = "<p style=\"margin:0; color:#555;\">Passport: {t.get('passport_number') or 'Not provided'} | DOB: {t.get('dob') or 'Not provided'} | Nationality: {t.get('nationality') or 'Not provided'}</p>"

content = content.replace(old_p, new_p)

with open('pages/trip_workspace.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated trip_workspace.py UI")
