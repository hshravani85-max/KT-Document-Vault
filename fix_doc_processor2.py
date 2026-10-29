import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_flight_logic = """    # Basic Extraction Logic for Flight Ticket
    elif doc_type == 'Flight Ticket':
        # passenger name
        m = re.search(r'(?:passenger name|passenger|traveler|name)\\s*[:\\-]?\\s*([A-Za-z\\s]+)(?:\\n|$)', text_clean, re.IGNORECASE)
        if m: 
            data['Passenger Name'] = m.group(1).strip()
            confidence['Passenger Name'] = 'high'
            
        # Airline
        m = re.search(r'(?:airline|carrier)\\s*[:\\-]?\\s*([A-Za-z\\s]+)(?:\\n|$)', text_clean, re.IGNORECASE)
        if m: 
            data['Airline'] = m.group(1).strip()
            confidence['Airline'] = 'high'
        
        # PNR
        m = re.search(r'(?:pnr|booking ref|booking reference|record locator)\\s*[:\\-]?\\s*([A-Z0-9]{5,8})', text_clean, re.IGNORECASE)
        if m:
            data['PNR/Booking Reference'] = m.group(1).strip()
            confidence['PNR/Booking Reference'] = 'high'
            
        # flight number
        m = re.search(r'\\b([A-Z]{2}\\s*\\d{3,4})\\b', text_clean)
        if m:
            data['Flight Number'] = m.group(1).strip()
            confidence['Flight Number'] = 'high'
            
        # Origin
        m = re.search(r'(?:origin|from|departing)\\s*[:\\-]?\\s*([A-Za-z\\s]+)(?:\\n|$)', text_clean, re.IGNORECASE)
        if m:
            data['Origin'] = m.group(1).strip()
            confidence['Origin'] = 'high'
            
        # Destination
        m = re.search(r'(?:destination|to|arriving)\\s*[:\\-]?\\s*([A-Za-z\\s]+)(?:\\n|$)', text_clean, re.IGNORECASE)
        if m:
            data['Destination'] = m.group(1).strip()
            confidence['Destination'] = 'high'"""

new_flight_logic = """    # Basic Extraction Logic for Flight Ticket
    elif doc_type == 'Flight Ticket':
        KNOWN_LABELS_FLIGHT = [
            'passenger', 'passenger name', 'traveler name',
            'route', 'from', 'origin', 'departing', 'to', 'destination', 'arriving',
            'outbound', 'departure', 'return',
            'airline', 'flight number', 'pnr', 'booking reference', 'reservation reference', 'cabin', 'class'
        ]
        
        def is_flight_label(s):
            s_lower = s.strip().lower().replace(':', '').replace('-', '')
            for label in KNOWN_LABELS_FLIGHT:
                if s_lower == label or s_lower.startswith(label + ' '): return True
            return False

        def clean_flight_label(s):
            return re.sub(r'^(?:Passenger(?: Name)?|Traveler Name|Route|From|Origin|To|Destination|Outbound|Departure|Return|Airline|Flight Number|PNR|Booking Reference|Reservation Reference|Cabin|Class)\\s*(?::|-)?\\s*', '', s, flags=re.IGNORECASE).strip()

        extracted_flight = {}
        current_label = None
        
        for line in lines:
            line_lower = line.lower()
            found_label = None
            
            if re.search(r'\\b(?:passenger|passenger name|traveler name)\\b', line_lower): found_label = 'Passenger Name'
            elif re.search(r'\\b(?:route)\\b', line_lower): found_label = 'Route'
            elif re.search(r'\\b(?:outbound|departure)\\b', line_lower): found_label = 'Outbound'
            elif re.search(r'\\b(?:return)\\b', line_lower): found_label = 'Return'
            elif re.search(r'\\b(?:airline)\\b', line_lower): found_label = 'Airline'
            elif re.search(r'\\b(?:flight number)\\b', line_lower): found_label = 'Flight Number'
            elif re.search(r'\\b(?:pnr|booking reference|reservation reference)\\b', line_lower): found_label = 'PNR/Booking Reference'
            elif re.search(r'\\b(?:from|origin)\\b', line_lower): found_label = 'Origin'
            elif re.search(r'\\b(?:to|destination)\\b', line_lower): found_label = 'Destination'
            elif re.search(r'\\b(?:cabin|class)\\b', line_lower): found_label = 'Cabin'
                
            if found_label:
                current_label = found_label
                val = clean_flight_label(line)
                if val and not is_flight_label(val):
                    if current_label not in extracted_flight: extracted_flight[current_label] = []
                    extracted_flight[current_label].append(val)
            else:
                if current_label:
                    if not is_flight_label(line):
                        if current_label not in extracted_flight: extracted_flight[current_label] = []
                        extracted_flight[current_label].append(line)
                        
        for f_key in ['Passenger Name', 'Route', 'Outbound', 'Return', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Cabin']:
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

content = content.replace(old_flight_logic, new_flight_logic)

# I also need to update the `Flight Ticket` schema to include Route and Cabin Class
content = content.replace(
    "'Flight Ticket': ['Passenger Name', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time']",
    "'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class']"
)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
