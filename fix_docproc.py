with open('document_processor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_tier = """    # Tier 1: Embedded PDF Text
    if file_name.lower().endswith('.pdf'):
        text = simple_pdf_extract(file_bytes)
        if text.strip():
            source_type = "pdf_text"
            data, confidence, doc_type = parse_passport_text(text)
        else:
            # Tier 2: OCR (Unavailable locally)
            warnings.append("Automatic OCR is unavailable for this document. Please review and enter the missing fields.")
    else:
        # Tier 2: OCR (Unavailable locally)
        warnings.append("Automatic OCR is unavailable for this document. Please review and enter the missing fields.")"""

new_tier = """    import ocr_service
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
            warnings.extend(ocr_result.get('warnings', []))"""

content = content.replace(old_tier, new_tier)

old_return = """    return {
        'document_type': doc_type,
        'source_type': source_type,
        'raw_text': text,
        'extracted_fields': data,
        'warnings': warnings,
        'confidence': confidence
    }"""

new_return = """    return {
        'document_type': doc_type,
        'source_type': source_type,
        'raw_text': text,
        'extracted_fields': data,
        'warnings': warnings,
        'confidence': confidence,
        'ocr_provider': ocr_provider
    }"""
content = content.replace(old_return, new_return)

with open('document_processor.py', 'w', encoding='utf-8') as f:
    f.write(content)
