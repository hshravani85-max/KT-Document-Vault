import travel_file_generator
import pypdf
import os

out_path = 'documents/TravelFile_KT-T-0001_pypdf_test.pdf'
travel_file_generator.generate_consolidated_travel_file('KT-T-0001', out_path=out_path)

print(f"Generated size: {os.path.getsize(out_path)} bytes")

with open(out_path, 'rb') as f:
    reader = pypdf.PdfReader(f)
    print("PDF loaded without warnings.")
    text = reader.pages[0].extract_text()
    
print("--- PYPDF EXTRACTED TEXT ---")
print(text)
print("----------------------------")
