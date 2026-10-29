import re

with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

def replace_parser(match):
    return """def parse_passport_text(text):
    data = {}
    confidence = {}
    
    lines = [line.strip() for line in text.replace('\\r', '\\n').split('\\n') if line.strip()]
    text_clean = ' '.join(lines)
    
    def detect_type(t):
        t = t.lower()
        if re.search(r'\\b(passport|travel document|republic of)\\b', t): return 'Passport'
        if re.search(r'\\b(visa|entry permit|entry clearance)\\b', t): return 'Visa / Entry Document'
        if re.search(r'\\b(e-ticket|flight|boarding pass|pnr|airline)\\b', t): return 'Flight Ticket'
        if re.search(r'\\b(hotel|reservation|check-in|room)\\b', t): return 'Hotel Voucher'
        if re.search(r'\\b(insurance|policy|certificate of insurance)\\b', t): return 'Travel Insurance'
        if re.search(r'\\b(transfer|pickup|drop|chauffeur)\\b', t): return 'Transfer Voucher'
        if re.search(r'\\b(sightseeing|tour|attraction|voucher)\\b', t): return 'Sightseeing Voucher'
        if re.search(r'\\b(itinerary|travel plan)\\b', t): return 'Itinerary'
        return 'Needs Review'
        
    doc_type = detect_type(text_clean)
    
    # Define expected schemas
    schemas = {
        'Passport': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
        'Visa / Entry Document': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
        'Flight Ticket': ['Passenger Name', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time'],
        'Hotel Voucher': ['Guest Name', 'Hotel Name', 'Check-in Date', 'Check-out Date', 'Booking Reference'],
        'Travel Insurance': ['Insured Name', 'Policy Number', 'Valid From', 'Valid Until'],
        'Transfer Voucher': ['Passenger Name', 'Pickup Location', 'Dropoff Location', 'Date', 'Time'],
        'Sightseeing Voucher': ['Guest Name', 'Tour Name', 'Date', 'Booking Reference'],
        'Arrival / Entry Document': ['Passenger Name', 'Arrival Date', 'Reference Number'],
        'Itinerary': ['Passenger Name', 'Start Date', 'End Date'],
        'Needs Review': ['Document Details']
    }
    
    expected_fields = schemas.get(doc_type, schemas['Needs Review'])
    for f in expected_fields:
        data[f] = ""
        confidence[f] = "low"

    # Passport / Visa Extraction Logic
    if doc_type in ['Passport', 'Visa / Entry Document']:
        KNOWN_LABELS = [
            'full name', 'name', 'surname', 'given name', 'given names',
            'passport no', 'passport number', 'document no', 'document number',
            'dob', 'date of birth', 'birth date',
            'nationality',
            'issue date', 'date of issue',
            'expiry date', 'date of expiry', 'valid until',
            'place of issue', 'issuing authority',
            'sex', 'gender'
        ]
        
        def is_label(s):
            s_lower = s.strip().lower().replace(':', '').replace('-', '')
            for label in KNOWN_LABELS:
                if s_lower == label or s_lower.startswith(label + ' '):
                    return True
            return False

        def clean_label(s):
            return re.sub(r'^(?:Full Name|Name|Surname|Given Name(?:s)?|Passport No\\.?|Passport Number|Document No\\.?|Document Number|DOB|Date of Birth|Birth Date|Nationality|Issue Date|Date of Issue|Expiry Date|Date of Expiry|Valid Until|Place of Issue|Issuing Authority)\\s*(?::|-)?\\s*', '', s, flags=re.IGNORECASE).strip()

        extracted = {}
        current_label = None
        
        for line in lines:
            line_lower = line.lower()
            found_label = None
            
            if re.search(r'\\b(?:full name|name|surname|given name(?:s)?)\\b', line_lower): found_label = 'Full Name'
            elif re.search(r'\\b(?:passport no\\.?|passport number|document no\\.?|document number)\\b', line_lower): found_label = 'Passport Number'
            elif re.search(r'\\b(?:dob|date of birth|birth date)\\b', line_lower): found_label = 'Date of Birth'
            elif re.search(r'\\b(?:nationality)\\b', line_lower): found_label = 'Nationality'
            elif re.search(r'\\b(?:issue date|date of issue)\\b', line_lower): found_label = 'Issue Date'
            elif re.search(r'\\b(?:expiry date|date of expiry|valid until)\\b', line_lower): found_label = 'Expiry Date'
            elif re.search(r'\\b(?:place of issue|issuing authority)\\b', line_lower): found_label = 'Place of Issue'
                
            if found_label:
                current_label = found_label
                val = clean_label(line)
                if val and not is_label(val):
                    if current_label not in extracted: extracted[current_label] = []
                    extracted[current_label].append(val)
            else:
                if current_label:
                    if not is_label(line):
                        if current_label not in extracted: extracted[current_label] = []
                        extracted[current_label].append(line)
                        
        if 'Full Name' in extracted:
            val = ' '.join(extracted['Full Name']).strip()
            if not is_label(val) and len(val) > 2:
                data['Full Name'] = val
                confidence['Full Name'] = 'high'
                
        if 'Passport Number' in extracted:
            val = ''.join(extracted['Passport Number']).replace(' ', '').upper()
            m = re.search(r'([A-Z0-9]{6,20})', val)
            if m and not is_label(val):
                data['Passport Number'] = m.group(1)
                confidence['Passport Number'] = 'high'
                
        date_pattern = r'(\\d{1,2}\\s*[A-Za-z]{3,4}\\s*\\d{4}|\\d{2}/\\d{2}/\\d{4}|\\d{2}-\\d{2}-\\d{4})'
        for f in ['Date of Birth', 'Issue Date', 'Expiry Date']:
            if f in extracted:
                val = ' '.join(extracted[f])
                m = re.search(date_pattern, val)
                if m:
                    data[f] = m.group(1).strip()
                    confidence[f] = 'high'
                    
        if 'Nationality' in extracted:
            val = ' '.join(extracted['Nationality']).strip()
            if not is_label(val) and len(val) > 2 and not re.search(r'\\d', val):
                data['Nationality'] = val
                confidence['Nationality'] = 'high'
                
        if 'Place of Issue' in extracted:
            lines_extr = extracted['Place of Issue']
            first_line = lines_extr[0].strip() if lines_extr else ""
            if first_line and not is_label(first_line) and len(first_line) < 50 and not re.search(r'\\b(prototype|fictional|document|identity|testing|demo synthetic|data sheet)\\b', first_line, re.IGNORECASE):
                data['Place of Issue'] = first_line
                confidence['Place of Issue'] = 'high'
        if not data.get('Passport Number'):
            m = re.search(r'\\b([A-Z][0-9]{7})\\b', text_clean)
            if m:
                data['Passport Number'] = m.group(1)
                confidence['Passport Number'] = 'high'
                
    # Basic Extraction Logic for Flight Ticket
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
            confidence['Flight Number'] = 'high'
            
    # If other types, we can do similar basic extractions...
    # But as requested, if empty, it's fine as long as the fields exist in `data` to be editable!

    return data, confidence, doc_type

def process_document(file_name, file_bytes):
    warnings = []
    text = ""
    source_type = "manual_required"
    doc_type = "Needs Review"
    data = {}
    confidence = {}
    
    import ocr_service
    ocr_provider = "None"
    
    # Tier 1: Embedded PDF Text
    if file_name.lower().endswith('.pdf'):
        text = simple_pdf_extract(file_bytes)
        if text.strip() and len(text.strip()) > 30: # reasonable threshold
            source_type = "pdf_text"
            data, confidence, doc_type = parse_passport_text(text)
            
    # Tier 2: OCR 
    if not text.strip() or len(text.strip()) <= 30:
        ocr_result = ocr_service.extract_text(file_bytes, file_name)
        ocr_provider = ocr_result['provider']
        if ocr_result['success'] and ocr_result['raw_text'].strip():
            source_type = "ocr"
            text = ocr_result['raw_text']
            data, confidence, doc_type = parse_passport_text(text)
            warnings.extend(ocr_result.get('warnings', []))
        else:
            warnings.extend(ocr_result.get('warnings', []))
        
    # The confidence check inside process_document is now handled organically by the fact
    # that `parse_passport_text` returns the full schema filled with empty strings.
            
    return {
        'document_type': doc_type,
        'source_type': source_type,
        'raw_text': text,
        'extracted_fields': data,
        'warnings': warnings,
        'confidence': confidence,
        'ocr_provider': ocr_provider
    }"""

content = re.sub(r'def parse_passport_text\(text\):.*?(?=\n$|\Z)', replace_parser, content, flags=re.DOTALL)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated document_processor.py schema")
