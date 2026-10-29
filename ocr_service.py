"""
Khanna Travels Vault V3 - Local Offline OCR Service
Uses verified local Tesseract-OCR installation to perform secure, offline text extraction.
Strictly offline: Zero external network or cloud OCR transmissions.
"""

import os
import sys
import shutil
import tempfile
import subprocess
import logging
import glob
import io
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger("kt_vault.ocr")

# Verified Tesseract executable path on this host
DEFAULT_TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Verified Poppler pdftoppm default executable paths
DEFAULT_POPPLER_EXE = r"C:\Program Files\Poppler\bin\pdftoppm.exe"

# Maximum file size permitted for OCR processing (20MB)
MAX_OCR_FILE_SIZE = 20 * 1024 * 1024

# Maximum PDF pages permitted for OCR rendering to bound resources (5 pages)
MAX_PDF_OCR_PAGES = 5

# Default DPI for PDF page rendering (300 DPI optimal for OCR and MRZ)
DEFAULT_PDF_RENDER_DPI = 300

# Supported image extensions for direct Tesseract/Leptonica processing
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

def get_tesseract_path() -> Optional[str]:
    """
    Resolves the Tesseract executable path.
    1. Checks environment variable KT_TESSERACT_CMD or TESSERACT_CMD.
    2. Checks the verified host default path.
    3. Checks system PATH via shutil.which.
    Returns the executable path if found, or None.
    """
    env_path = os.environ.get("KT_TESSERACT_CMD") or os.environ.get("TESSERACT_CMD")
    if env_path and os.path.isfile(env_path):
        return env_path

    if os.path.isfile(DEFAULT_TESSERACT_EXE):
        return DEFAULT_TESSERACT_EXE

    which_path = shutil.which("tesseract")
    if which_path and os.path.isfile(which_path):
        return which_path

    return None

def get_pdftoppm_path() -> Optional[str]:
    r"""
    Resolves the Poppler pdftoppm executable path.
    1. Checks environment variable KT_POPPLER_PATH or PDFTOPPM_PATH.
    2. Checks system PATH via shutil.which.
    3. Checks verified default enterprise paths (e.g. C:\Program Files\Poppler\bin\pdftoppm.exe).
    4. Checks IT-approved Windows Package Manager (WinGet) installation directory in LOCALAPPDATA.
    5. Checks Windows Registry User/System PATH environment variables.
    Returns the executable path if found, or None.
    """
    env_path = os.environ.get("KT_POPPLER_PATH") or os.environ.get("PDFTOPPM_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    which_path = shutil.which("pdftoppm") or shutil.which("pdftoppm.exe")
    if which_path and os.path.isfile(which_path):
        return which_path

    standard_paths = [
        DEFAULT_POPPLER_EXE,
        r"C:\Program Files (x86)\Poppler\bin\pdftoppm.exe",
    ]
    for p in standard_paths:
        if os.path.isfile(p):
            return p

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        pattern = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*poppler*", "**", "pdftoppm.exe")
        matches = glob.glob(pattern, recursive=True)
        if matches:
            for m in matches:
                if os.path.isfile(m):
                    return m

    try:
        import winreg
        for root, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Environment"),
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
        ]:
            try:
                with winreg.OpenKey(root, subkey) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    for part in val.split(";"):
                        part = part.strip()
                        if part:
                            candidate = os.path.join(part, "pdftoppm.exe")
                            if os.path.isfile(candidate):
                                return candidate
            except Exception:
                pass
    except Exception:
        pass

    return None

