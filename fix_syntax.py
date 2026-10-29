with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("doc_type = detect_type(text_clean)'", "doc_type = detect_type(text_clean)")

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
