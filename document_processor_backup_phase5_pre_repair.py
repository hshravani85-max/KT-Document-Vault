import os
import re
import zlib

def simple_pdf_extract(pdf_data):
    text = ''
    try:
        import base64
        streams = re.findall(b'<<(.*?)>>[\r\n\\s]*stream[\r\n]*(.*?)[\r\n]*endstream', pdf_data, re.DOTALL)
        for dict_part, stream_data in streams:
            if b'/ASCII85Decode' in dict_part:
                if stream_data.endswith(b'~>\n'): stream_data = stream_data[:-3]
                elif stream_data.endswith(b'~>\r\n'): stream_data = stream_data[:-4]
                elif stream_data.endswith(b'~>'): stream_data = stream_data[:-2]
                try: stream_data = base64.a85decode(stream_data)
                except: pass
                
            if b'/FlateDecode' in dict_part:
                try: stream_data = zlib.decompress(stream_data)
                except: pass
                
            blocks = re.findall(b'BT(.*?)ET', stream_data, re.DOTALL)
            for block in blocks:
                strings = re.findall(b'\\((.*?)(?<!\\\\)\\)', block)
                for s in strings: text += s.decode('ascii', 'ignore').replace('\\(', '(').replace('\\)', ')') + '\n'
        if not text.strip():
            blocks = re.findall(b'BT(.*?)ET', pdf_data, re.DOTALL)
            for block in blocks:
                strings = re.findall(b'\\((.*?)(?<!\\\\)\\)', block)
                for s in strings: text += s.decode('ascii', 'ignore').replace('\\(', '(').replace('\\)', ')') + '\n'
    except Exception:
        pass
    return text.strip()

