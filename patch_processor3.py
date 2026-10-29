import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_route_clean = "val = val.replace('\\\\', ')').replace(') )', '))').replace(')(', ') - (')"
new_route_clean = "val = val.replace('\\\\', ')').replace(') ', ') - ').replace('))', ')') "

content = content.replace(old_route_clean, new_route_clean)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_processor.py route patched 2.")
