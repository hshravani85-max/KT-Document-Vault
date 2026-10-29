import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix simple_pdf_extract escape chars
old_decode = "for s in strings: text += s.decode('ascii', 'ignore') + '\\n'"
new_decode = "for s in strings: text += s.decode('ascii', 'ignore').replace('\\\\(', '(').replace('\\\\)', ')') + '\\n'"
content = content.replace(old_decode, new_decode)

# Fix flight parsing logic for boilerplate
old_flight_loop = """        for f_key in ['Passenger Name', 'Route', 'Outbound', 'Return', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Cabin']:
            if f_key in extracted_flight:
                val = ' '.join(extracted_flight[f_key]).strip()
                if not is_flight_label(val) and len(val) > 2 and not re.search(r'\\b(prototype|fictional)\\b', val, re.IGNORECASE):
                    # Map to the global schema
                    schema_map = {
                        'Outbound': 'Departure Date/Time',
                        'Return': 'Arrival Date/Time',
                        'Cabin': 'Cabin Class',
                        'Route': 'Route'
                    }
                    target_key = schema_map.get(f_key, f_key)
                    data[target_key] = val
                    confidence[target_key] = 'high'"""

new_flight_loop = """        for f_key in ['Passenger Name', 'Route', 'Outbound', 'Return', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Cabin']:
            if f_key in extracted_flight:
                val = ' '.join(extracted_flight[f_key]).strip()
                # Exclude long boilerplate and known disclaimer words
                if not is_flight_label(val) and len(val) > 2 and not re.search(r'\\b(prototype|fictional|document|airline, hotel)\\b', val, re.IGNORECASE):
                    if f_key != 'Route' and len(val) > 50:
                        continue # Ignore long paragraphs accidentally captured
                    # Map to the global schema
                    schema_map = {
                        'Outbound': 'Departure Date/Time',
                        'Return': 'Arrival Date/Time',
                        'Cabin': 'Cabin Class',
                        'Route': 'Route'
                    }
                    target_key = schema_map.get(f_key, f_key)
                    data[target_key] = val
                    confidence[target_key] = 'high'"""

content = content.replace(old_flight_loop, new_flight_loop)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("document_processor.py patched.")
