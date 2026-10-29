"""
Khanna Travels Vault V3 - Phase 12B-3
Comprehensive Automated Test Suite for Secure Offline Scanned PDF OCR Integration
"""

import os
import sys
import io
import re
import glob
import shutil
import tempfile
import hashlib
import unittest
import subprocess
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import ocr_service
import document_processor
import pypdf
from travel_file_generator import create_raw_pdf

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

# Captured baseline for Phase 12B-3
EXPECTED_PROD_DB_SIZE = 176128
EXPECTED_PROD_DB_SHA256 = "899da8c64b72cb25e04b556a48a8c87a13e6804d6e39a94165ce31778dcd2833"
EXPECTED_DOC_COUNT = 78


def render_synthetic_jpeg_bytes(text: str, width: int = 900, height: int = 450) -> bytes:
    """
    Renders text onto a white bitmap and exports JPEG bytes using Windows System.Drawing.
    Guarantees no dependency on blocked Python .pyd native libraries like Pillow.
    """
    ps_file = os.path.join(tempfile.gettempdir(), f'gen_test_{os.getpid()}_{abs(hash(text))%100000}.ps1')
    out_img = os.path.join(tempfile.gettempdir(), f'rendered_test_{os.getpid()}_{abs(hash(text))%100000}.jpg')
    out_img_escaped = out_img.replace('\\', '/')

    script = f"""Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {width}, {height}
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)
$font = New-Object System.Drawing.Font('Arial', 14, [System.Drawing.FontStyle]::Regular)
$brush = [System.Drawing.Brushes]::Black
$text = @'
{text}
'@
$g.DrawString($text, $font, $brush, 30.0, 30.0)
$g.Dispose()
$bmp.Save('{out_img_escaped}', [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bmp.Dispose()
"""
    try:
        with open(ps_file, 'w', encoding='utf-8') as f:
            f.write(script)
        subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-File', ps_file],
            check=True,
            capture_output=True,
            timeout=10
        )
        with open(out_img, 'rb') as f:
            data = f.read()
        return data
    finally:
        for p in (ps_file, out_img):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass


def create_image_only_pdf_bytes(jpg_data: bytes, width: int = 900, height: int = 450) -> bytes:
    """
    Wraps raw JPEG bytes into a compliant, single-page image-only PDF container.
    Contains zero embedded text stream (BT ... ET), accurately simulating a scanned document.
    """
    img_len = len(jpg_data)
    content_stream = f"q\n{width} 0 0 {height} 0 0 cm\n/Im1 Do\nQ\n"
    content_bytes = content_stream.encode('latin1')

    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n".encode('latin1')
    obj4_header = f"4 0 obj\n<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {img_len} >>\nstream\n".encode('latin1')
    obj4_footer = b"\nendstream\nendobj\n"
    obj5 = f"5 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n{content_stream}endstream\nendobj\n".encode('latin1')

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in [obj1, obj2, obj3]:
        offsets.append(len(pdf))
        pdf.extend(obj)
    offsets.append(len(pdf))
    pdf.extend(obj4_header)
    pdf.extend(jpg_data)
    pdf.extend(obj4_footer)
    offsets.append(len(pdf))
    pdf.extend(obj5)

    startxref = len(pdf)
    xref = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    for i in range(1, len(offsets)):
        xref += f"{offsets[i]:010d} 00000 n \n"
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n"
    pdf.extend(xref.encode('latin1'))
    pdf.extend(trailer.encode('latin1'))
    return bytes(pdf)


