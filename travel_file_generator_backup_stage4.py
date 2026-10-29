import os
from datetime import datetime
import sqlite3
import database

def generate_consolidated_travel_file(trip_id, out_path=None):
    conn = database.get_connection()
    trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    if not trip:
        raise ValueError("Trip not found.")
        
    cust = conn.execute("SELECT name FROM customers WHERE id = ?", (trip['customer_id'],)).fetchone()
    
    trip_travellers = conn.execute('''
        SELECT t.* FROM travellers t
        JOIN trip_travellers tt ON t.id = tt.traveller_id
        WHERE tt.trip_id = ?
    ''', (trip_id,)).fetchall()
    
    docs = conn.execute('''
        SELECT r.name as req_name, r.type as req_type, d.status, d.extracted_data, t.name as traveller_name
        FROM requirements r
        LEFT JOIN documents d ON r.id = d.requirement_id
        LEFT JOIN travellers t ON r.traveller_id = t.id
        WHERE r.trip_id = ?
    ''', (trip_id,)).fetchall()
    
    conn.close()

    lines = [
        f"Customer: {cust['name'] if cust else 'Unknown'}",
        f"Trip: {trip['name']} ({trip['destination']})",
        f"Dates: {trip['start_date']} to {trip['end_date']}",
        f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Travellers:"
    ]
    for t in trip_travellers:
        lines.append(f" - {t['name']} (Passport: {t['passport_number'] or 'N/A'})")
        
    lines.extend(["", "Document Status Checklist:"])
    
    for d in docs:
        status = d['status'] or "Missing"
        if d['req_type'] == 'TRAVELLER':
            label = f"{d['traveller_name']} - {d['req_name']}"
        else:
            label = f"Trip - {d['req_name']}"
        lines.append(f" - {label}: [{status}]")
        
    if out_path is None:
        out_path = f"documents/TravelFile_{trip_id}.pdf"
    return create_raw_pdf(out_path, "KHANNA TRAVELS - TRAVEL FILE", lines)

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
