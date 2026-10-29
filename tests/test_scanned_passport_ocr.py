"""
Khanna Travels Vault V3 - Real-World Scanned Passport OCR & Extraction Test Suite
Comprehensive automated test suite for bilingual Indian passports, rotated scans (90/180/270 deg),
flatbed scanner margins, MRZ character recovery, label protection, and zero cloud leaks.
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
from unittest.mock import patch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import ocr_service
import document_processor
import mrz_parser
import pypdf

PROD_DB_PATH = os.path.join(PROJECT_ROOT, "data", "kt_vault_v3.db")
PROD_DOCS_DIR = os.path.join(PROJECT_ROOT, "documents")


def render_synthetic_image(text_lines, width=1200, height=800, rotation_deg=0, margin_padding=0):
    """
    Renders text onto a white bitmap and exports JPEG bytes using Windows System.Drawing.
    Supports rotation (90, 180, 270) and simulated flatbed scanner margins.
    Guarantees no dependency on blocked Python .pyd native libraries like Pillow.
    """
    total_w = width + (2 * margin_padding)
    total_h = height + (2 * margin_padding)

    ps_script_path = os.path.join(tempfile.gettempdir(), f"gen_pass_{os.getpid()}_{abs(hash(''.join(text_lines))) % 100000}.ps1")
    out_img_path = os.path.join(tempfile.gettempdir(), f"rendered_pass_{os.getpid()}_{abs(hash(''.join(text_lines))) % 100000}.jpg")
    out_img_esc = out_img_path.replace("\\", "/")

    # Escape lines for PowerShell heredoc
    text_block = "\n".join(text_lines).replace("'", "''")

    rot_cmd = ""
    if rotation_deg == 90:
        rot_cmd = "$bmp.RotateFlip([System.Drawing.RotateFlipType]::Rotate90FlipNone)"
    elif rotation_deg == 180:
        rot_cmd = "$bmp.RotateFlip([System.Drawing.RotateFlipType]::Rotate180FlipNone)"
    elif rotation_deg == 270:
        rot_cmd = "$bmp.RotateFlip([System.Drawing.RotateFlipType]::Rotate270FlipNone)"

    ps_content = f"""Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap {total_w}, {total_h}
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)

# Draw darker border simulating flatbed scanner background if margins exist
if ({margin_padding} -gt 0) {{
    $bgBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(240, 240, 240))
    $g.FillRectangle($bgBrush, 0, 0, {total_w}, {total_h})
    $pageBrush = [System.Drawing.Brushes]::White
    $g.FillRectangle($pageBrush, {margin_padding}, {margin_padding}, {width}, {height})
}}

$fontHeader = New-Object System.Drawing.Font('Arial', 16, [System.Drawing.FontStyle]::Bold)
$fontBody = New-Object System.Drawing.Font('Arial', 14, [System.Drawing.FontStyle]::Regular)
$fontMrz = New-Object System.Drawing.Font('Consolas', 15, [System.Drawing.FontStyle]::Bold)
$brush = [System.Drawing.Brushes]::Black

$yOffset = {margin_padding} + 30.0
$lines = @'
{text_block}
'@ -split "`n"

foreach ($line in $lines) {{
    $trimmed = $line.Trim()
    if ($trimmed.Length -eq 0) {{ continue }}
    if ($trimmed.StartsWith("P<") -or $trimmed -match '^[A-Z0-9<]{40,44}$') {{
        $g.DrawString($trimmed, $fontMrz, $brush, ({margin_padding} + 30.0), $yOffset)
        $yOffset += 32.0
    }} elseif ($trimmed -match 'PASSPORT|REPUBLIC OF INDIA') {{
        $g.DrawString($trimmed, $fontHeader, $brush, ({margin_padding} + 30.0), $yOffset)
        $yOffset += 36.0
    }} else {{
        $g.DrawString($trimmed, $fontBody, $brush, ({margin_padding} + 30.0), $yOffset)
        $yOffset += 28.0
    }}
}}

