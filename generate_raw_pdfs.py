import os

def create_raw_pdf(path, title, lines):
    # Very basic manual PDF construction
    
    # Calculate stream content
    stream = "BT\n"
    stream += "/F1 18 Tf\n"
    stream += f"50 720 Td\n({title}) Tj\n"
    
    stream += "/F1 14 Tf\n0 -30 Td\n"
    stream += "(DEMO / SAMPLE / NOT A REAL DOCUMENT) Tj\n"
    
    stream += "/F1 12 Tf\n0 -40 Td\n"
    for line in lines:
        clean_line = line.replace("(", "\\(").replace(")", "\\)")
        stream += f"({clean_line}) Tj\n0 -20 Td\n"
    stream += "ET"
    
    stream_bytes = stream.encode('latin1')
    stream_len = len(stream_bytes)
    
    pdf = f'''%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length {stream_len} >>
stream
{stream}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000224 00000 n 
0000000312 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
400
%%EOF'''
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(pdf.encode('latin1'))

# 1. Visa
create_raw_pdf("documents/02_Amit_Mehta_Demo_Visa_Entry.pdf", "VISA / ENTRY DOCUMENT", [
    "Reference: DXB-DEMO-VISA-26001",
    "Traveller: Amit Mehta",
    "Destination: Dubai, UAE",
    "Purpose: Holiday - Demo",
    "Travel Dates: 12 Dec 2026 - 18 Dec 2026",
    "!No government seal, MRZ, QR, barcode, emblem or security design."
])

# 2. Flight Ticket
create_raw_pdf("documents/03_Dubai_Flight_Ticket.pdf", "FLIGHT TICKET", [
    "Passenger: Amit Mehta",
    "Booking Reference: KTDEMO-DXB-4812",
    "Route: Mumbai - Dubai - Mumbai",
    "Outbound: 12 Dec 2026",
    "Return: 18 Dec 2026",
    "Cabin: Economy - Demo"
])

# 3. Hotel Voucher
create_raw_pdf("documents/04_Dubai_Hotel_Voucher.pdf", "HOTEL VOUCHER", [
    "Guest: Amit Mehta",
    "Hotel: Demo Marina Grand Hotel",
    "City: Dubai, UAE",
    "Check-in: 12 Dec 2026",
    "Check-out: 18 Dec 2026",
    "Nights: 6",
    "Booking Reference: KT-HOTEL-DXB-26012"
])

# 4. Travel Insurance
create_raw_pdf("documents/05_Travel_Insurance.pdf", "TRAVEL INSURANCE", [
    "Traveller: Amit Mehta",
    "Certificate: KT-INS-DEMO-202612",
    "Destination: UAE - Demo",
    "Coverage: 12 Dec 2026 - 18 Dec 2026",
    "!NO REAL INSURANCE COVERAGE EXISTS."
])

# 5. Transfer Voucher
create_raw_pdf("documents/06_Transfer_Voucher.pdf", "TRANSFER VOUCHER", [
    "Traveller: Amit Mehta",
    "Reference: KT-TRF-DXB-1201",
    "Arrival: Dubai Airport -> Demo Marina Grand Hotel",
    "Date: 12 Dec 2026",
    "Departure: Demo Marina Grand Hotel -> Dubai Airport",
    "Date: 18 Dec 2026"
])

# 6. Sightseeing Voucher
create_raw_pdf("documents/07_Sightseeing_Voucher.pdf", "SIGHTSEEING VOUCHER", [
    "Traveller: Amit Mehta",
    "Reference: KT-SIGHT-DXB-7781",
    "Activity: Dubai City Highlights Tour - Demo",
    "Activity Date: 14 Dec 2026",
    "Guests: 1 Adult"
])

# 7. Arrival / Entry Document
create_raw_pdf("documents/08_Arrival_Entry_Document.pdf", "ARRIVAL / ENTRY DOCUMENT", [
    "Traveller: Amit Mehta",
    "Trip: Dubai Holiday",
    "Arrival Date: 12 Dec 2026",
    "Destination: Dubai, UAE",
    "Reference: KT-ARRIVAL-DEMO-001",
    "!NOT AN OFFICIAL IMMIGRATION OR GOVERNMENT DOCUMENT."
])

# 8. Itinerary
create_raw_pdf("documents/09_Dubai_Itinerary.pdf", "ITINERARY", [
    "12 Dec: Arrival / hotel transfer",
    "13 Dec: Leisure",
    "14 Dec: Dubai City Highlights Tour",
    "15 Dec: Leisure / optional activities",
    "16 Dec: Leisure",
    "17 Dec: Final full day",
    "18 Dec: Checkout / airport transfer / return flight"
])

print("Raw PDFs created successfully.")
