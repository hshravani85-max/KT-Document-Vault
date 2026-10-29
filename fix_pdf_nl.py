with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("text += s.decode('ascii', 'ignore') + ' '", "text += s.decode('ascii', 'ignore') + '\\n'")

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
