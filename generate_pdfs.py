from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import os

def generate_pdf(path, title, lines):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, title)
    
    # Warning Watermark / Text
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0.8, 0.2, 0.2)
    c.drawString(50, height - 80, "DEMO / SAMPLE / NOT A REAL DOCUMENT")
    
    # Reset color for content
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 12)
    
    y = height - 120
    for line in lines:
        if line.startswith("!"):  # Warning lines
            c.setFont("Helvetica-Bold", 12)
            c.setFillColorRGB(0.8, 0.2, 0.2)
            c.drawString(50, y, line[1:])
            c.setFillColorRGB(0, 0, 0)
            c.setFont("Helvetica", 12)
        elif ":" in line:
            parts = line.split(":", 1)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, parts[0] + ":")
            c.setFont("Helvetica", 12)
            c.drawString(200, y, parts[1].strip())
        else:
            c.setFont("Helvetica", 12)
            c.drawString(50, y, line)
        y -= 25
        
    c.save()

os.makedirs('documents', exist_ok=True)

# 1. Visa / Entry Document
generate_pdf("documents/02_Amit_Mehta_Demo_Visa_Entry.pdf", "VISA / ENTRY DOCUMENT", [
    "Reference: DXB-DEMO-VISA-26001",
    "Traveller: Amit Mehta",
    "Destination: Dubai, UAE",
    "Purpose: Holiday - Demo",
    "Travel Dates: 12 Dec 2026 - 18 Dec 2026",
    "!No government seal, MRZ, QR, barcode, emblem or security design."
])

# 2. Flight Ticket
generate_pdf("documents/03_Dubai_Flight_Ticket.pdf", "FLIGHT TICKET", [
    "Passenger: Amit Mehta",
    "Booking Reference: KTDEMO-DXB-4812",
    "Route: Mumbai - Dubai - Mumbai",
    "Outbound: 12 Dec 2026",
    "Return: 18 Dec 2026",
    "Cabin: Economy - Demo"
])

# 3. Hotel Voucher
generate_pdf("documents/04_Dubai_Hotel_Voucher.pdf", "HOTEL VOUCHER", [
    "Guest: Amit Mehta",
    "Hotel: Demo Marina Grand Hotel",
    "City: Dubai, UAE",
    "Check-in: 12 Dec 2026",
    "Check-out: 18 Dec 2026",
    "Nights: 6",
    "Booking Reference: KT-HOTEL-DXB-26012"
])

# 4. Travel Insurance
generate_pdf("documents/05_Travel_Insurance.pdf", "TRAVEL INSURANCE", [
    "Traveller: Amit Mehta",
    "Certificate: KT-INS-DEMO-202612",
    "Destination: UAE - Demo",
    "Coverage: 12 Dec 2026 - 18 Dec 2026",
    "!NO REAL INSURANCE COVERAGE EXISTS."
])

# 5. Transfer Voucher
generate_pdf("documents/06_Transfer_Voucher.pdf", "TRANSFER VOUCHER", [
    "Traveller: Amit Mehta",
    "Reference: KT-TRF-DXB-1201",
    "Arrival: Dubai Airport -> Demo Marina Grand Hotel",
    "Date: 12 Dec 2026",
    "Departure: Demo Marina Grand Hotel -> Dubai Airport",
    "Date: 18 Dec 2026"
])

# 6. Sightseeing Voucher
generate_pdf("documents/07_Sightseeing_Voucher.pdf", "SIGHTSEEING VOUCHER", [
    "Traveller: Amit Mehta",
    "Reference: KT-SIGHT-DXB-7781",
    "Activity: Dubai City Highlights Tour - Demo",
    "Activity Date: 14 Dec 2026",
    "Guests: 1 Adult"
])

# 7. Arrival / Entry Document
generate_pdf("documents/08_Arrival_Entry_Document.pdf", "ARRIVAL / ENTRY DOCUMENT", [
    "Traveller: Amit Mehta",
    "Trip: Dubai Holiday",
    "Arrival Date: 12 Dec 2026",
    "Destination: Dubai, UAE",
    "Reference: KT-ARRIVAL-DEMO-001",
    "!NOT AN OFFICIAL IMMIGRATION OR GOVERNMENT DOCUMENT."
])

# 8. Itinerary
generate_pdf("documents/09_Dubai_Itinerary.pdf", "ITINERARY", [
    "12 Dec: Arrival / hotel transfer",
    "13 Dec: Leisure",
    "14 Dec: Dubai City Highlights Tour",
    "15 Dec: Leisure / optional activities",
    "16 Dec: Leisure",
    "17 Dec: Final full day",
    "18 Dec: Checkout / airport transfer / return flight"
])

print("Generated 8 PDFs.")
