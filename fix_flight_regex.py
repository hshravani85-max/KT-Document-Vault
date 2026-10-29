import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_flight = """    # Basic Extraction Logic for Flight Ticket
    elif doc_type == 'Flight Ticket':
        # passenger name
        m = re.search(r'(?:passenger|name|traveler)\\s*[:\\-]?\\s*([A-Za-z\\s]{4,30})', text_clean, re.IGNORECASE)
        if m: 
            data['Passenger Name'] = m.group(1).strip()
            confidence['Passenger Name'] = 'high'
        
        # PNR
        m = re.search(r'(?:pnr|booking ref|booking reference|record locator)\\s*[:\\-]?\\s*([A-Z0-9]{5,8})', text_clean, re.IGNORECASE)
        if m:
            data['PNR/Booking Reference'] = m.group(1).strip()
            confidence['PNR/Booking Reference'] = 'high'
            
        # flight number
        m = re.search(r'\\b([A-Z]{2}\\s*\\d{3,4})\\b', text_clean)
        if m:
            data['Flight Number'] = m.group(1).strip()
            confidence['Flight Number'] = 'high'"""

new_flight = """    # Basic Extraction Logic for Flight Ticket
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

content = content.replace(old_flight, new_flight)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated flight ticket regexes")
