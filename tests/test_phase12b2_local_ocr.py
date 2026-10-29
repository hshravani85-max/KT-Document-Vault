"""
Khanna Travels Vault V3 - Phase 12B-2
Comprehensive Automated Test Suite for Local Offline OCR Integration
"""

import os
import sys
import shutil
import tempfile
import hashlib
import unittest
import subprocess
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import ocr_service
import document_processor

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")

EXPECTED_PROD_DB_SIZE = 167936
EXPECTED_PROD_DB_SHA256 = "d3f0d65d1619b84c3afc9413ede8b5b6b38dc9de3996fc672ec9048a4349a31d"
EXPECTED_DOC_COUNT = 74


def render_synthetic_image_bytes(text: str, fmt: str = 'Png', width: int = 900, height: int = 450) -> bytes:
    """
    Renders text onto a white bitmap and exports image bytes using Windows System.Drawing.
    Guarantees no dependency on blocked Python .pyd native libraries like Pillow.
    """
    ps_file = os.path.join(tempfile.gettempdir(), f'gen_test_{os.getpid()}_{fmt}.ps1')
    out_img = os.path.join(tempfile.gettempdir(), f'rendered_test_{os.getpid()}.{fmt.lower()}')
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
$g.DrawString($text, $font, $brush, 20.0, 20.0)
$g.Dispose()
$bmp.Save('{out_img_escaped}', [System.Drawing.Imaging.ImageFormat]::{fmt})
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


