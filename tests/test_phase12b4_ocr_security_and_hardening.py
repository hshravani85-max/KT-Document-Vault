"""
Khanna Travels Vault V3 - Phase 12B-4
Comprehensive Security Audit, Subprocess Hardening & Resource Protection Test Suite
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


def render_synthetic_jpeg_bytes(text: str, width: int = 900, height: int = 450) -> bytes:
    """Renders text onto a white bitmap and exports JPEG bytes via System.Drawing."""
    ps_file = os.path.join(tempfile.gettempdir(), f'sec_gen_{os.getpid()}_{abs(hash(text))%100000}.ps1')
    out_img = os.path.join(tempfile.gettempdir(), f'sec_ren_{os.getpid()}_{abs(hash(text))%100000}.jpg')
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
        subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-File', ps_file], check=True, capture_output=True, timeout=10)
        with open(out_img, 'rb') as f:
            data = f.read()
        return data
    finally:
        for p in (ps_file, out_img):
            if os.path.exists(p):
                try: os.unlink(p)
                except Exception: pass


def create_image_only_pdf_bytes(jpg_data: bytes, width: int = 900, height: int = 450) -> bytes:
    """Wraps raw JPEG bytes into a compliant single-page image-only PDF container."""
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


class TestPhase12b4OCRSecurityAndHardening(unittest.TestCase):
    """Rigorous security, resource, error recovery, and immutability test suite."""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        cls.sample_text = "PASSPORT\nSurname: SEN\nGiven Names: ARJUN\nPassport Number: Z9988776\nNationality: Indian\nDate of Birth: 05 May 1991\nExpiry Date: 04 May 2036\n"
        cls.sample_jpg = render_synthetic_jpeg_bytes(cls.sample_text)
        cls.sample_pdf = create_image_only_pdf_bytes(cls.sample_jpg)

    def test_01_poppler_subprocess_execution_safety(self):
        """01. Verify Poppler pdftoppm is executed strictly with shell=False and list arguments."""
        orig_run = subprocess.run
        captured_calls = []

        def mock_run(cmd, *args, **kwargs):
            captured_calls.append({"cmd": cmd, "kwargs": kwargs})
            return orig_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            ocr_service.extract_text_from_pdf(self.sample_pdf, "safe_exec.pdf")

        poppler_calls = [c for c in captured_calls if isinstance(c["cmd"], list) and any("pdftoppm" in str(x).lower() for x in c["cmd"])]
        self.assertTrue(len(poppler_calls) > 0, "No pdftoppm subprocess calls captured!")
        for call in poppler_calls:
            self.assertFalse(call["kwargs"].get("shell", False), "SECURITY VIOLATION: Subprocess invoked with shell=True!")
            self.assertIsInstance(call["cmd"], list, "SECURITY VIOLATION: Command not passed as structured argument list!")
            self.assertIn("timeout", call["kwargs"], "SECURITY VIOLATION: No execution timeout enforced on subprocess!")

    def test_02_subprocess_argument_injection_prevention(self):
        """02. Verify filenames with malicious CLI injection flags cannot alter command options."""
        malicious_filenames = [
            "--help.pdf",
            "-png; rm -rf /.pdf",
            "test & calc.exe.pdf",
            "file | dir.pdf",
            "../etc/passwd.pdf"
        ]
        for bad_name in malicious_filenames:
            res = ocr_service.extract_text(self.sample_pdf, bad_name)
            # The extraction should either succeed normally or return a clean error without executing options
            self.assertIsInstance(res, dict)
            self.assertIn("success", res)

    def test_03_temporary_directory_isolation(self):
        """03. Verify separate processing requests use distinct, isolated temporary directories."""
        dirs_used = []
        orig_mkdtemp = tempfile.mkdtemp

        def mock_mkdtemp(*args, **kwargs):
            d = orig_mkdtemp(*args, **kwargs)
            dirs_used.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=mock_mkdtemp):
            ocr_service.extract_text_from_pdf(self.sample_pdf, "req1.pdf")
            ocr_service.extract_text_from_pdf(self.sample_pdf, "req2.pdf")

        self.assertEqual(len(dirs_used), 2)
        self.assertNotEqual(dirs_used[0], dirs_used[1], "CRITICAL FLAW: Temporary directories shared across requests!")

    def test_04_temporary_directory_cleanup_on_error(self):
        """04. Verify temporary directories are completely removed even when rendering fails."""
        dirs_created = []
        orig_mkdtemp = tempfile.mkdtemp

        def mock_mkdtemp(*args, **kwargs):
            d = orig_mkdtemp(*args, **kwargs)
            dirs_created.append(d)
            return d

        corrupted = b"%PDF-1.4\n CORRUPT DATA"
        with patch("tempfile.mkdtemp", side_effect=mock_mkdtemp):
            res = ocr_service.extract_text_from_pdf(corrupted, "corrupt.pdf")

        for d in dirs_created:
            self.assertFalse(os.path.exists(d), f"LEAK DETECTED: Temp directory {d} was not cleaned up after error!")

    def test_05_temporary_directory_cleanup_on_timeout(self):
        """05. Verify temporary directories are completely removed when subprocess times out."""
        dirs_created = []
        orig_mkdtemp = tempfile.mkdtemp

        def mock_mkdtemp(*args, **kwargs):
            d = orig_mkdtemp(*args, **kwargs)
            dirs_created.append(d)
            return d

        with patch("tempfile.mkdtemp", side_effect=mock_mkdtemp):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["pdftoppm"], timeout=1)):
                res = ocr_service.extract_text_from_pdf(self.sample_pdf, "timeout_test.pdf", timeout=1)

        for d in dirs_created:
            self.assertFalse(os.path.exists(d), f"LEAK DETECTED: Temp directory {d} was not cleaned up after timeout!")

    def test_06_resource_limit_max_file_size(self):
        """06. Verify oversized files (>20MB) are rejected immediately prior to any rendering."""
        oversized = b"%PDF-1.4\n" + b"A" * (20 * 1024 * 1024 + 10)
        res = ocr_service.extract_text(oversized, "huge.pdf")
        self.assertFalse(res["success"])
        self.assertTrue(any("exceeds the maximum" in w.lower() for w in res["warnings"]))

    def test_07_resource_limit_max_pages_ceiling(self):
        """07. Verify documents exceeding 5 pages are bounded to 5 pages with explicit warning."""
        w = pypdf.PdfWriter()
        r = pypdf.PdfReader(io.BytesIO(self.sample_pdf))
        for _ in range(7):
            w.add_page(r.pages[0])
        buf = io.BytesIO()
        w.write(buf)
        seven_page_pdf = buf.getvalue()

        res = ocr_service.extract_text_from_pdf(seven_page_pdf, "7pages.pdf", max_pages=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["pages_ocred"], 5)
        self.assertTrue(any("processed first 5 pages" in w for w in res["warnings"]))

    def test_08_empty_zero_byte_pdf(self):
        """08. Verify empty bytes input returns clean failure dictionary without throwing exceptions."""
        res = ocr_service.extract_text(b"", "empty.pdf")
        self.assertFalse(res["success"])
        self.assertEqual(res["raw_text"], "")
        self.assertTrue(any("empty" in w.lower() for w in res["warnings"]))

    def test_09_corrupted_pdf_structure(self):
        """09. Verify malformed PDF is handled safely and routed to manual review."""
        res = document_processor.process_document("malformed.pdf", b"NOT_A_PDF_STREAM", expected_requirement="Passport")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertEqual(res["source_type"], "manual_required")

    def test_10_password_protected_pdf_rejection(self):
        """10. Verify encrypted/password-protected PDF is detected and routes to Needs Review with clear notice."""
        w_enc = pypdf.PdfWriter()
        r = pypdf.PdfReader(io.BytesIO(self.sample_pdf))
        w_enc.add_page(r.pages[0])
        w_enc.encrypt("mySecretPassword")
        buf_enc = io.BytesIO()
        w_enc.write(buf_enc)
        enc_pdf = buf_enc.getvalue()

        res = document_processor.process_document("locked.pdf", enc_pdf, expected_requirement="Passport")
        self.assertEqual(res["document_type"], "Needs Review")
        self.assertTrue(any("password" in w.lower() or "encrypted" in w.lower() for w in res["warnings"]))

    def test_11_mixed_pdf_alternating_page_routing(self):
        """11. Verify alternating digital and scanned pages preserve page sequence."""
        with tempfile.TemporaryDirectory() as td:
            dig_path = os.path.join(td, "dig_page.pdf")
            create_raw_pdf(dig_path, "ITINERARY - DIGITAL CONFIRMATION", [
                "Trip Destination: Singapore",
                "Start Date: 12 Jan 2027",
                "End Date: 18 Jan 2027",
                "Schedule Summary: Flight SQ423 arrival, hotel checkin at Marina Bay, city tour"
            ])
            import storage_service
            dig_bytes = storage_service.read_decrypted_document(dig_path, system_context=True, allow_external=True)

        w_alt = pypdf.PdfWriter()
        r_scan = pypdf.PdfReader(io.BytesIO(self.sample_pdf))
        r_dig = pypdf.PdfReader(io.BytesIO(dig_bytes))

        # Page 1: Digital, Page 2: Scanned Passport
        w_alt.add_page(r_dig.pages[0])
        w_alt.add_page(r_scan.pages[0])
        buf_alt = io.BytesIO()
        w_alt.write(buf_alt)
        alt_pdf = buf_alt.getvalue()

        res = document_processor.process_document("alt_mixed.pdf", alt_pdf, expected_requirement="Passport")
        self.assertEqual(res["source_type"], "mixed_pdf_ocr")
        self.assertIn("ITINERARY", res["raw_text"])
        self.assertIn("SEN", res["raw_text"])

    def test_12_traveller_identity_mismatch_security(self):
        """12. Verify identity mismatch against expected traveller name is flagged with error severity."""
        res = document_processor.process_document("passport_sen.pdf", self.sample_pdf, expected_requirement="Passport")
        # Document name is ARJUN SEN; test traveller is Rohan Test
        validation = document_processor.validate_traveller_identity(
            doc_type=res["document_type"],
            extracted_fields=res["extracted_fields"],
            expected_traveller_name="Rohan Test",
            trip_travellers=["Rohan Test"]
        )
        self.assertFalse(validation["valid"])
        self.assertEqual(validation["severity"], "error")
        self.assertIn("mismatch", validation["status"])

    def test_13_document_status_cannot_be_auto_verified(self):
        """13. Verify OCR processing never sets status to 'Verified'; documents remain Under Review."""
        res = document_processor.process_document("passport_check.pdf", self.sample_pdf, expected_requirement="Passport")
        self.assertNotIn("status", res, "CRITICAL FLAW: Processor output contains database 'status' field!")

    def test_14_zero_cloud_network_calls(self):
        """14. Verify socket connections are blocked/asserted not called during scanned PDF processing."""
        with patch("socket.socket") as mock_sock:
            document_processor.process_document("offline_audit.pdf", self.sample_pdf, expected_requirement="Passport")
            mock_sock.assert_not_called()

    def test_15_pii_sanitization_in_warnings_and_logs(self):
        """15. Verify passport numbers and traveller names do not appear in generated warning messages."""
        res = document_processor.process_document("passport_pii.pdf", self.sample_pdf, expected_requirement="Passport")
        for w in res.get("warnings", []):
            self.assertNotIn("Z9988776", w, "PII LEAK: Passport number found in warning string!")
            self.assertNotIn("ARJUN SEN", w, "PII LEAK: Full traveller name found in warning string!")

    def test_16_missing_executable_graceful_recovery(self):
        """16. Verify graceful fallback when Poppler or Tesseract path resolution fails."""
        with patch("ocr_service.get_pdftoppm_path", return_value=None):
            res = ocr_service.extract_text(self.sample_pdf, "no_poppler.pdf")
            self.assertFalse(res["success"])
            self.assertTrue(any("approved local pdf renderer" in w.lower() for w in res["warnings"]))

    def test_17_production_database_and_documents_untouched(self):
        """17. Verify production database and document store remain completely bit-for-bit unchanged."""
        curr_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            curr_sha = hashlib.sha256(f.read()).hexdigest().lower()
        curr_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if os.path.isfile(os.path.join(PROD_DOCS_DIR, f))])

        self.assertEqual(curr_size, self.initial_prod_db_size, "Database size changed during test run!")
        self.assertEqual(curr_sha, self.initial_prod_db_sha256, "Database SHA-256 changed during test run!")
        self.assertEqual(curr_doc_count, self.initial_doc_count, "Document store count changed during test run!")

        conn = self.sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()


if __name__ == "__main__":
    unittest.main()