def parse_passport_text(text):
    data = {}
    confidence = {}
    
    # Strip disclaimers and synthetic prototype notices
    raw_lines = [line.strip() for line in text.replace('\r', '\n').split('\n') if line.strip()]
    lines = []
    in_disclaimer = False
    for l in raw_lines:
        l_lower = l.lower()
        if 'prototype notice' in l_lower or 'this document is fictional' in l_lower or '!no ' in l_lower:
            in_disclaimer = True
            continue
        if in_disclaimer:
            continue
        if any(marker in l_lower for marker in ['demo / sample', 'synthetic ']):
            continue
        lines.append(l)
    
    text_clean = ' '.join(lines)
    
    def detect_type(clean_lines):
        t = ' '.join(clean_lines).lower()
        title_line = clean_lines[0].lower() if clean_lines else ''
        
        scores = {
            'Passport': 0,
            'Visa / Entry Document': 0,
            'Flight Ticket': 0,
            'Hotel Voucher': 0,
            'Travel Insurance': 0,
            'Transfer Voucher': 0,
            'Sightseeing Voucher': 0,
            'Arrival / Entry Document': 0,
            'Itinerary': 0
        }
        
        # Primary Title Evidence Priority (Weight +6)
        if re.search(r'\b(flight\s*ticket|flight\s*itinerary|flight\s*booking|e-ticket|boarding\s*pass)\b', title_line): scores['Flight Ticket'] += 6
        elif re.search(r'\b(itinerary|travel plan|tour itinerary)\b', title_line): scores['Itinerary'] += 6
        elif re.search(r'\b(arrival\s*/?\s*entry\s*(?:document|information|card)?|arrival card|disembarkation)\b', title_line): scores['Arrival / Entry Document'] += 6
        elif re.search(r'\b(transfer\s*voucher)\b', title_line): scores['Transfer Voucher'] += 6
        elif re.search(r'\b(hotel\s*voucher|hotel\s*confirmation|hotel\s*booking)\b', title_line): scores['Hotel Voucher'] += 6
        elif re.search(r'\b(travel\s*insurance|insurance\s*policy|certificate\s*of\s*insurance)\b', title_line): scores['Travel Insurance'] += 6
        elif re.search(r'\b(sightseeing\s*voucher|tour\s*voucher)\b', title_line): scores['Sightseeing Voucher'] += 6
        elif re.search(r'\b(visa\s*/?\s*entry\s*(?:document)?|visa)\b', title_line): scores['Visa / Entry Document'] += 6
        elif re.search(r'\b(passport|republic\s*of)\b', title_line): scores['Passport'] += 6
        
        # Passport Body Rules
        if re.search(r'\b(passport|republic of)\b', t): scores['Passport'] += 4
        if re.search(r'\b(nationality|place of birth|date of birth)\b', t): scores['Passport'] += 1
        
        # Visa Body Rules
        if re.search(r'\b(visa|entry permit|entry clearance)\b', t): scores['Visa / Entry Document'] += 4
        
        # Flight Ticket Body Rules
        if re.search(r'\b(flight ticket|boarding pass|e-ticket|flight itinerary|flight booking|airline)\b', t): scores['Flight Ticket'] += 4
        if re.search(r'\b(flight|flight number|cabin class|pnr|airways)\b', t): scores['Flight Ticket'] += 2
        
        # Hotel Voucher Body Rules
        if re.search(r'\b(hotel voucher|hotel booking|hotel reservation|accommodation voucher)\b', t): scores['Hotel Voucher'] += 4
        if re.search(r'\b(hotel|check-in|check-out|room type|hotel address)\b', t): scores['Hotel Voucher'] += 2
        if re.search(r'\b(guest|guest name)\b', t): scores['Hotel Voucher'] += 1
        
        # Travel Insurance Body Rules
        if re.search(r'\b(travel insurance|insurance policy|certificate of insurance)\b', t): scores['Travel Insurance'] += 4
        
        # Transfer Voucher Body Rules (Require specific transfer voucher indicators)
        if re.search(r'\b(transfer voucher|airport transfer|chauffeur service)\b', t): scores['Transfer Voucher'] += 4
        elif re.search(r'\b(transfer|pickup location|dropoff location)\b', t): scores['Transfer Voucher'] += 2
        
        # Sightseeing Voucher Body Rules
        if re.search(r'\b(sightseeing voucher|tour voucher|attraction voucher)\b', t): scores['Sightseeing Voucher'] += 4
        elif re.search(r'\b(sightseeing|tour|attraction)\b', t): scores['Sightseeing Voucher'] += 2
        
        # Arrival / Entry Document Body Rules
        if re.search(r'\b(arrival\s*/?\s*entry\s*document|arrival\s*entry\s*information|arrival document|disembarkation card|arrival card|electronic arrival)\b', t): scores['Arrival / Entry Document'] += 4
        elif re.search(r'\b(arrival date|entry information|port of entry)\b', t): scores['Arrival / Entry Document'] += 2
        
        # Itinerary Body Rules
        if re.search(r'\b(travel itinerary|tour itinerary|day 1|day 2|schedule)\b', t): scores['Itinerary'] += 3

        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]
        sorted_scores = sorted(scores.values(), reverse=True)
        
        if best_score < 2 or (sorted_scores[0] == sorted_scores[1] and sorted_scores[0] > 0):
            return 'Needs Review', 'low'
        return best_type, 'high' if best_score >= 3 else 'medium'
        
    doc_type, type_confidence = detect_type(lines)
    
    # Define expected schemas
    schemas = {
        'Passport': ['Full Name', 'Passport Number', 'Date of Birth', 'Nationality', 'Issue Date', 'Expiry Date', 'Place of Issue'],
        'Visa / Entry Document': ['Traveller Name', 'Visa Number / Reference', 'Destination', 'Purpose', 'Travel Dates', 'Issue Date', 'Expiry Date / Valid Until'],
        'Flight Ticket': ['Passenger Name', 'Route', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Departure Date/Time', 'Arrival Date/Time', 'Cabin Class'],
        'Hotel Voucher': ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address'],
        'Travel Insurance': ['Insured Name', 'Policy Number', 'Insurance Provider', 'Valid From', 'Valid Until', 'Destination / Coverage Area'],
        'Transfer Voucher': ['Passenger Name', 'Booking Reference', 'Pickup Location', 'Dropoff Location', 'Transfer Date', 'Transfer Time'],
        'Sightseeing Voucher': ['Guest Name', 'Booking Reference', 'Tour / Activity Name', 'Activity Date', 'Number of Guests'],
        'Arrival / Entry Document': ['Traveller Name', 'Trip Name', 'Destination', 'Arrival Date', 'Departure Date', 'Reference Number'],
        'Itinerary': ['Trip Destination', 'Start Date', 'End Date', 'Schedule Summary'],
        'Needs Review': ['Document Details']
    }
    
    expected_fields = schemas.get(doc_type, schemas['Needs Review'])
    for f in expected_fields:
        data[f] = ""
        confidence[f] = "low"

    # Passport Extraction Logic
    if doc_type == 'Passport':
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
            return re.sub(r'^(?:Full Name|Name|Surname|Given Name(?:s)?|Passport No\.?|Passport Number|Document No\.?|Document Number|DOB|Date of Birth|Birth Date|Nationality|Issue Date|Date of Issue|Expiry Date|Date of Expiry|Valid Until|Place of Issue|Issuing Authority)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        extracted = {}
        current_label = None
        
        for line in lines:
            line_lower = line.lower()
            found_label = None
            
            if re.search(r'\b(?:full name|name|surname|given name(?:s)?)\b', line_lower): found_label = 'Full Name'
            elif re.search(r'\b(?:passport no\.?|passport number|document no\.?|document number)\b', line_lower): found_label = 'Passport Number'
            elif re.search(r'\b(?:dob|date of birth|birth date)\b', line_lower): found_label = 'Date of Birth'
            elif re.search(r'\b(?:nationality)\b', line_lower): found_label = 'Nationality'
            elif re.search(r'\b(?:issue date|date of issue)\b', line_lower): found_label = 'Issue Date'
            elif re.search(r'\b(?:expiry date|date of expiry|valid until)\b', line_lower): found_label = 'Expiry Date'
            elif re.search(r'\b(?:place of issue|issuing authority)\b', line_lower): found_label = 'Place of Issue'
                
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
                
        date_pattern = r'(\d{1,2}\s*[A-Za-z]{3,4}\s*\d{4}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})'
        for f in ['Date of Birth', 'Issue Date', 'Expiry Date']:
            if f in extracted:
                val = ' '.join(extracted[f])
                m = re.search(date_pattern, val)
                if m:
                    data[f] = m.group(1).strip()
                    confidence[f] = 'high'
                    
        if 'Nationality' in extracted:
            val = ' '.join(extracted['Nationality']).strip()
            if not is_label(val) and len(val) > 2 and not re.search(r'\d', val):
                data['Nationality'] = val
                confidence['Nationality'] = 'high'
                
        if 'Place of Issue' in extracted:
            lines_extr = extracted['Place of Issue']
            first_line = lines_extr[0].strip() if lines_extr else ""
            if first_line and not is_label(first_line) and len(first_line) < 50 and not re.search(r'\b(prototype|fictional|document|identity|testing|demo synthetic|data sheet)\b', first_line, re.IGNORECASE):
                data['Place of Issue'] = first_line
                confidence['Place of Issue'] = 'high'
        if not data.get('Passport Number'):
            m = re.search(r'\b([A-Z][0-9]{7})\b', text_clean)
            if m:
                data['Passport Number'] = m.group(1)
                confidence['Passport Number'] = 'high'

    # Visa / Entry Document Extraction Logic
    elif doc_type == 'Visa / Entry Document':
        def clean_visa_label(s):
            return re.sub(r'^(?:Traveller(?: Name)?|Reference|Visa Number|Visa No\.?|Destination|Purpose|Travel Dates|Issue Date|Date of Issue|Expiry Date|Date of Expiry|Valid Until)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        for line in lines:
            line_lower = line.lower()
            if re.search(r'\b(?:traveller|traveler|name)\b', line_lower) and not data['Traveller Name']:
                v = clean_visa_label(line)
                if v: data['Traveller Name'] = v; confidence['Traveller Name'] = 'high'
            elif re.search(r'\b(?:reference|visa number|visa no\.?)\b', line_lower) and not data['Visa Number / Reference']:
                v = clean_visa_label(line)
                if v: data['Visa Number / Reference'] = v; confidence['Visa Number / Reference'] = 'high'
            elif re.search(r'\b(?:destination|country)\b', line_lower) and not data['Destination']:
                v = clean_visa_label(line)
                if v: data['Destination'] = v; confidence['Destination'] = 'high'
            elif re.search(r'\b(?:purpose)\b', line_lower) and not data['Purpose']:
                v = clean_visa_label(line)
                if v: data['Purpose'] = v; confidence['Purpose'] = 'high'
            elif re.search(r'\b(?:travel dates|validity|duration)\b', line_lower) and not data['Travel Dates']:
                v = clean_visa_label(line)
                if v: data['Travel Dates'] = v; confidence['Travel Dates'] = 'high'
            elif re.search(r'\b(?:issue date|date of issue)\b', line_lower) and not data['Issue Date']:
                v = clean_visa_label(line)
                if v: data['Issue Date'] = v; confidence['Issue Date'] = 'high'
            elif re.search(r'\b(?:expiry date|valid until)\b', line_lower) and not data['Expiry Date / Valid Until']:
                v = clean_visa_label(line)
                if v: data['Expiry Date / Valid Until'] = v; confidence['Expiry Date / Valid Until'] = 'high'

        # If Expiry Date / Valid Until not found, attempt to parse end date from Travel Dates
        if not data['Expiry Date / Valid Until'] and data['Travel Dates']:
            dates = re.findall(r'(\d{1,2}\s+[A-Za-z]{3,4}\s+\d{4}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})', data['Travel Dates'])
            if dates:
                data['Expiry Date / Valid Until'] = dates[-1]
                confidence['Expiry Date / Valid Until'] = 'high'
                
    # Basic Extraction Logic for Flight Ticket
    elif doc_type == 'Flight Ticket':
        KNOWN_LABELS_FLIGHT = [
            'passenger', 'passenger name', 'traveler name',
            'route', 'from', 'origin', 'departing', 'to', 'destination', 'arriving',
            'outbound', 'departure', 'arrival', 'return',
            'airline', 'flight number', 'pnr', 'booking reference', 'reservation reference', 'cabin', 'class'
        ]
        
        def is_flight_label(s):
            s_lower = s.strip().lower().replace(':', '').replace('-', '')
            for label in KNOWN_LABELS_FLIGHT:
                if s_lower == label or s_lower.startswith(label + ' '): return True
            return False

        def clean_flight_label(s):
            return re.sub(r'^(?:Passenger(?: Name)?|Traveler Name|Route|From|Origin|To|Destination|Outbound|Departure|Arrival|Return|Airline|Flight Number|PNR|Booking Reference|Reservation Reference|Cabin|Class)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        extracted_flight = {}
        current_label = None
        
        for line in lines:
            line_lower = line.lower()
            found_label = None
            
            if re.search(r'\b(?:passenger|passenger name|traveler name)\b', line_lower): found_label = 'Passenger Name'
            elif re.search(r'\b(?:route)\b', line_lower): found_label = 'Route'
            elif re.search(r'\b(?:outbound|departure)\b', line_lower): found_label = 'Outbound'
            elif re.search(r'\b(?:arrival|return)\b', line_lower): found_label = 'Return'
            elif re.search(r'\b(?:airline)\b', line_lower): found_label = 'Airline'
            elif re.search(r'\b(?:flight number)\b', line_lower): found_label = 'Flight Number'
            elif re.search(r'\b(?:pnr|booking reference|reservation reference)\b', line_lower): found_label = 'PNR/Booking Reference'
            elif re.search(r'\b(?:from|origin)\b', line_lower): found_label = 'Origin'
            elif re.search(r'\b(?:to|destination)\b', line_lower): found_label = 'Destination'
            elif re.search(r'\b(?:cabin|class)\b', line_lower): found_label = 'Cabin'
                
            if found_label:
                current_label = found_label
                val = clean_flight_label(line)
                if val and not is_flight_label(val):
                    extracted_flight[current_label] = [val]
            else:
                if current_label:
                    if not is_flight_label(line):
                        if current_label not in extracted_flight: extracted_flight[current_label] = []
                        extracted_flight[current_label].append(line)
                        
        for f_key in ['Passenger Name', 'Route', 'Outbound', 'Return', 'Airline', 'Flight Number', 'PNR/Booking Reference', 'Origin', 'Destination', 'Cabin']:
            if f_key in extracted_flight:
                val = ' '.join(extracted_flight[f_key]).strip()
                
                # Exclude long boilerplate and known disclaimer words
                if not is_flight_label(val) and len(val) > 2 and not re.search(r'\b(prototype|fictional|document|airline, hotel)\b', val, re.IGNORECASE):
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
                    confidence[target_key] = 'high'

    # Hotel Voucher Extraction Logic
    elif doc_type == 'Hotel Voucher':
        def clean_hotel_label(s):
            return re.sub(
                r'^(?:Hotel\s+Name|Hotel\s+Address|Hotel|Property|Accommodation|'
                r'Guest\s+Name|Primary\s+Guest|Lead\s+Guest|Traveler\s+Name|Traveller\s+Name|Guest|'
                r'Check-in\s+Date|Check\s+In\s+Date|Check-in|Check\s+In|Arrival\s+Date|'
                r'Check-out\s+Date|Check\s+Out\s+Date|Check-out|Check\s+Out|Departure\s+Date|'
                r'Booking\s+Confirmation\s+Number|Booking\s+Confirmation|Confirmation\s+Number|'
                r'Confirmation\s+No\.?|Booking\s+Reference|Reservation\s+Number|Booking\s+ID|'
                r'Room\s+Type|Room\s+Category|Room|Hotel\s+Address|Address|Location)\s*(?::|-)?\s*',
                '', s, flags=re.IGNORECASE
            ).strip()

        def is_hotel_header(s):
            s_clean = re.sub(r'[^a-z0-9 ]', ' ', s.lower()).strip()
            s_clean = re.sub(r'\s+', ' ', s_clean)
            if s_clean in ['hotel voucher', 'hotel booking', 'voucher', 'hotel reservation', 'hotel confirmation', 'hotel voucher demo']:
                return True
            return False

        extracted_hotel = {}
        for line in lines:
            if is_hotel_header(line):
                continue
            line_lower = line.lower()
            found_key = None
            if re.search(r'\b(?:hotel\s+address|address)\b', line_lower):
                found_key = 'Hotel Address'
            elif re.search(r'\b(?:booking\s+confirmation|confirmation\s+number|confirmation\s+no|booking\s+reference|reservation\s+number|booking\s+id)\b', line_lower):
                found_key = 'Booking Confirmation Number'
            elif re.search(r'\b(?:hotel\s+name|hotel|property|accommodation)\b', line_lower):
                found_key = 'Hotel Name'
            elif re.search(r'\b(?:guest\s+name|primary\s+guest|lead\s+guest|traveler\s+name|traveller\s+name|guest)\b', line_lower):
                found_key = 'Guest Name'
            elif re.search(r'\b(?:check-in|check\s+in|arrival\s+date)\b', line_lower):
                found_key = 'Check-in Date'
            elif re.search(r'\b(?:check-out|check\s+out|departure\s+date)\b', line_lower):
                found_key = 'Check-out Date'
            elif re.search(r'\b(?:room\s+type|room\s+category|room)\b', line_lower):
                found_key = 'Room Type'

            if found_key and found_key not in extracted_hotel:
                val = clean_hotel_label(line)
                if val and not is_hotel_header(val):
                    extracted_hotel[found_key] = val

        for f_key in ['Hotel Name', 'Guest Name', 'Check-in Date', 'Check-out Date', 'Booking Confirmation Number', 'Room Type', 'Hotel Address']:
            if f_key in extracted_hotel:
                data[f_key] = extracted_hotel[f_key]
                confidence[f_key] = 'high'

    # Travel Insurance Extraction Logic
    elif doc_type == 'Travel Insurance':
        def clean_ins_label(s):
            return re.sub(r'^(?:Traveller|Insured(?: Name)?|Policy Number|Policy No\.?|Certificate(?: Number| No\.?)?|Destination|Coverage|Valid From|Valid Until|Provider|Insurer)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        for line in lines:
            line_lower = line.lower()
            if line_lower in ['travel insurance', 'insurance certificate', 'travel insurance certificate', 'certificate of insurance']:
                continue
            if re.search(r'\b(?:traveller|traveler|insured(?: name)?)\b', line_lower) and not data['Insured Name']:
                v = clean_ins_label(line)
                if v: data['Insured Name'] = v; confidence['Insured Name'] = 'high'
            elif re.search(r'\b(?:policy number|policy no\.?|certificate(?: number| no\.?)?)\b', line_lower) and not data['Policy Number']:
                v = clean_ins_label(line)
                if v and not re.search(r'\b(?:travel insurance|insurance certificate)\b', v, re.IGNORECASE):
                    data['Policy Number'] = v; confidence['Policy Number'] = 'high'
            elif re.search(r'\b(?:destination|coverage area)\b', line_lower) and not data['Destination / Coverage Area']:
                v = clean_ins_label(line)
                if v: data['Destination / Coverage Area'] = v; confidence['Destination / Coverage Area'] = 'high'
            elif re.search(r'\b(?:coverage|validity|period)\b', line_lower):
                v = clean_ins_label(line)
                dates = re.findall(r'(\d{1,2}\s+[A-Za-z]{3,4}\s+\d{4}|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{4})', v)
                if len(dates) >= 2:
                    data['Valid From'] = dates[0]; confidence['Valid From'] = 'high'
                    data['Valid Until'] = dates[1]; confidence['Valid Until'] = 'high'
                elif len(dates) == 1:
                    data['Valid Until'] = dates[0]; confidence['Valid Until'] = 'high'
            elif re.search(r'\b(?:valid from)\b', line_lower) and not data['Valid From']:
                v = clean_ins_label(line)
                if v: data['Valid From'] = v; confidence['Valid From'] = 'high'
            elif re.search(r'\b(?:valid until)\b', line_lower) and not data['Valid Until']:
                v = clean_ins_label(line)
                if v: data['Valid Until'] = v; confidence['Valid Until'] = 'high'

    # Transfer Voucher Extraction Logic
    elif doc_type == 'Transfer Voucher':
        def clean_trf_label(s):
            return re.sub(r'^(?:Traveller|Passenger(?: Name)?|Reference|Booking Ref(?:erence)?|Arrival|Departure|Pickup|Dropoff|Date|Time)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        for line in lines:
            line_lower = line.lower()
            if re.search(r'\b(?:traveller|passenger(?: name)?)\b', line_lower) and not data['Passenger Name']:
                v = clean_trf_label(line)
                if v: data['Passenger Name'] = v; confidence['Passenger Name'] = 'high'
            elif re.search(r'\b(?:reference|booking ref(?:erence)?)\b', line_lower) and not data['Booking Reference']:
                v = clean_trf_label(line)
                if v: data['Booking Reference'] = v; confidence['Booking Reference'] = 'high'
            elif re.search(r'\b(?:arrival|pickup)\b', line_lower) and not data['Pickup Location']:
                v = clean_trf_label(line)
                if '->' in v:
                    parts = [p.strip() for p in v.split('->')]
                    data['Pickup Location'] = parts[0]; confidence['Pickup Location'] = 'high'
                    if len(parts) > 1 and not data['Dropoff Location']:
                        data['Dropoff Location'] = parts[1]; confidence['Dropoff Location'] = 'high'
                elif v:
                    data['Pickup Location'] = v; confidence['Pickup Location'] = 'high'
            elif re.search(r'\b(?:departure|dropoff)\b', line_lower) and not data['Dropoff Location']:
                v = clean_trf_label(line)
                if '->' in v:
                    parts = [p.strip() for p in v.split('->')]
                    if not data['Pickup Location']: data['Pickup Location'] = parts[0]; confidence['Pickup Location'] = 'high'
                    data['Dropoff Location'] = parts[-1]; confidence['Dropoff Location'] = 'high'
                elif v:
                    data['Dropoff Location'] = v; confidence['Dropoff Location'] = 'high'
            elif re.search(r'\b(?:date)\b', line_lower) and not data['Transfer Date']:
                v = clean_trf_label(line)
                if v: data['Transfer Date'] = v; confidence['Transfer Date'] = 'high'
            elif re.search(r'\b(?:time)\b', line_lower) and not data['Transfer Time']:
                v = clean_trf_label(line)
                if v: data['Transfer Time'] = v; confidence['Transfer Time'] = 'high'

    # Sightseeing Voucher Extraction Logic
    elif doc_type == 'Sightseeing Voucher':
        def clean_sight_label(s):
            return re.sub(r'^(?:Number of Guests|Guest(?: Name|s)?|Traveller|Booking Ref(?:erence)?|Reference|Activity Date|Tour(?: Name)?|Activity|Date)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        for line in lines:
            line_lower = line.lower()
            if re.search(r'\b(?:traveller|guest(?: name)?)\b', line_lower) and not data['Guest Name']:
                v = clean_sight_label(line)
                if v: data['Guest Name'] = v; confidence['Guest Name'] = 'high'
            elif re.search(r'\b(?:reference|booking ref(?:erence)?)\b', line_lower) and not data['Booking Reference']:
                v = clean_sight_label(line)
                if v: data['Booking Reference'] = v; confidence['Booking Reference'] = 'high'
            elif re.search(r'\b(?:activity date)\b', line_lower) and not data['Activity Date']:
                v = clean_sight_label(line)
                if v: data['Activity Date'] = v; confidence['Activity Date'] = 'high'
            elif re.search(r'\b(?:activity|tour(?: name)?)\b', line_lower) and not data['Tour / Activity Name']:
                v = clean_sight_label(line)
                if v: data['Tour / Activity Name'] = v; confidence['Tour / Activity Name'] = 'high'
            elif re.search(r'\b(?:date)\b', line_lower) and not data['Activity Date']:
                v = clean_sight_label(line)
                if v: data['Activity Date'] = v; confidence['Activity Date'] = 'high'
            elif re.search(r'\b(?:guests|number of guests)\b', line_lower) and not data['Number of Guests']:
                v = clean_sight_label(line)
                if v: data['Number of Guests'] = v; confidence['Number of Guests'] = 'high'

    # Arrival / Entry Document Extraction Logic
    elif doc_type == 'Arrival / Entry Document':
        def clean_arr_label(s):
            return re.sub(r'^(?:Traveller(?: Name)?|Trip(?: Name)?|Arrival Date|Departure Date|Destination|Reference(?: Number)?)\s*(?::|-)?\s*', '', s, flags=re.IGNORECASE).strip()

        for line in lines:
            line_lower = line.lower()
            if re.search(r'\b(?:traveller|passenger(?: name)?)\b', line_lower) and not data['Traveller Name']:
                v = clean_arr_label(line)
                if v: data['Traveller Name'] = v; confidence['Traveller Name'] = 'high'
            elif re.search(r'\b(?:trip(?: name)?)\b', line_lower) and not data['Trip Name']:
                v = clean_arr_label(line)
                if v: data['Trip Name'] = v; confidence['Trip Name'] = 'high'
            elif re.search(r'\b(?:arrival date)\b', line_lower) and not data['Arrival Date']:
                v = clean_arr_label(line)
                if v: data['Arrival Date'] = v; confidence['Arrival Date'] = 'high'
            elif re.search(r'\b(?:departure date)\b', line_lower) and not data['Departure Date']:
                v = clean_arr_label(line)
                if v: data['Departure Date'] = v; confidence['Departure Date'] = 'high'
            elif re.search(r'\b(?:destination)\b', line_lower) and not data['Destination']:
                v = clean_arr_label(line)
                if v: data['Destination'] = v; confidence['Destination'] = 'high'
            elif re.search(r'\b(?:reference(?: number)?)\b', line_lower) and not data['Reference Number']:
                v = clean_arr_label(line)
                if v: data['Reference Number'] = v; confidence['Reference Number'] = 'high'

    # Itinerary Extraction Logic
    elif doc_type == 'Itinerary':
        schedule_entries = []
        for line in lines:
            # Check for day / date pattern, e.g. "12 Dec: ..." or "12 Dec 2026: ..."
            m = re.match(r'^(\d{1,2}\s+[A-Za-z]{3,4}(?:\s+\d{4})?|\bDay\s+\d+)\s*(?::|-)?\s*(.+)$', line, re.IGNORECASE)
            if m:
                schedule_entries.append(f"{m.group(1)}: {m.group(2).strip()}")

        if schedule_entries:
            data['Schedule Summary'] = ' | '.join(schedule_entries[:5])
            confidence['Schedule Summary'] = 'high'
            
            # Start Date from first entry
            d_start = re.search(r'(\d{1,2}\s+[A-Za-z]{3,4}(?:\s+\d{4})?)', schedule_entries[0])
            if d_start:
                data['Start Date'] = d_start.group(1).strip()
                confidence['Start Date'] = 'high'
                
            # End Date from last entry
            d_end = re.search(r'(\d{1,2}\s+[A-Za-z]{3,4}(?:\s+\d{4})?)', schedule_entries[-1])
            if d_end:
                data['End Date'] = d_end.group(1).strip()
                confidence['End Date'] = 'high'
                
        # Try to find destination from lines or header
        for line in lines:
            m_dest = re.search(r'\b(?:destination|trip|tour)\b\s*:\s*(.+)$', line, re.IGNORECASE)
            if m_dest and not data['Trip Destination']:
                data['Trip Destination'] = m_dest.group(1).strip()
                confidence['Trip Destination'] = 'high'
            elif not data['Trip Destination'] and re.search(r'^([A-Za-z\s]+?)\s+(?:itinerary|tour|trip)\b', line, re.IGNORECASE):
                m_title = re.search(r'^([A-Za-z\s]+?)\s+(?:itinerary|tour|trip)\b', line, re.IGNORECASE)
                cand = m_title.group(1).strip()
                if cand and cand.lower() not in ['demo', 'sample', 'the']:
                    data['Trip Destination'] = cand
                    confidence['Trip Destination'] = 'high'
            
    return data, confidence, doc_type, type_confidence

def process_document(file_name, file_bytes):
    warnings = []
    text = ""
    source_type = "manual_required"
    doc_type = "Needs Review"
    type_confidence = "low"
    data = {}
    confidence = {}
    
    import ocr_service
    ocr_provider = "None"
    
    # Tier 1: Embedded PDF Text
    if file_name.lower().endswith('.pdf'):
        text = simple_pdf_extract(file_bytes)
        if text.strip() and len(text.strip()) > 30: # reasonable threshold
            source_type = "pdf_text"
            data, confidence, doc_type, type_confidence = parse_passport_text(text)
            
    # Tier 2: OCR 
    if not text.strip() or len(text.strip()) <= 30:
        ocr_result = ocr_service.extract_text(file_bytes, file_name)
        ocr_provider = ocr_result['provider']
        if ocr_result['success'] and ocr_result['raw_text'].strip():
            source_type = "ocr"
            text = ocr_result['raw_text']
            data, confidence, doc_type, type_confidence = parse_passport_text(text)
            warnings.extend(ocr_result.get('warnings', []))
        else:
            warnings.extend(ocr_result.get('warnings', []))
            
    return {
        'document_type': doc_type,
        'type_confidence': type_confidence,
        'source_type': source_type,
        'raw_text': text,
        'extracted_fields': data,
        'warnings': warnings,
        'confidence': confidence,
        'ocr_provider': ocr_provider
    }