$g.Dispose()
{rot_cmd}
$bmp.Save('{out_img_esc}', [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bmp.Dispose()
"""
    try:
        with open(ps_script_path, "w", encoding="utf-8") as f:
            f.write(ps_content)
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script_path],
            check=True,
            capture_output=True,
            timeout=15
        )
        with open(out_img_path, "rb") as f:
            data = f.read()
        return data
    finally:
        for p in (ps_script_path, out_img_path):
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass


def create_scanned_pdf(jpg_bytes, width=1200, height=800):
    """Wraps raw JPEG bytes into a standard image-only PDF container."""
    img_len = len(jpg_bytes)
    content_stream = f"q\n{width} 0 0 {height} 0 0 cm\n/Im1 Do\nQ\n"
    content_bytes = content_stream.encode("latin1")

    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n".encode("latin1")
    obj4_header = f"4 0 obj\n<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {img_len} >>\nstream\n".encode("latin1")
    obj4_footer = b"\nendstream\nendobj\n"
    obj5 = f"5 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n{content_stream}endstream\nendobj\n".encode("latin1")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in [obj1, obj2, obj3]:
        offsets.append(len(pdf))
        pdf.extend(obj)
    offsets.append(len(pdf))
    pdf.extend(obj4_header)
    pdf.extend(jpg_bytes)
    pdf.extend(obj4_footer)
    offsets.append(len(pdf))
    pdf.extend(obj5)

    startxref = len(pdf)
    xref = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    for i in range(1, len(offsets)):
        xref += f"{offsets[i]:010d} 00000 n \n"
    pdf.extend(xref.encode("latin1"))

    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{startxref}\n%%EOF\n"
    pdf.extend(trailer.encode("latin1"))
    return bytes(pdf)


class TestScannedPassportOCR(unittest.TestCase):
    """
    Validation test suite for real-world scanned Indian passport PDFs.
    Tests orientation handling, bilingual labels, check digits, margin cropping,
    and label protection.
    """

    @classmethod
    def setUpClass(cls):
        import sqlite3
        cls.sqlite3 = sqlite3
        cls.initial_prod_db_size = os.path.getsize(PROD_DB_PATH)
        with open(PROD_DB_PATH, "rb") as f:
            cls.initial_prod_db_sha256 = hashlib.sha256(f.read()).hexdigest().lower()
        cls.initial_doc_count = len([f for f in os.listdir(PROD_DOCS_DIR) if not f.startswith(".")])

        # Standard synthetic test passport lines
        cls.passport_lines_upright = [
            "PASSPORT / PASSEPORT",
            "REPUBLIC OF INDIA",
            "Passport No: Z1234567",
            "Surname: SHARMA",
            "Given Name: RAHUL",
            "Nationality: Indian",
            "Date of Birth: 15/08/1985",
            "Sex: M",
            "Place of Issue: DELHI",
            "Date of Issue: 10/01/2020",
            "Date of Expiry: 09/01/2030",
            "",
            "P<INDSHARMA<<RAHUL<<<<<<<<<<<<<<<<<<<<<<<<<<",
            "Z1234567<1IND8508155M3001097<<<<<<<<<<<<<<02"
        ]

    def test_01_bilingual_indian_passport_text_parsing(self):
        """01. Verify exact parsing of bilingual Indian passport text (Devanagari labels)."""
        text = """
        भारत गणराज्य / REPUBLIC OF INDIA
        पासपोर्ट / PASSPORT
        प्रकार / Type: P   देश का कोड / Country Code: IND
        पासपोर्ट सं. / Passport No.
        Z1234567
        उपनाम / Surname
        SHARMA
        दिया गया नाम / Given Name(s)
        RAHUL
        राष्ट्रीयता / Nationality
        INDIAN
        लिंग / Sex
        M
        जन्म तिथि / Date of Birth
        15/08/1985
        जारी करने का स्थान / Place of Issue
        DELHI
        जारी करने की तिथि / Date of Issue
        10/01/2020
        समाप्ति की तिथि / Date of Expiry
        09/01/2030

        P<INDSHARMA<<RAHUL<<<<<<<<<<<<<<<<<<<<<<<<<<
        Z1234567<1IND8508155M3001097<<<<<<<<<<<<<<02
        """
        data, conf, doc_type, type_conf = document_processor.parse_passport_text(text)
        self.assertEqual(doc_type, "Passport")
        self.assertEqual(type_conf, "high")
        self.assertEqual(data["Full Name"], "RAHUL SHARMA")
        self.assertEqual(conf["Full Name"], "high")
        self.assertEqual(data["Passport Number"], "Z1234567")
        self.assertEqual(conf["Passport Number"], "high")
        self.assertEqual(data["Date of Birth"], "15 Aug 1985")
        self.assertEqual(data["Expiry Date"], "09 Jan 2030")
        self.assertIn(data["Nationality"], ("Indian", "INDIAN"))
        self.assertEqual(data["Place of Issue"], "DELHI")

    def test_02_upright_scanned_pdf_ocr(self):
        """02. Verify end-to-end OCR and extraction from an upright scanned PDF."""
        jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=0)
        pdf = create_scanned_pdf(jpg)
        res = document_processor.process_document("passport_scan_upright.pdf", pdf)
        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["source_type"], "ocr")
        fields = res["extracted_fields"]
        self.assertEqual(fields["Full Name"], "RAHUL SHARMA")
        self.assertEqual(fields["Passport Number"], "Z1234567")
        self.assertEqual(res["confidence"]["Passport Number"], "high")

    def test_03_rotated_90_scanned_pdf_ocr(self):
        """03. Verify automatic rotation correction and extraction on 90 deg rotated scan."""
        jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=90)
        pdf = create_scanned_pdf(jpg, width=800, height=1200)
        res = document_processor.process_document("passport_scan_rot90.pdf", pdf)
        self.assertEqual(res["document_type"], "Passport")
        fields = res["extracted_fields"]
        self.assertEqual(fields["Full Name"], "RAHUL SHARMA")
        self.assertEqual(fields["Passport Number"], "Z1234567")

    def test_04_rotated_180_scanned_pdf_ocr(self):
        """04. Verify automatic rotation correction on 180 deg upside-down scan."""
        jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=180)
        pdf = create_scanned_pdf(jpg)
        res = document_processor.process_document("passport_scan_rot180.pdf", pdf)
        self.assertEqual(res["document_type"], "Passport")
        fields = res["extracted_fields"]
        self.assertEqual(fields["Full Name"], "RAHUL SHARMA")
        self.assertEqual(fields["Passport Number"], "Z1234567")

    def test_05_rotated_270_scanned_pdf_ocr(self):
        """05. Verify automatic rotation correction on 270 deg scan."""
        jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=270)
        pdf = create_scanned_pdf(jpg, width=800, height=1200)
        res = document_processor.process_document("passport_scan_rot270.pdf", pdf)
        self.assertEqual(res["document_type"], "Passport")
        fields = res["extracted_fields"]
        self.assertEqual(fields["Full Name"], "RAHUL SHARMA")
        self.assertEqual(fields["Passport Number"], "Z1234567")

    def test_06_flatbed_margins_auto_cropping(self):
        """06. Verify scanner margin auto-cropping isolates document region."""
        # 100px padding around 1200x800 page
        jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=0, margin_padding=100)
        pdf = create_scanned_pdf(jpg, width=1400, height=1000)
        res = document_processor.process_document("passport_scan_margins.pdf", pdf)
        self.assertEqual(res["document_type"], "Passport")
        fields = res["extracted_fields"]
        self.assertEqual(fields["Passport Number"], "Z1234567")
        self.assertEqual(fields["Full Name"], "RAHUL SHARMA")

    def test_07_passport_label_protection_and_blacklist(self):
        """07. Verify that 'PASSPORT' or label words are NEVER assigned as passport numbers."""
        noisy_text = """
        GOVERNMENT OF INDIA
        PASSPORT
        Passport No.
        Type: P
        Details: Travel Record
        Surname: KAPOOR
        Given Name: ANITA
        """
        data, conf, doc_type, _ = document_processor.parse_passport_text(noisy_text)
        self.assertEqual(doc_type, "Passport")
        # Passport number must NOT be 'PASSPORT' or 'PASSPORTNO' or 'Type: P'
        self.assertNotEqual(data["Passport Number"].upper(), "PASSPORT")
        self.assertNotEqual(data["Passport Number"].upper(), "TYPE: P")
        self.assertEqual(data["Passport Number"], "")
        self.assertEqual(conf["Passport Number"], "low")
        self.assertEqual(data["Full Name"], "ANITA KAPOOR")

    def test_08_mrz_lookalike_recovery_and_checksum(self):
        """08. Verify MRZ lookalike recovery ('O'->'0', '('->'<') validates check digits."""
        corrupted_mrz = """
        PASSPORT
        P(INDSHARMA((RAHUL((((((((((((((((((((((((((
        Z1234567<1IND85O8155M3001O97<<<<<<<<<<<<<<02
        """
        res = mrz_parser.parse_td3_mrz(corrupted_mrz)
        self.assertTrue(res["success"])
        self.assertEqual(res["fields"]["full_name"], "RAHUL SHARMA")
        self.assertEqual(res["fields"]["document_number"], "Z1234567")
        self.assertEqual(res["fields"]["dob_formatted"], "15 Aug 1985")
        self.assertEqual(res["fields"]["expiry_formatted"], "09 Jan 2030")

    def test_09_multipage_pdf_processing(self):
        """09. Verify multipage PDF correctly extracts passport from page 1."""
        jpg1 = render_synthetic_image(self.passport_lines_upright, rotation_deg=0)
        pdf1 = create_scanned_pdf(jpg1)

        # Build 2-page PDF
        writer = pypdf.PdfWriter()
        r1 = pypdf.PdfReader(io.BytesIO(pdf1))
        writer.add_page(r1.pages[0])
        writer.add_page(r1.pages[0])
        buf = io.BytesIO()
        writer.write(buf)
        two_page_pdf = buf.getvalue()

        res = document_processor.process_document("two_page_passport.pdf", two_page_pdf)
        self.assertEqual(res["document_type"], "Passport")
        self.assertEqual(res["extracted_fields"]["Passport Number"], "Z1234567")

    def test_10_zero_cloud_or_external_network_transmissions(self):
        """10. Verify that OCR pipeline executes 100% offline with zero external network calls."""
        import socket
        real_connect = socket.socket.connect

        def blocked_connect(self, *args, **kwargs):
            raise AssertionError("Security violation: External network connection attempted during local OCR!")

        with patch.object(socket.socket, 'connect', blocked_connect):
            jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=0)
            res = ocr_service.extract_text(jpg, "offline_test.jpg")
            self.assertTrue(res["success"])
            self.assertTrue("Z1234567" in res["raw_text"] or "21234567" in res["raw_text"])

    def test_11_zero_pii_in_logs(self):
        """11. Verify that sensitive passport numbers and traveller names are not logged."""
        import logging
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        logger = logging.getLogger("kt_vault.ocr")
        logger.addHandler(handler)
        try:
            jpg = render_synthetic_image(self.passport_lines_upright, rotation_deg=0)
            ocr_service.extract_text(jpg, "pii_audit.jpg")
            logs = log_stream.getvalue()
            self.assertNotIn("Z1234567", logs, "Passport number leaked into logs!")
            self.assertNotIn("RAHUL SHARMA", logs, "Traveller name leaked into logs!")
        finally:
            logger.removeHandler(handler)

    def test_12_production_database_and_documents_untouched(self):
        """12. Verify production database hash and document vault count remain completely unchanged."""
        self.assertTrue(os.path.exists(PROD_DB_PATH), "Production DB not found!")
        self.assertEqual(os.path.getsize(PROD_DB_PATH), self.initial_prod_db_size, "Production DB size changed!")
        with open(PROD_DB_PATH, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest().lower()
        self.assertEqual(h, self.initial_prod_db_sha256, "Production DB SHA-256 changed!")

        files = [f for f in os.listdir(PROD_DOCS_DIR) if not f.startswith(".")]
        self.assertEqual(len(files), self.initial_doc_count, "Document vault count changed!")

        conn = self.sqlite3.connect(f"file:{PROD_DB_PATH}?mode=ro", uri=True)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchall(), [('ok',)])
        conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