class TestPhase12b2LocalOCR(unittest.TestCase):
    """Test suite covering all Phase 12B-2 local offline OCR requirements."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        # Generate reusable synthetic fixtures once for performance
        cls.passport_text = (
            "PASSPORT\n"
            "Surname: MALHOTRA\n"
            "Given Names: VIKRAM\n"
            "Passport Number: V9876543\n"
            "Date of Birth: 14 Aug 1988\n"
            "Nationality: Indian\n"
            "Expiry Date: 09 Jan 2031\n"
        )
        cls.passport_png_bytes = render_synthetic_image_bytes(cls.passport_text, 'Png')
        cls.passport_jpg_bytes = render_synthetic_image_bytes(cls.passport_text, 'Jpeg')

        cls.visa_text = (
            "VISA / ENTRY DOCUMENT\n"
            "Traveller Name: Vikram Malhotra\n"
            "Visa Number / Reference: DXB-VISA-2026-991\n"
            "Destination: Dubai, UAE\n"
            "Purpose of Visit: Tourist\n"
            "Issue Date: 01 Nov 2026\n"
            "Expiry Date / Valid Until: 31 Dec 2026\n"
        )
        cls.visa_jpg_bytes = render_synthetic_image_bytes(cls.visa_text, 'Jpeg')

        cls.ins_text = (
            "CERTIFICATE OF TRAVEL INSURANCE\n"
            "Insured Name: Vikram Malhotra\n"
            "Policy Number: POL-TRAVEL-2026-774\n"
            "Insurance Provider: Tata AIG General Insurance\n"
            "Valid From: 12 Dec 2026\n"
            "Valid Until: 19 Dec 2026\n"
        )
        cls.ins_jpg_bytes = render_synthetic_image_bytes(cls.ins_text, 'Jpeg')

    # -------------------------------------------------------------
    # 1. Tesseract Executable Detection
    # -------------------------------------------------------------
    def test_01_tesseract_executable_detection(self):
        """01. Verify Tesseract executable path is detected and exists on disk."""
        tess_path = ocr_service.get_tesseract_path()
        self.assertIsNotNone(tess_path, "Tesseract executable path could not be resolved.")
        self.assertTrue(os.path.isfile(tess_path), f"Tesseract binary does not exist at {tess_path}")

    # -------------------------------------------------------------
    # 2. English OCR Availability
    # -------------------------------------------------------------
    def test_02_english_ocr_availability(self):
        """02. Verify Tesseract reports healthy status and English language pack."""
        avail, msg = ocr_service.is_tesseract_available()
        self.assertTrue(avail, f"Tesseract probe failed: {msg}")
        self.assertIn("English", msg)

    # -------------------------------------------------------------
    # 3. Valid Synthetic JPG OCR
    # -------------------------------------------------------------
    def test_03_valid_synthetic_jpg_ocr(self):
        """03. Verify text extraction from a synthetic JPEG document."""
        res = ocr_service.extract_text(self.passport_jpg_bytes, "passport_scan.jpg")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "tesseract_local")
        self.assertIn("MALHOTRA", res["raw_text"])
        self.assertIn("V9876543", res["raw_text"])

    # -------------------------------------------------------------
    # 4. Valid Synthetic PNG OCR
    # -------------------------------------------------------------
    def test_04_valid_synthetic_png_ocr(self):
        """04. Verify text extraction from a synthetic PNG document."""
        res = ocr_service.extract_text(self.passport_png_bytes, "passport_scan.png")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "tesseract_local")
        self.assertIn("VIKRAM", res["raw_text"])
        self.assertIn("09 Jan 2031", res["raw_text"])

    # -------------------------------------------------------------
    # 5. Corrupted Image Handling
    # -------------------------------------------------------------
    def test_05_corrupted_image_handling(self):
        """05. Verify corrupted image bytes fail safely without crashing."""
        corrupted_bytes = b"CORRUPTED_NON_IMAGE_HEADER_BYTES_1234567890"
        res = ocr_service.extract_text(corrupted_bytes, "corrupt_sample.jpg")
        self.assertFalse(res["success"])
        self.assertEqual(res["raw_text"], "")
        self.assertGreater(len(res["warnings"]), 0)
        self.assertIn("manual review", res["warnings"][0].lower())

    # -------------------------------------------------------------
    # 6. Empty OCR Output Handling
    # -------------------------------------------------------------
    def test_06_empty_ocr_output_handling(self):
        """06. Verify empty bytes and blank images fail gracefully with manual review routing."""
        # A. 0-byte file
        res_zero = ocr_service.extract_text(b"", "empty.jpg")
        self.assertFalse(res_zero["success"])
        self.assertIn("Empty document bytes", res_zero["warnings"][0])

        # B. Blank image (pure white canvas with no text)
        blank_png = render_synthetic_image_bytes("   \n   ", 'Png')
        res_blank = ocr_service.extract_text(blank_png, "blank.png")
        self.assertFalse(res_blank["success"])
        self.assertIn("no readable text", res_blank["warnings"][0].lower())

    # -------------------------------------------------------------
    # 7. OCR Timeout Handling
    # -------------------------------------------------------------
    def test_07_ocr_timeout_handling(self):
        """07. Verify bounded timeout handling when subprocess exceeds time limit."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["tesseract"], timeout=0.001)):
            res = ocr_service.extract_text(self.passport_png_bytes, "timeout_test.png", timeout=1)
            self.assertFalse(res["success"])
            self.assertEqual(res["raw_text"], "")
            self.assertTrue(any("timed out" in w.lower() for w in res["warnings"]))

    # -------------------------------------------------------------
    # 8. Missing Tesseract Handling
    # -------------------------------------------------------------
    def test_08_missing_tesseract_handling(self):
        """08. Verify system reports clear manual-review message when Tesseract is missing."""
        with patch("ocr_service.get_tesseract_path", return_value=None):
            res = ocr_service.extract_text(self.passport_png_bytes, "missing_tess.png")
            self.assertFalse(res["success"])
            self.assertEqual(res["provider"], "None")
            self.assertTrue(any("not configured or unavailable" in w for w in res["warnings"]))

    # -------------------------------------------------------------
    # 9. File-Size and Format Validation
    # -------------------------------------------------------------
    def test_09_file_size_and_format_validation(self):
        """09. Verify rejection of oversized files (>20MB) and unsupported formats."""
        # Oversized
        oversized_bytes = b"0" * (21 * 1024 * 1024)
        res_large = ocr_service.extract_text(oversized_bytes, "large.jpg")
        self.assertFalse(res_large["success"])
        self.assertTrue(any("exceeds the maximum" in w for w in res_large["warnings"]))

        # Unsupported format (.docx)
        res_docx = ocr_service.extract_text(b"PK\x03\x04...", "document.docx")
        self.assertFalse(res_docx["success"])
        self.assertTrue(any("not supported" in w for w in res_docx["warnings"]))

    # -------------------------------------------------------------
    # 10. Digital PDF Extraction Regression
    # -------------------------------------------------------------
    def test_10_digital_pdf_extraction_regression(self):
        """10. Verify digital PDF text extraction is preserved and does not call OCR."""
        lines = [
            "DEMO PASSPORT",
            "Full Name: Vikram Malhotra",
            "Passport Number: V9876543",
            "Date of Birth: 14 Aug 1988",
            "Nationality: Indian",
            "Expiry Date: 09 Jan 2031"
        ]
        stream_lines = []
        y = 720
        for l in lines:
            clean = l.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            stream_lines.append(f"BT /F1 10 Tf 50 {y} Td ({clean}) Tj ET")
            y -= 14
        stream_data = "\n".join(stream_lines).encode('latin-1', 'ignore')
        stream_len = len(stream_data)

        pdf_stream = (
            f"%PDF-1.4\n"
            f"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            f"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
            f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode('ascii')
            + stream_data +
            f"\nendstream\nendobj\n"
            f"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
            f"xref\n0 6\n0000000000 65535 f \n"
            f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n500\n%%EOF\n".encode('ascii')
        )
        res = document_processor.process_document("digital_passport.pdf", pdf_stream, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "pdf_text")
        self.assertEqual(res["ocr_provider"], "None")
        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["extracted_fields"]["Full Name"], "Vikram Malhotra")
        self.assertEqual(res["extracted_fields"]["Passport Number"], "V9876543")

    # -------------------------------------------------------------
    # 11. Scanned PDF Safe Unavailable State
    # -------------------------------------------------------------
    def test_11_scanned_pdf_behavior_and_renderer_check(self):
        """11. Verify scanned (image-only) PDF cleanly routes to Needs Review with documented renderer requirement."""
        # Empty text PDF simulates a scanned document
        empty_pdf = (
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
            b"0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n180\n%%EOF\n"
        )
        res = document_processor.process_document("scanned_empty.pdf", empty_pdf, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "manual_required")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertTrue(any("approved local pdf renderer" in w.lower() for w in res["warnings"]))

    # -------------------------------------------------------------
    # 12. Passport Extraction Regression on Image
    # -------------------------------------------------------------
    def test_12_passport_extraction_regression(self):
        """12. Verify Passport image routes through OCR and extracts surname+given combined name."""
        res = document_processor.process_document("passport_test.png", self.passport_png_bytes, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["ocr_provider"], "tesseract_local")
        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["extracted_fields"]["Full Name"], "VIKRAM MALHOTRA")
        self.assertEqual(res["extracted_fields"]["Passport Number"], "V9876543")
        self.assertEqual(res["extracted_fields"]["Date of Birth"], "14 Aug 1988")
        self.assertEqual(res["extracted_fields"]["Expiry Date"], "09 Jan 2031")

    # -------------------------------------------------------------
    # 13. Visa Extraction Regression on Image
    # -------------------------------------------------------------
    def test_13_visa_extraction_regression(self):
        """13. Verify Visa image routes through OCR and cleanly strips compound labels."""
        res = document_processor.process_document("visa_test.jpg", self.visa_jpg_bytes, expected_requirement="Visa / Entry Document")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["document_type"], "Visa / Entry Document")
        self.assertEqual(res["extracted_fields"]["Traveller Name"], "Vikram Malhotra")
        self.assertEqual(res["extracted_fields"]["Visa Number / Reference"], "DXB-VISA-2026-991")
        self.assertEqual(res["extracted_fields"]["Destination"], "Dubai, UAE")
        self.assertEqual(res["extracted_fields"]["Expiry Date / Valid Until"], "31 Dec 2026")

    # -------------------------------------------------------------
    # 14. Insurance Extraction Regression on Image
    # -------------------------------------------------------------
    def test_14_insurance_extraction_regression(self):
        """14. Verify Insurance image routes through OCR and prevents title heading collision."""
        res = document_processor.process_document("insurance_test.jpg", self.ins_jpg_bytes, expected_requirement="Travel Insurance")
        self.assertEqual(res["source_type"], "ocr")
        self.assertEqual(res["document_type"], "Travel Insurance")
        self.assertEqual(res["extracted_fields"]["Insured Name"], "Vikram Malhotra")
        self.assertEqual(res["extracted_fields"]["Policy Number"], "POL-TRAVEL-2026-774")
        self.assertNotEqual(res["extracted_fields"]["Policy Number"], "TRAVEL")
        self.assertEqual(res["extracted_fields"]["Valid From"], "12 Dec 2026")
        self.assertEqual(res["extracted_fields"]["Valid Until"], "19 Dec 2026")

    # -------------------------------------------------------------
    # 15. MRZ Checksum Validation on Image
    # -------------------------------------------------------------
    def test_15_mrz_checksum_validation_on_image(self):
        """15. Verify Passport image with MRZ executes TD3 7-3-1 check digit validation."""
        mrz_img_text = (
            "PASSPORT\n"
            "Surname: MALHOTRA\n"
            "Given Names: VIKRAM\n"
            "Passport Number: V9876543\n"
            "Date of Birth: 14 Aug 1988\n"
            "Nationality: INDIAN\n"
            "Date of Expiry: 09 Jan 2031\n\n"
            "P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04\n"
        )
        img_bytes = render_synthetic_image_bytes(mrz_img_text, 'Png', width=950, height=500)
        res = document_processor.process_document("passport_mrz.png", img_bytes, expected_requirement="Passport")

        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["extracted_fields"]["Full Name"], "VIKRAM MALHOTRA")
        self.assertEqual(res["extracted_fields"]["Passport Number"], "V9876543")
        self.assertEqual(res["confidence"]["Full Name"], "high")
        self.assertEqual(res["confidence"]["Passport Number"], "high")

    # -------------------------------------------------------------
    # 16. VIZ / MRZ Conflict Review on Image
    # -------------------------------------------------------------
    def test_16_viz_mrz_conflict_review(self):
        """16. Verify conflicting VIZ and MRZ preserves VIZ value and logs warning for human review."""
        conflict_text = (
            "PASSPORT\n"
            "Surname: SHARMA\n"
            "Given Names: RAHUL\n"
            "Passport Number: P1122334\n"
            "Date of Birth: 14 Aug 1988\n"
            "Date of Expiry: 09 Jan 2031\n\n"
            "P<INDMALHOTRA<<VIKRAM<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "V9876543<8IND8808144M3101092<<<<<<<<<<<<<<04\n"
        )
        img_bytes = render_synthetic_image_bytes(conflict_text, 'Png', width=950, height=500)
        res = document_processor.process_document("passport_conflict.png", img_bytes, expected_requirement="Passport")

        # VIZ value strictly preserved
        self.assertEqual(res["extracted_fields"]["Full Name"], "RAHUL SHARMA")
        self.assertEqual(res["extracted_fields"]["Passport Number"], "P1122334")
        # Review warning logged
        self.assertTrue(any("Passport name conflict" in w for w in res["warnings"]))

    # -------------------------------------------------------------
    # 17. Cloud OCR Not Called
    # -------------------------------------------------------------
    def test_17_cloud_ocr_not_called(self):
        """17. Verify that zero external network or HTTP requests are attempted during OCR."""
        with patch("urllib.request.urlopen") as mock_url, patch("requests.post") as mock_post:
            res = ocr_service.extract_text(self.passport_png_bytes, "offline_check.png")
            self.assertTrue(res["success"])
            mock_url.assert_not_called()
            mock_post.assert_not_called()

    # -------------------------------------------------------------
    # 18. No Database Changes During OCR
    # -------------------------------------------------------------
    def test_18_no_database_changes_during_ocr(self):
        """18. Verify production database hash and byte size remain completely untouched."""
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha = hashlib.sha256(f.read()).hexdigest().lower()

        self.assertEqual(curr_size, self.initial_prod_db_size, "Database size was modified during test run!")
        self.assertEqual(curr_sha, self.initial_prod_db_sha256, "Database checksum was modified during test run!")
        conn = self.sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()

    # -------------------------------------------------------------
    # 19. Existing Authorization and Verification Behavior
    # -------------------------------------------------------------
    def test_19_existing_authorization_and_verification_behavior(self):
        """19. Verify OCR never auto-verifies documents; human review workflow preserved."""
        res = document_processor.process_document("passport_review.png", self.passport_png_bytes, expected_requirement="Passport")
        # Ensure document structure has no 'Verified' status injected
        self.assertNotIn("status", res)  # Verification status is handled solely by database models
        self.assertIn("extracted_fields", res)
        self.assertIn("warnings", res)

    # -------------------------------------------------------------
    # 20. Temporary File Cleanup
    # -------------------------------------------------------------
    def test_20_temporary_file_cleanup(self):
        """20. Verify temporary files created during OCR are removed in both success and failure paths."""
        tmp_dir = tempfile.gettempdir()
        before_files = set(os.listdir(tmp_dir))

        # Run successful OCR
        ocr_service.extract_text(self.passport_png_bytes, "cleanup_success.png")

        # Run failing OCR
        ocr_service.extract_text(b"CORRUPTED", "cleanup_fail.jpg")

        after_files = set(os.listdir(tmp_dir))
        # No orphan temporary files with .png or .jpg created by ocr_service should linger
        new_leaks = [f for f in (after_files - before_files) if f.startswith("tmp") and (f.endswith(".png") or f.endswith(".jpg"))]
        self.assertEqual(len(new_leaks), 0, f"Temporary file leak detected: {new_leaks}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