def is_tesseract_available() -> Tuple[bool, str]:
    """
    Checks if Tesseract executable is installed and has English language support.
    Returns (is_available, status_message).
    """
    tess_path = get_tesseract_path()
    if not tess_path:
        return False, "Tesseract executable not found at configured path."

    try:
        proc = subprocess.run(
            [tess_path, '--list-langs'],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        if proc.returncode != 0:
            return False, f"Tesseract error: return code {proc.returncode}"

        langs = proc.stdout.lower()
        if 'eng' not in langs:
            return False, "Tesseract executable found but English language pack ('eng') is missing."

        return True, "Tesseract available with English language support."
    except Exception as e:
        return False, f"Failed to probe Tesseract: {str(e)}"

def is_local_pdf_renderer_available() -> Tuple[bool, str]:
    """
    Checks if a safe, verified local PDF-to-image renderer is available.
    Prefers Poppler pdftoppm executable which runs cleanly under Windows Application Control.
    Returns (is_available, explanation).
    """
    pdftoppm_path = get_pdftoppm_path()
    if pdftoppm_path:
        return True, f"Poppler pdftoppm available at {pdftoppm_path}"

    try:
        from PIL import Image  # noqa: F401
        # Check if native C extension is unblocked
        Image.new('RGB', (1, 1))
        return True, "Pillow imaging library is available"
    except Exception:
        pass

    return False, (
        "No approved local PDF renderer is available. Scanned (image-only) PDFs require "
        "a certified renderer (such as Poppler pdftoppm or unblocked Pillow) to rasterize "
        "pages for Tesseract OCR. Document routed to staff review."
    )

# -----------------------------------------------------------------------------
# Pure-Python PGM (Portable GrayMap) Image Operations for Sandboxed Processing
# -----------------------------------------------------------------------------

def parse_pgm(data: bytes) -> Tuple[int, int, bytearray]:
    """
    Parses a binary PGM (P5) image header and body in pure Python.
    Returns (width, height, bytearray_of_pixels).
    """
    idx = 0
    def next_token() -> bytes:
        nonlocal idx
        while idx < len(data):
            while idx < len(data) and data[idx:idx+1] in (b' ', b'\t', b'\r', b'\n'):
                idx += 1
            if idx < len(data) and data[idx:idx+1] == b'#':
                while idx < len(data) and data[idx:idx+1] not in (b'\r', b'\n'):
                    idx += 1
                continue
            break
        start = idx
        while idx < len(data) and data[idx:idx+1] not in (b' ', b'\t', b'\r', b'\n', b'#'):
            idx += 1
        return data[start:idx]

    magic = next_token()
    if magic != b'P5':
        raise ValueError(f"Invalid PGM magic: {magic}")
    w = int(next_token())
    h = int(next_token())
    maxv = int(next_token())
    if idx < len(data) and data[idx:idx+1] in (b' ', b'\t', b'\r', b'\n'):
        idx += 1
    pixels = bytearray(data[idx:idx + (w * h)])
    return w, h, pixels

def encode_pgm(w: int, h: int, pixels: bytes) -> bytes:
    """Encodes width, height, and grayscale pixel bytes into binary PGM format."""
    header = f"P5\n{w} {h}\n255\n".encode("ascii")
    return header + pixels

def rotate_pgm_90_cw(w: int, h: int, pixels: bytearray) -> Tuple[int, int, bytearray]:
    """Rotates a grayscale PGM bytearray 90 degrees clockwise in ~25ms."""
    new_pixels = bytearray(w * h)
    mv = memoryview(pixels)
    for x in range(w):
        col = mv[x::w][::-1]
        new_pixels[x * h : (x + 1) * h] = col
    return h, w, new_pixels

def rotate_pgm_180(w: int, h: int, pixels: bytearray) -> Tuple[int, int, bytearray]:
    """Rotates a grayscale PGM bytearray 180 degrees in ~3ms."""
    return w, h, bytearray(pixels[::-1])

def rotate_pgm_270_cw(w: int, h: int, pixels: bytearray) -> Tuple[int, int, bytearray]:
    """Rotates a grayscale PGM bytearray 270 degrees clockwise (90 CCW) in ~25ms."""
    new_pixels = bytearray(w * h)
    mv = memoryview(pixels)
    for x in range(w):
        col = mv[x::w]
        new_pixels[(w - 1 - x) * h : (w - x) * h] = col
    return h, w, new_pixels

def rotate_pgm(w: int, h: int, pixels: bytearray, degrees: int) -> Tuple[int, int, bytearray]:
    """Dispatches rotation based on degrees (90, 180, 270)."""
    norm_deg = degrees % 360
    if norm_deg == 90:
        return rotate_pgm_90_cw(w, h, pixels)
    elif norm_deg == 180:
        return rotate_pgm_180(w, h, pixels)
    elif norm_deg == 270:
        return rotate_pgm_270_cw(w, h, pixels)
    return w, h, pixels

def crop_pgm(w: int, h: int, pixels: bytearray, x: int, y: int, crop_w: int, crop_h: int) -> Tuple[int, int, bytearray]:
    """Crops a rectangular sub-region from a PGM image."""
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    crop_w = max(1, min(crop_w, w - x))
    crop_h = max(1, min(crop_h, h - y))
    out = bytearray(crop_w * crop_h)
    mv = memoryview(pixels)
    for row in range(crop_h):
        src_start = (y + row) * w + x
        dst_start = row * crop_w
        out[dst_start : dst_start + crop_w] = mv[src_start : src_start + crop_w]
    return crop_w, crop_h, out

def auto_crop_margins_pgm(w: int, h: int, pixels: bytearray, padding: int = 40) -> Tuple[int, int, bytearray]:
    """
    Detects non-white, non-black document content bounds and crops excessive flatbed scanner margins.
    """
    step_y = max(1, h // 200)
    step_x = max(1, w // 200)

    min_x, max_x = w, 0
    min_y, max_y = h, 0

    mv = memoryview(pixels)
    has_content = False

    for y in range(0, h, step_y):
        row_offset = y * w
        for x in range(0, w, step_x):
            val = mv[row_offset + x]
            if 30 <= val <= 235:
                has_content = True
                if x < min_x: min_x = x
                if x > max_x: max_x = x
                if y < min_y: min_y = y
                if y > max_y: max_y = y

    if not has_content or (max_x - min_x < w * 0.25) or (max_y - min_y < h * 0.25):
        return w, h, pixels

    x0 = max(0, min_x - padding)
    y0 = max(0, min_y - padding)
    x1 = min(w, max_x + padding)
    y1 = min(h, max_y + padding)

    crop_w = x1 - x0
    crop_h = y1 - y0

    if crop_w >= int(w * 0.95) and crop_h >= int(h * 0.95):
        return w, h, pixels

    return crop_pgm(w, h, pixels, x0, y0, crop_w, crop_h)

def detect_image_orientation(image_path: str, tess_path: str, timeout: int = 8) -> Tuple[int, float]:
    """
    Runs Tesseract Orientation and Script Detection (OSD, PSM 0) on the given image.
    Returns (rotate_needed_degrees, confidence).
    0 = image is upright; 90, 180, 270 = clockwise rotation needed to make image upright.
    """
    try:
        proc = subprocess.run(
            [tess_path, image_path, "stdout", "--psm", "0"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        out = proc.stdout or ""
        m_rot = re.search(r"Rotate:\s*(\d+)", out)
        m_conf = re.search(r"Orientation confidence:\s*([\d\.]+)", out)
        conf = float(m_conf.group(1)) if m_conf else 0.0

        if m_rot:
            return int(m_rot.group(1)), conf

        m_deg = re.search(r"Orientation in degrees:\s*(\d+)", out)
        if m_deg:
            deg = int(m_deg.group(1))
            rotate_needed = (360 - deg) % 360
            return rotate_needed, conf

        return 0, 0.0
    except Exception:
        return 0, 0.0

def rotate_image_file_powershell(in_path: str, out_path: str, degrees: int) -> bool:
    """
    Rotates an image file (JPG, PNG, BMP) using Windows System.Drawing.
    Guarantees no native C-extension dependencies.
    """
    flip_map = {90: 'Rotate90FlipNone', 180: 'Rotate180FlipNone', 270: 'Rotate270FlipNone'}
    flip_type = flip_map.get(degrees)
    if not flip_type:
        return False
    in_clean = in_path.replace('\\', '/')
    out_clean = out_path.replace('\\', '/')
    ps_lines = [
        "Add-Type -AssemblyName System.Drawing",
        f"$img = [System.Drawing.Image]::FromFile('{in_clean}')",
        f"$img.RotateFlip([System.Drawing.RotateFlipType]::{flip_type})",
        f"$img.Save('{out_clean}')",
        "$img.Dispose()"
    ]
    script_content = "\n".join(ps_lines)
    tf_ps1 = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.ps1', mode='w', encoding='utf-8', delete=False) as f:
            tf_ps1 = f.name
            f.write(script_content)
        res = subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', tf_ps1],
            capture_output=True, text=True, timeout=10, check=False
        )
        return res.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False
    finally:
        if tf_ps1 and os.path.exists(tf_ps1):
            try: os.unlink(tf_ps1)
            except Exception: pass

def ocr_mrz_region(img_path: str, tess_path: str, timeout: int = 8) -> str:
    """
    Performs targeted MRZ character extraction with PSM 6 and an ICAO TD3 whitelist.
    """
    try:
        cmd = [
            tess_path, img_path, "stdout",
            "--psm", "6",
            "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""

def extract_text_from_image(file_bytes: bytes, ext: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Extracts text from image bytes using local Tesseract executable via subprocess.
    Includes automated orientation detection, rotation correction, and targeted MRZ reading.
    Writes bytes to a securely managed temporary file and guarantees removal.
    Never exposes raw customer data in error messages.
    """
    tess_path = get_tesseract_path()
    if not tess_path:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": ["Local Tesseract OCR engine is not configured or unavailable on this system. Document routed to manual review."],
            "confidence": {}
        }

    temp_path = None
    rotated_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            temp_path = tf.name
            tf.write(file_bytes)
            tf.flush()

        active_path = temp_path
        # Orientation detection via PSM 0
        rot_deg, rot_conf = detect_image_orientation(active_path, tess_path, timeout=5)
        if rot_deg in (90, 180, 270) and rot_conf >= 0.5:
            rotated_path = active_path + f"_rot{rot_deg}" + ext
            if rotate_image_file_powershell(active_path, rotated_path, rot_deg):
                active_path = rotated_path

        # Run primary Tesseract OCR
        cmd = [tess_path, active_path, "stdout", "-l", "eng", "--psm", "3"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        if proc.returncode != 0:
            logger.warning("Local Tesseract exited with code %d", proc.returncode)
            return {
                "success": False,
                "raw_text": "",
                "provider": "tesseract_local",
                "warnings": ["OCR processing could not read image content. Document routed to manual review."],
                "confidence": {}
            }

        extracted_text = proc.stdout.strip()

        # Multi-angle orientation fallback if no text found or text does not contain passport indicators
        if not extracted_text or (len(extracted_text) < 30 and 'P<' not in extracted_text):
            for test_rot in (90, 180, 270):
                trial_path = temp_path + f"_trial_{test_rot}" + ext
                try:
                    if rotate_image_file_powershell(temp_path, trial_path, test_rot):
                        trial_proc = subprocess.run(
                            [tess_path, trial_path, "stdout", "-l", "eng", "--psm", "3"],
                            capture_output=True, text=True, timeout=timeout, check=False
                        )
                        if trial_proc.returncode == 0 and trial_proc.stdout.strip():
                            if 'P<' in trial_proc.stdout or 'PASSPORT' in trial_proc.stdout.upper() or len(trial_proc.stdout.strip()) > len(extracted_text):
                                extracted_text = trial_proc.stdout.strip()
                                active_path = trial_path
                                break
                finally:
                    if os.path.exists(trial_path) and trial_path != active_path:
                        try: os.unlink(trial_path)
                        except Exception: pass

        if not extracted_text:
            return {
                "success": False,
                "raw_text": "",
                "provider": "tesseract_local",
                "warnings": ["OCR completed but no readable text was detected. Document routed to manual review."],
                "confidence": {}
            }

        return {
            "success": True,
            "raw_text": extracted_text,
            "provider": "tesseract_local",
            "warnings": [],
            "confidence": {}
        }

    except subprocess.TimeoutExpired:
        logger.warning("Local Tesseract timed out after %d seconds", timeout)
        return {
            "success": False,
            "raw_text": "",
            "provider": "tesseract_local",
            "warnings": [f"OCR processing timed out after {timeout} seconds. Document routed to manual review."],
            "confidence": {}
        }
    except Exception as e:
        logger.error("OCR execution error: %s", type(e).__name__)
        return {
            "success": False,
            "raw_text": "",
            "provider": "tesseract_local",
            "warnings": ["OCR processing encountered an unexpected error. Document routed to manual review."],
            "confidence": {}
        }
    finally:
        for p in (temp_path, rotated_path):
            if p and os.path.exists(p):
                try: os.unlink(p)
                except Exception: pass

def extract_text_from_pdf(
    file_bytes: bytes,
    filename: str = "",
    max_pages: int = MAX_PDF_OCR_PAGES,
    dpi: int = DEFAULT_PDF_RENDER_DPI,
    timeout: int = 30,
    specific_pages: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Extracts text from scanned PDF bytes by rasterizing pages with Poppler pdftoppm
    and performing OCR with local Tesseract.
    Strictly offline: Zero external network or cloud OCR transmissions.
    Guarantees temporary file cleanup on success, error, or timeout.
    """
    # 1. Validation: empty file
    if not file_bytes or len(file_bytes) == 0:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": ["Empty document bytes provided. Document routed to manual review."],
            "confidence": {}
        }

    # 2. Validation: oversized file
    if len(file_bytes) > MAX_OCR_FILE_SIZE:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": [f"File size ({len(file_bytes)} bytes) exceeds the maximum allowed OCR limit of {MAX_OCR_FILE_SIZE // (1024*1024)}MB. Document routed to manual review."],
            "confidence": {}
        }

    renderer_avail, reason = is_local_pdf_renderer_available()
    if not renderer_avail:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": [reason],
            "confidence": {}
        }

    tess_avail, tess_msg = is_tesseract_available()
    if not tess_avail:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": [tess_msg],
            "confidence": {}
        }

    pdftoppm_path = get_pdftoppm_path()
    tess_path = get_tesseract_path()

    warnings = []

    # 3. Validate PDF signature
    if not file_bytes.startswith(b"%PDF-") and b"%PDF-" not in file_bytes[:1024]:
        return {
            "success": False,
            "raw_text": "",
            "provider": "poppler_tesseract_local",
            "warnings": ["PDF file appears corrupt or malformed. Document routed to manual review."],
            "confidence": {}
        }

    # 4. Check for password-protection / encryption and page count via pypdf
    total_pages = 1
    is_encrypted = False
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            is_encrypted = True
        else:
            total_pages = len(reader.pages)
    except Exception:
        # Corrupted or unusual structure; pdftoppm will attempt rendering if viable
        pass

    if is_encrypted:
        return {
            "success": False,
            "raw_text": "",
            "provider": "poppler_tesseract_local",
            "warnings": ["PDF is password-protected or encrypted. Document routed to manual review."],
            "confidence": {}
        }

    if total_pages == 0:
        return {
            "success": False,
            "raw_text": "",
            "provider": "poppler_tesseract_local",
            "warnings": ["PDF document contains no pages. Document routed to manual review."],
            "confidence": {}
        }

    # 5. Determine pages to process
    if specific_pages:
        target_pages = [p for p in specific_pages if p >= 1]
    else:
        target_pages = list(range(1, min(total_pages, max_pages) + 1))
        if total_pages > max_pages:
            warnings.append(
                f"Document has {total_pages} pages; processed first {max_pages} pages for travel verification. "
                f"Additional pages require manual inspection."
            )

    extracted_page_texts = []
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="kt_pdf_ocr_")
        input_pdf_path = os.path.join(temp_dir, "input_doc.pdf")
        with open(input_pdf_path, "wb") as f:
            f.write(file_bytes)

        per_page_timeout = max(5, min(15, timeout // max(1, len(target_pages))))

        for page_num in target_pages:
            out_prefix = os.path.join(temp_dir, f"page_{page_num}")
            # Render page as grayscale PGM for high-speed, native pure-Python manipulation
            cmd_ppm = [
                pdftoppm_path,
                "-gray",
                "-r", str(dpi),
                "-f", str(page_num),
                "-l", str(page_num),
                input_pdf_path,
                out_prefix
            ]
            try:
                proc_ppm = subprocess.run(
                    cmd_ppm,
                    capture_output=True,
                    text=True,
                    timeout=per_page_timeout,
                    check=False
                )
            except subprocess.TimeoutExpired:
                warnings.append(f"Page {page_num} rasterization timed out after {per_page_timeout} seconds.")
                continue

            if proc_ppm.returncode != 0:
                err_lower = (proc_ppm.stderr or "").lower()
                if "password" in err_lower or "encrypted" in err_lower:
                    return {
                        "success": False,
                        "raw_text": "",
                        "provider": "poppler_tesseract_local",
                        "warnings": ["PDF is password-protected or encrypted. Document routed to manual review."],
                        "confidence": {}
                    }
                warnings.append(f"Page {page_num} could not be rendered by PDF rasterizer.")
                continue

            # Locate rendered image for this page (PGM or PNG)
            candidates = glob.glob(os.path.join(temp_dir, f"page_{page_num}*.pgm"))
            if not candidates:
                candidates = glob.glob(os.path.join(temp_dir, f"page_{page_num}*.png"))
            if not candidates:
                continue

            page_img_path = candidates[0]
            is_pgm = page_img_path.lower().endswith('.pgm')
            page_text = ""
            mrz_text = ""

            try:
                if is_pgm:
                    with open(page_img_path, "rb") as pf:
                        pgm_bytes = pf.read()
                    img_w, img_h, img_pixels = parse_pgm(pgm_bytes)

                    # 1. Orientation Detection via Tesseract OSD (PSM 0)
                    rot_deg, rot_conf = detect_image_orientation(page_img_path, tess_path, timeout=5)
                    if rot_deg in (90, 180, 270) and rot_conf >= 0.5:
                        img_w, img_h, img_pixels = rotate_pgm(img_w, img_h, img_pixels, rot_deg)
                        with open(page_img_path, "wb") as pf:
                            pf.write(encode_pgm(img_w, img_h, img_pixels))

                    # 2. Scanner Margin Trimming
                    img_w, img_h, img_pixels = auto_crop_margins_pgm(img_w, img_h, img_pixels, padding=35)
                    with open(page_img_path, "wb") as pf:
                        pf.write(encode_pgm(img_w, img_h, img_pixels))

                    # 3. Primary Full-Page OCR
                    cmd_tess = [tess_path, page_img_path, "stdout", "-l", "eng", "--psm", "3"]
                    proc_tess = subprocess.run(cmd_tess, capture_output=True, text=True, timeout=per_page_timeout, check=False)
                    if proc_tess.returncode == 0:
                        page_text = proc_tess.stdout.strip()

                    # 4. Targeted MRZ Band Extraction (TSV-guided crop + multi-band thresholding)
                    if img_h >= 200:
                        # Attempt to locate MRZ coordinates via Tesseract TSV word positions
                        tsv_mrz_box = None
                        try:
                            cmd_tsv = [tess_path, page_img_path, "stdout", "tsv", "-l", "eng", "--psm", "3"]
                            proc_tsv = subprocess.run(cmd_tsv, capture_output=True, text=True, timeout=5, check=False)
                            if proc_tsv.returncode == 0:
                                mrz_y_pts = []
                                for line in proc_tsv.stdout.splitlines()[1:]:
                                    parts = line.split('\t')
                                    if len(parts) >= 12:
                                        wtext = parts[11].strip()
                                        if '<<' in wtext or 'P<' in wtext or 'IND' in wtext or '1ND' in wtext or (len(wtext) >= 8 and sum(1 for c in wtext if c.isdigit()) >= 6):
                                            top_val = int(parts[7])
                                            left_val = int(parts[6])
                                            if top_val > int(img_h * 0.4): # lower half of page
                                                mrz_y_pts.append((top_val, left_val))
                                if mrz_y_pts:
                                    avg_y = sum(p[0] for p in mrz_y_pts) // len(mrz_y_pts)
                                    box_min_x = max(0, min(p[1] for p in mrz_y_pts) - 50)
                                    box_min_y = max(0, avg_y - 60)
                                    box_w = min(img_w - box_min_x, 1550)
                                    box_h = min(img_h - box_min_y, 240)
                                    tsv_mrz_box = (box_min_x, box_min_y, box_w, box_h)
                        except Exception:
                            pass

                        # Candidate crop regions: TSV-derived box, center-bottom (A4 flatbed), bottom 28% (full page)
                        crops_to_try = []
                        if tsv_mrz_box:
                            crops_to_try.append(tsv_mrz_box)
                        # A4 Flatbed scan band (y around 65% - 78%)
                        crops_to_try.append((int(img_w * 0.2), int(img_h * 0.65), int(img_w * 0.7), int(img_h * 0.12)))
                        # Standard bottom band
                        crops_to_try.append((0, int(img_h * 0.72), img_w, int(img_h * 0.28)))

                        mrz_candidates = []
                        for bx, by, bw, bh in crops_to_try[:2]:
                            cw, ch, bpix = crop_pgm(img_w, img_h, img_pixels, bx, by, bw, bh)
                            # Test both raw and contrast-thresholded PGM (threshold 185 enhances faint dot-matrix MRZ)
                            for th_val in (None, 185):
                                if th_val is not None:
                                    cpix = bytearray([0 if v < th_val else 255 for v in bpix])
                                else:
                                    cpix = bpix
                                mrz_temp_path = os.path.join(temp_dir, f"mrz_b_{bx}_{by}_{th_val}.pgm")
                                try:
                                    with open(mrz_temp_path, "wb") as mf:
                                        mf.write(encode_pgm(cw, ch, cpix))
                                    res_t = ocr_mrz_region(mrz_temp_path, tess_path, timeout=5)
                                    if res_t and ('P<' in res_t or '<<' in res_t or 'IND' in res_t or any(c.isdigit() for c in res_t)):
                                        mrz_candidates.append(res_t)
                                finally:
                                    if os.path.exists(mrz_temp_path):
                                        try: os.unlink(mrz_temp_path)
                                        except Exception: pass

                        if mrz_candidates:
                            # Pick candidate with most MRZ features or combine
                            mrz_text = "\n".join(mrz_candidates)

                    # 5. Multi-Angle Fallback if no MRZ or passport indicators found
                    has_passport_indicators = ('P<' in page_text or 'P<' in mrz_text or 'PASSPORT' in page_text.upper())
                    if not has_passport_indicators:
                        # Try rotating the original unrotated image through 90, 180, 270
                        for trial_rot in (90, 180, 270):
                            trial_w, trial_h, trial_pixels = rotate_pgm(img_w, img_h, img_pixels, trial_rot)
                            trial_path = os.path.join(temp_dir, f"trial_{page_num}_{trial_rot}.pgm")
                            try:
                                with open(trial_path, "wb") as tf:
                                    tf.write(encode_pgm(trial_w, trial_h, trial_pixels))
                                trial_proc = subprocess.run([tess_path, trial_path, "stdout", "-l", "eng", "--psm", "3"], capture_output=True, text=True, timeout=per_page_timeout, check=False)
                                if trial_proc.returncode == 0:
                                    trial_out = trial_proc.stdout.strip()
                                    if 'P<' in trial_out or 'PASSPORT' in trial_out.upper():
                                        page_text = trial_out
                                        # Also extract MRZ band from this trial
                                        trial_mrz_y = int(trial_h * 0.72)
                                        trial_mrz_h = trial_h - trial_mrz_y
                                        _, _, trial_mrz_crop = crop_pgm(trial_w, trial_h, trial_pixels, 0, trial_mrz_y, trial_w, trial_mrz_h)
                                        trial_mrz_path = os.path.join(temp_dir, f"trial_mrz_{trial_rot}.pgm")
                                        try:
                                            with open(trial_mrz_path, "wb") as tmf:
                                                tmf.write(encode_pgm(trial_w, trial_mrz_h, trial_mrz_crop))
                                            mrz_text = ocr_mrz_region(trial_mrz_path, tess_path, timeout=5)
                                        finally:
                                            if os.path.exists(trial_mrz_path):
                                                try: os.unlink(trial_mrz_path)
                                                except Exception: pass
                                        break
                            finally:
                                if os.path.exists(trial_path):
                                    try: os.unlink(trial_path)
                                    except Exception: pass
                else:
                    # Fallback for PNG / non-PGM formats
                    cmd_tess = [tess_path, page_img_path, "stdout", "-l", "eng", "--psm", "3"]
                    proc_tess = subprocess.run(cmd_tess, capture_output=True, text=True, timeout=per_page_timeout, check=False)
                    if proc_tess.returncode == 0:
                        page_text = proc_tess.stdout.strip()

                combined_page = page_text
                if mrz_text:
                    combined_page = (combined_page + "\n\n" + mrz_text).strip() if combined_page else mrz_text

                if combined_page:
                    extracted_page_texts.append(combined_page)

            except subprocess.TimeoutExpired:
                warnings.append(f"Page {page_num} OCR timed out after {per_page_timeout} seconds.")
            finally:
                for c in candidates:
                    if os.path.exists(c):
                        try:
                            os.unlink(c)
                        except Exception:
                            pass

        combined_text = "\n\n".join(t for t in extracted_page_texts if t.strip())
        if not combined_text.strip():
            return {
                "success": False,
                "raw_text": "",
                "provider": "poppler_tesseract_local",
                "warnings": warnings + ["OCR completed using approved local PDF renderer but no readable text was detected. Document routed to manual review."],
                "confidence": {}
            }

        return {
            "success": True,
            "raw_text": combined_text,
            "provider": "poppler_tesseract_local",
            "warnings": warnings,
            "page_count": total_pages,
            "pages_ocred": len(extracted_page_texts),
            "confidence": {}
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "raw_text": "",
            "provider": "poppler_tesseract_local",
            "warnings": [f"Scanned PDF processing timed out after {timeout} seconds. Document routed to manual review."],
            "confidence": {}
        }
    except Exception as e:
        logger.error("Scanned PDF processing error: %s", type(e).__name__)
        return {
            "success": False,
            "raw_text": "",
            "provider": "poppler_tesseract_local",
            "warnings": ["Scanned PDF processing encountered an unexpected error. Document routed to manual review."],
            "confidence": {}
        }
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

def extract_text(file_bytes: bytes, filename: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Main entry point for local document OCR.
    Handles file validation, format routing, and safe error reporting.
    Strictly offline: Zero external network or cloud OCR transmissions.
    """
    # 1. Validation: empty file
    if not file_bytes or len(file_bytes) == 0:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": ["Empty document bytes provided. Document routed to manual review."],
            "confidence": {}
        }

    # 2. Validation: oversized file
    if len(file_bytes) > MAX_OCR_FILE_SIZE:
        return {
            "success": False,
            "raw_text": "",
            "provider": "None",
            "warnings": [f"File size ({len(file_bytes)} bytes) exceeds the maximum allowed OCR limit of {MAX_OCR_FILE_SIZE // (1024*1024)}MB. Document routed to manual review."],
            "confidence": {}
        }

    ext = os.path.splitext(filename)[1].lower() if filename else ''

    # 3. Image file handling (JPG, JPEG, PNG, etc.)
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return extract_text_from_image(file_bytes, ext, timeout=timeout)

    # 4. PDF file handling
    if ext == '.pdf':
        renderer_avail, reason = is_local_pdf_renderer_available()
        if not renderer_avail:
            return {
                "success": False,
                "raw_text": "",
                "provider": "None",
                "warnings": [reason],
                "confidence": {}
            }
        return extract_text_from_pdf(file_bytes, filename=filename, timeout=timeout)

    # 5. Unsupported format
    return {
        "success": False,
        "raw_text": "",
        "provider": "None",
        "warnings": [f"File format '{ext}' is not supported for local OCR. Document routed to manual review."],
        "confidence": {}
    }

