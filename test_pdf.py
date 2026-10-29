import os

def create_raw_pdf(path, title, lines):
    stream_lines = ["BT", "/F1 18 Tf", f"50 720 Td", f"({title}) Tj", "/F1 12 Tf", "0 -30 Td"]
    for line in lines:
        clean_line = line.replace("(", "\\(").replace(")", "\\)")
        stream_lines.append(f"({clean_line}) Tj")
        stream_lines.append("0 -20 Td")
    stream_lines.append("ET")
    
    stream_content = "\n".join(stream_lines) + "\n"
    stream_bytes = stream_content.encode('latin1')
    stream_len = len(stream_bytes)
    
    objects = []
    objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append("3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n")
    objects.append("4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(f"5 0 obj\n<< /Length {stream_len} >>\nstream\n{stream_content}endstream\nendobj\n")
    
    pdf_bytes = bytearray(b"%PDF-1.4\n")
    
    offsets = [0]
    for obj_str in objects:
        offsets.append(len(pdf_bytes))
        pdf_bytes.extend(obj_str.encode('latin1'))
        
    startxref = len(pdf_bytes)
    
    xref = f"xref\n0 {len(offsets)}\n"
    xref += "0000000000 65535 f \n"
    for i in range(1, len(offsets)):
        xref += f"{offsets[i]:010d} 00000 n \n"
        
    pdf_bytes.extend(xref.encode('latin1'))
    
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n"
    pdf_bytes.extend(trailer.encode('latin1'))
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(pdf_bytes)
    return path

create_raw_pdf("test_output.pdf", "KHANNA TRAVELS - TRAVEL FILE", [
    "Customer: Amit Mehta",
    "Trip: Dubai Holiday (Dubai, UAE)",
    "Dates: 2026-12-12 to 2026-12-18",
    "Generated On: 2026-10-10 16:30:00",
    "",
    "Travellers:",
    " - Amit Mehta (Passport: M908122)",
    "",
    "Document Status Checklist:",
    " - Amit Mehta - Passport: [Verified]",
    " - Trip - Flight Ticket: [Missing]"
])
