import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all occurrences of strings = re.findall(b'\((.*?)\)', block)
# with strings = re.findall(b'\\\\((.*?)(?<!\\\\\\\\)\\\\)', block)
content = content.replace("strings = re.findall(b'\\((.*?)\\)', block)", "strings = re.findall(b'\\\\((.*?)(?<!\\\\\\\\)\\\\)', block)")

# Fix SyntaxWarnings in document_processor.py while we're at it
content = content.replace(r"b'<<(.*?)>>[\r\n\s]*stream", r"b'<<(.*?)>>[\r\n\\s]*stream")

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_processor.py fully patched.")
