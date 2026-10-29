with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re

def place_issue_fix(match):
    return """    if 'Place of Issue' in extracted:
        lines = extracted['Place of Issue']
        first_line = lines[0].strip() if lines else ""
        if first_line and not is_label(first_line) and len(first_line) < 50 and not re.search(r'\\b(prototype|fictional|document|identity|testing|demo synthetic|data sheet)\\b', first_line, re.IGNORECASE):
            data['Place of Issue'] = first_line
            confidence['Place of Issue'] = 'high'
"""

content = re.sub(r"    if 'Place of Issue' in extracted:.*?(?=    if 'Passport Number' not in data:)", place_issue_fix, content, flags=re.DOTALL)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
