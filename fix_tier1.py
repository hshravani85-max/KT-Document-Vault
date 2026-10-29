with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
import base64

# Inject the ASCII85Decode fix safely
def replace_simple_extract(match):
    return """def simple_pdf_extract(pdf_data):
    text = ''
    try:
        import base64
        streams = re.findall(b'<<(.*?)>>[\\r\\n\\s]*stream[\\r\\n]*(.*?)[\\r\\n]*endstream', pdf_data, re.DOTALL)
        for dict_part, stream_data in streams:
            if b'/ASCII85Decode' in dict_part:
                if stream_data.endswith(b'~>\\n'): stream_data = stream_data[:-3]
                elif stream_data.endswith(b'~>\\r\\n'): stream_data = stream_data[:-4]
                elif stream_data.endswith(b'~>'): stream_data = stream_data[:-2]
                try: stream_data = base64.a85decode(stream_data)
                except: pass
                
            if b'/FlateDecode' in dict_part:
                try: stream_data = zlib.decompress(stream_data)
                except: pass
                
            blocks = re.findall(b'BT(.*?)ET', stream_data, re.DOTALL)
            for block in blocks:
                strings = re.findall(b'\\((.*?)\\)', block)
                for s in strings: text += s.decode('ascii', 'ignore') + '\\n'
        if not text.strip():
            blocks = re.findall(b'BT(.*?)ET', pdf_data, re.DOTALL)
            for block in blocks:
                strings = re.findall(b'\\((.*?)\\)', block)
                for s in strings: text += s.decode('ascii', 'ignore') + '\\n'
    except Exception:
        pass
    return text.strip()"""

content = re.sub(r'def simple_pdf_extract\(pdf_data\):.*?return text\.strip\(\)', replace_simple_extract, content, flags=re.DOTALL)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