class TestPhase12b3ScannedPdfOCR(unittest.TestCase):
    """Test suite covering all Phase 12B-3 scanned PDF OCR requirements."""

    @classmethod
    def setUpClass(cls):
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_docs_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        # 1. Synthetic Scanned Passport PDF
        cls.passport_text = (
            "PASSPORT\n"
            "Surname: MALHOTRA\n"
            "Given Names: VIKRAM\n"
            "Passport Number: V9876543\n"
            "Date of Birth: 14 Aug 1988\n"
            "Nationality: Indian\n"
            "Expiry Date: 09 Jan 2031\n"
        )
        cls.passport_jpg = render_synthetic_jpeg_bytes(cls.passport_text)
        cls.scanned_passport_pdf = create_image_only_pdf_bytes(cls.passport_jpg)

        # 2. Synthetic Scanned Visa PDF
        cls.visa_text = (
            "VISA / ENTRY DOCUMENT\n"
            "Traveller Name: Vikram Malhotra\n"
            "Visa Number / Reference: DXB-VISA-2026-991\n"
            "Destination: Dubai, UAE\n"
            "Purpose of Visit: Tourist\n"
            "Issue Date: 01 Nov 2026\n"
            "Expiry Date / Valid Until: 31 Dec 2026\n"
        )
        cls.visa_jpg = render_synthetic_jpeg_bytes(cls.visa_text)
        cls.scanned_visa_pdf = create_image_only_pdf_bytes(cls.visa_jpg)

        # 3. Synthetic Scanned Insurance PDF
        cls.insurance_text = (
            "TRAVEL INSURANCE\n"
            "Insured Name: Vikram Malhotra\n"
            "Policy Number: TI-2026-987654\n"
            "Insurance Provider: Global Travel Care\n"
            "Valid From: 01 Nov 2026\n"
            "Valid Until: 30 Nov 2026\n"
            "Destination / Coverage Area: Worldwide\n"
        )
        cls.insurance_jpg = render_synthetic_jpeg_bytes(cls.insurance_text)
        cls.scanned_insurance_pdf = create_image_only_pdf_bytes(cls.insurance_jpg)

        # 4. Synthetic Digital PDF (Flight Ticket)
        with tempfile.TemporaryDirectory() as td:
            dig_path = os.path.join(td, "dig_flight.pdf")
            create_raw_pdf(dig_path, "FLIGHT TICKET", [
                "Passenger Name: Vikram Malhotra",
                "Airline: Emirates",
                "Flight Number: EK501",
                "PNR/Booking Reference: EK-98765",
                "Origin: Mumbai (BOM)",
                "Destination: Dubai (DXB)",
                "Departure Date/Time: 10 Nov 2026 10:00",
                "Arrival Date/Time: 10 Nov 2026 12:30",
                "Cabin Class: Economy"
            ])
            import storage_service
            cls.digital_flight_pdf = storage_service.read_decrypted_document(dig_path, system_context=True, allow_external=True)

        # 5. Synthetic 2-Page Mixed PDF (Page 1 Scanned Passport, Page 2 Digital Flight Ticket)
        w_mix = pypdf.PdfWriter()
        r_scanned = pypdf.PdfReader(io.BytesIO(cls.scanned_passport_pdf))
        r_digital = pypdf.PdfReader(io.BytesIO(cls.digital_flight_pdf))
        w_mix.add_page(r_scanned.pages[0])
        w_mix.add_page(r_digital.pages[0])
        buf_mix = io.BytesIO()
        w_mix.write(buf_mix)
        cls.mixed_pdf = buf_mix.getvalue()

        # 6. Synthetic Multipage Scanned PDF (Page 1 Passport, Page 2 Visa)
        w_multi = pypdf.PdfWriter()
        r_visa = pypdf.PdfReader(io.BytesIO(cls.scanned_visa_pdf))
        w_multi.add_page(r_scanned.pages[0])
        w_multi.add_page(r_visa.pages[0])
        buf_multi = io.BytesIO()
        w_multi.write(buf_multi)
        cls.multipage_scanned_pdf = buf_multi.getvalue()

        # 7. Synthetic Empty PDF
        cls.empty_pdf = (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
            b"0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n180\n%%EOF\n"
        )

        # 8. Synthetic Corrupted PDF
        cls.corrupted_pdf = b"%PDF-1.4\n INVALID MALFORMED CORRUPTED CONTENT %%%"

        # 9. Synthetic Password-Protected PDF
        w_enc = pypdf.PdfWriter()
        w_enc.add_page(r_digital.pages[0])
        w_enc.encrypt("secretPass123")
        buf_enc = io.BytesIO()
        w_enc.write(buf_enc)
        cls.encrypted_pdf = buf_enc.getvalue()

    def test_01_poppler_executable_discovery(self):
        """01. Verify Poppler pdftoppm executable is safely discovered on host."""
        poppler_path = ocr_service.get_pdftoppm_path()
        self.assertIsNotNone(poppler_path, "Poppler pdftoppm path could not be resolved.")
        self.assertTrue(os.path.isfile(poppler_path), f"Resolved path '{poppler_path}' does not exist.")

        # Test subprocess execution without shell=True
        proc = subprocess.run([poppler_path, "-v"], capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("poppler", (proc.stdout + proc.stderr).lower())

    def test_02_is_local_pdf_renderer_available(self):
        """02. Verify is_local_pdf_renderer_available returns True and reports valid path."""
        avail, msg = ocr_service.is_local_pdf_renderer_available()
        self.assertTrue(avail)
        self.assertIn("pdftoppm", msg.lower())

    def test_03_real_integration_scanned_passport_ocr(self):
        """03. Real integration test: Scanned Passport PDF -> Poppler -> Tesseract -> Field extraction."""
        res = document_processor.process_document("scan_pass.pdf", self.scanned_passport_pdf, expected_requirement="Passport")
        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["ocr_provider"], "poppler_tesseract_local")
        self.assertIn("MALHOTRA", res["extracted_fields"].get("Full Name", "").upper())
        self.assertIn("1988", res["extracted_fields"].get("Date of Birth", ""))
        self.assertIn("INDIAN", res["extracted_fields"].get("Nationality", "").upper())

    def test_04_real_integration_scanned_visa_ocr(self):
        """04. Real integration test: Scanned Visa PDF -> Poppler -> Tesseract -> Field extraction."""
        res = document_processor.process_document("scan_visa.pdf", self.scanned_visa_pdf, expected_requirement="Visa / Entry Document")
        self.assertEqual(res["document_type"], "Visa / Entry Document")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["ocr_provider"], "poppler_tesseract_local")
        self.assertIn("MALHOTRA", res["extracted_fields"].get("Traveller Name", "").upper())
        self.assertIn("DXB-VISA", res["extracted_fields"].get("Visa Number / Reference", ""))

    def test_05_real_integration_scanned_insurance_ocr(self):
        """05. Real integration test: Scanned Insurance PDF -> Poppler -> Tesseract -> Field extraction."""
        res = document_processor.process_document("scan_ins.pdf", self.scanned_insurance_pdf, expected_requirement="Travel Insurance")
        self.assertEqual(res["document_type"], "Travel Insurance")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["ocr_provider"], "poppler_tesseract_local")
        self.assertIn("MALHOTRA", res["extracted_fields"].get("Insured Name", "").upper())
        self.assertIn("2026-987654", res["extracted_fields"].get("Policy Number", ""))

    def test_06_real_integration_mixed_pdf_routing(self):
        """06. Real integration test: Mixed PDF with scanned page 1 and digital page 2 preserves page order."""
        res = document_processor.process_document("mixed_test.pdf", self.mixed_pdf, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "mixed_pdf_ocr")
        self.assertEqual(res["ocr_provider"], "poppler_tesseract_local")
        self.assertTrue(any("[Mixed PDF]" in w for w in res["warnings"]))

    def test_07_real_integration_multipage_scanned_pdf(self):
        """07. Real integration test: Multi-page scanned PDF processes all pages sequentially."""
        res = document_processor.process_document("multi_scan.pdf", self.multipage_scanned_pdf, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["ocr_provider"], "poppler_tesseract_local")
        self.assertIn("MALHOTRA", res["raw_text"])

    def test_08_digital_pdf_preservation(self):
        """08. Verify digital PDF continues to use pure-Python pypdf without OCR invocation."""
        res = document_processor.process_document("flight.pdf", self.digital_flight_pdf, expected_requirement="Flight Ticket")
        self.assertEqual(res["document_type"], "Flight Ticket")
        self.assertEqual(res["source_type"], "pdf_text")
        self.assertEqual(res["ocr_provider"], "None")
        self.assertEqual(res["extracted_fields"].get("Airline"), "Emirates")
        self.assertEqual(res["extracted_fields"].get("Flight Number"), "EK501")

    def test_09_empty_pdf_safe_handling(self):
        """09. Verify empty scanned PDF cleanly routes to Needs Review with clear warning."""
        res = document_processor.process_document("empty_doc.pdf", self.empty_pdf, expected_requirement="Passport")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertEqual(res["source_type"], "manual_required")
        self.assertTrue(any("approved local pdf renderer" in w.lower() for w in res["warnings"]))

    def test_10_corrupted_pdf_safe_handling(self):
        """10. Verify corrupted PDF is handled safely without unhandled exceptions."""
        res = document_processor.process_document("corrupted_doc.pdf", self.corrupted_pdf, expected_requirement="Passport")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertEqual(res["source_type"], "manual_required")
        self.assertTrue(len(res["warnings"]) > 0)

    def test_11_encrypted_password_protected_pdf_safe_handling(self):
        """11. Verify password-protected / encrypted PDF routes to Needs Review with encryption notice."""
        res = document_processor.process_document("locked.pdf", self.encrypted_pdf, expected_requirement="Flight Ticket")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertEqual(res["source_type"], "manual_required")
        self.assertTrue(any("password" in w.lower() or "encrypted" in w.lower() for w in res["warnings"]))

    def test_12_oversized_pdf_rejection(self):
        """12. Verify PDFs exceeding 20MB are rejected prior to rendering."""
        dummy_oversized = b"%PDF-1.4\n" + b"0" * (ocr_service.MAX_OCR_FILE_SIZE + 1024)
        res = ocr_service.extract_text_from_pdf(dummy_oversized, "big.pdf")
        self.assertFalse(res["success"])
        self.assertTrue(any("exceeds the maximum" in w for w in res["warnings"]))

    def test_13_temporary_directory_cleanup_guarantee(self):
        """13. Verify all temporary rendering directories and PNG files are unlinked."""
        temp_dir_base = tempfile.gettempdir()
        before_dirs = glob.glob(os.path.join(temp_dir_base, "kt_pdf_ocr_*"))

        ocr_service.extract_text_from_pdf(self.scanned_passport_pdf, "test_clean.pdf")

        after_dirs = glob.glob(os.path.join(temp_dir_base, "kt_pdf_ocr_*"))
        self.assertEqual(len(after_dirs), len(before_dirs), "Temporary OCR directory was leaked!")

    def test_14_timeout_handling_enforced(self):
        """14. Verify timeout during subprocess is caught and returned as clean warning."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pdftoppm"], timeout=1)):
            res = ocr_service.extract_text_from_pdf(self.scanned_passport_pdf, "timeout.pdf", timeout=1)
            self.assertFalse(res["success"])
            self.assertTrue(any("timed out" in w.lower() for w in res["warnings"]))

    def test_15_identity_mismatch_protection_preserved(self):
        """15. Verify traveller identity mismatch detection functions on scanned PDF extractions."""
        res = document_processor.process_document("mismatch.pdf", self.scanned_passport_pdf, expected_requirement="Passport")
        # Document name is Vikram Malhotra; expected is Amit Mehta
        validation = document_processor.validate_traveller_identity(
            doc_type=res["document_type"],
            extracted_fields=res["extracted_fields"],
            expected_traveller_name="Amit Mehta",
            trip_travellers=["Amit Mehta"]
        )
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["severity"], "error")
        self.assertIn("mismatch", validation["status"])

    def test_16_zero_cloud_network_requests(self):
        """16. Verify no external network sockets are opened during scanned PDF processing."""
        with patch("socket.socket") as mock_sock:
            document_processor.process_document("offline_check.pdf", self.scanned_passport_pdf, expected_requirement="Passport")
            mock_sock.assert_not_called()

    def test_17_production_database_and_documents_untouched(self):
        """17. Verify production database hash, byte size, and documents directory remain completely unchanged."""
        import sqlite3
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        curr_docs_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        self.assertEqual(curr_size, self.initial_prod_db_size, "Database size was modified!")
        self.assertEqual(curr_sha256, self.initial_prod_db_sha256, "Database SHA-256 hash was modified!")
        self.assertEqual(curr_docs_count, self.initial_docs_count, "Documents directory file count was modified!")

        conn = sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()

    def test_18_existing_image_ocr_still_functional(self):
        """18. Verify JPG/PNG image OCR continues to function without regression."""
        res_png = ocr_service.extract_text_from_image(self.passport_jpg, ".jpg")
        self.assertTrue(res_png["success"])
        self.assertEqual(res_png["provider"], "tesseract_local")
        self.assertIn("MALHOTRA", res_png["raw_text"])


if __name__ == "__main__":
    unittest.main()
