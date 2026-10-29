import travel_file_generator
import document_processor
import database

trip_id = 'KT-T-0001'
conn = database.get_connection()
trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
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
    "Generated On: 2026-10-10 16:00:00",
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
    
path = f"documents/TravelFile_{trip_id}_v2.pdf"
travel_file_generator.create_raw_pdf(path, "KHANNA TRAVELS - TRAVEL FILE", lines)

with open(path, 'rb') as f:
    pdf_data = f.read()

text = document_processor.simple_pdf_extract(pdf_data)
print("--- EXTRACTED TEXT FROM NEW PDF ---")
print(text)
