import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the simple_pdf_extract regex
old_regex = "strings = re.findall(b'\\\\((.*?)\\\\)', block)"
new_regex = "strings = re.findall(b'\\\\((.*?)(?<!\\\\\\\\)\\\\)', block)"
content = content.replace(old_regex, new_regex)

# Also fix the Route cleanup loop - we no longer need the hacky replace
old_route_clean = "if f_key == 'Route':\\n                    val = val.replace('\\\\\\\\', ')').replace(') ', ') - ').replace('))', ')') "
new_route_clean = ""
content = content.replace(old_route_clean, new_route_clean)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_processor.py regex patched.")
