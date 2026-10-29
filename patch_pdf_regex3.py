import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the Route cleanup hack completely
content = re.sub(r'# Special cleanup for Route.*?(?=# Exclude long boilerplate)', '', content, flags=re.DOTALL)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_processor.py Route hack removed.")
