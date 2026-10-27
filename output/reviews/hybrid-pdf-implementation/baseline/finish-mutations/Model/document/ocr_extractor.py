"""Page-level OCR with explicit readiness, evidence gates and source geometry."""
import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

PACKS = {"English": "eng", "Cebuano": "ceb", "Filipino": "fil"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_PIXELS = 40_000_000
SETTINGS = {"version": 2, "dpi": 300, "psm": 3, "grouping": "paragraph-with-word-geometry",
            "preprocessing": "exif-transpose,grayscale,autocontrast", "retain_uncertain_words": True}


class OCRUnavailable(ValueError):
    """A readable input cannot be safely extracted with the configured OCR."""


def tesseract_command():
    configured = os.environ.get("OCR_TESSERACT_CMD")
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    windows = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Tesseract-OCR/tesseract.exe"
    return str(windows) if windows.is_file() else "tesseract"


def readiness():
    """Inventory without any translation-provider request."""
    state = inventory(tesseract_command())
    try:
        import pytesseract
        state["python_package_available"] = True
    except ImportError:
        state["python_package_available"] = False
    state["ready"] = state["available"] and state["python_package_available"]
    return state


def inventory(binary):
    resolved = shutil.which(binary) or (str(Path(binary).resolve()) if Path(binary).is_file() else None)
    if not resolved:
        return {'available': False, 'binary': None, 'installed_packs': None,
                'reason': 'Tesseract executable was not found at the supplied path or on PATH'}
    try:
        version = subprocess.run([resolved, '--version'], capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=15, check=True)
        languages = subprocess.run([resolved, '--list-langs'], capture_output=True, text=True,
                                   encoding='utf-8', errors='replace', timeout=15, check=True)
        output = languages.stdout + languages.stderr
        packs = [line.strip() for line in output.splitlines()
                 if re.fullmatch(r'[A-Za-z0-9_/]+', line.strip())]
        data = {'available': True, 'binary': resolved, 'version': (version.stdout or version.stderr).splitlines()[0],
                'binary_sha256': hashlib.sha256(Path(resolved).read_bytes()).hexdigest(),
                'installed_packs': packs, 'list_languages_output': output, 'pack_sha256': {}}
        match = re.search(r'"([^"]+)"', output)
        if match:
            for pack in packs:
                path = Path(match[1]) / (pack + '.traineddata')
                if path.is_file():
                    data['pack_sha256'][pack] = hashlib.sha256(path.read_bytes()).hexdigest()
        return data
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        return {'available': False, 'binary': resolved, 'installed_packs': None, 'reason': str(exc)}


def require_ready(source_lang, category):
    """Fail closed until this language/category passes the agreed real-input gate."""
    state = readiness()
    pack = PACKS.get(source_lang)
    if not state["ready"]:
        raise OCRUnavailable("OCR runtime unavailable: install Tesseract and pytesseract; check OCR_TESSERACT_CMD.")
    if not pack or pack not in (state.get("installed_packs") or []):
        raise OCRUnavailable(f"OCR language pack unavailable for {source_lang}: required {pack}.")
    try:
        from document.artifact_auth import load_json
        from document.report_trust import verify_report
        report = load_json(os.environ.get('OCR_ACCEPTANCE_REPORT', ''))
        verify_report(report, os.environ.get('OCR_ACCEPTANCE_KEY_FILE', ''),
                      os.environ.get('OCR_CORPUS_MANIFEST', ''), state, source_lang, category)
        accepted = True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError):
        accepted = False
    if not accepted:
        raise OCRUnavailable(f"OCR {source_lang} / {category} is on hold: a representative, checked 95% acceptance report is required.")
    return pack


def prepare_image(image):
    from PIL import Image, ImageOps
    if min(image.size) < 200 or image.width * image.height > MAX_PIXELS:
        raise OCRUnavailable("OCR image must be at least 200 pixels per side and at most 40 megapixels.")
    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        image = Image.alpha_composite(Image.new("RGBA", image.size, "white"), image.convert("RGBA"))
    return ImageOps.autocontrast(image.convert("L"))


def recognize_image(image, pack, page=0, page_size=None):
    """Shared production/evaluation path. Retain uncertain words for review."""
    try:
        import pytesseract
    except ImportError as exc:
        raise OCRUnavailable("OCR requires the pytesseract Python package.") from exc
    image = prepare_image(image)
    pytesseract.pytesseract.tesseract_cmd = tesseract_command()
    try:
        data = pytesseract.image_to_data(image, lang=pack, config="--psm 3 --dpi 300",
                                        output_type=pytesseract.Output.DICT, timeout=60)
    except (RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as exc:
        raise OCRUnavailable(f"OCR failed on page {page + 1}: {exc}") from exc
    width, height = page_size or (image.width * 72 / 300, image.height * 72 / 300)
    sx, sy = width / image.width, height / image.height
    groups = {}
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        try:
            confidence = float(data["conf"][i])
            if not math.isfinite(confidence):
                confidence = -1
        except (ValueError, TypeError):
            confidence = -1
        x, y = data["left"][i] * sx, data["top"][i] * sy
        box = [x, y, x + data["width"][i] * sx, y + data["height"][i] * sy]
        key = (data["block_num"][i], data["par_num"][i])
        groups.setdefault(key, []).append({"text": text, "confidence": confidence, "position": box,
                                          "line": data['line_num'][i], 'paragraph': list(key)})
    blocks = []
    for words in groups.values():
        box = [min(w["position"][0] for w in words), min(w["position"][1] for w in words),
               max(w["position"][2] for w in words), max(w["position"][3] for w in words)]
        blocks.append({"type": "paragraph", "text": " ".join(w["text"] for w in words),
                       "page": page, "position": box, "pdf_coordinates": "display",
                       "style": {"font": "helv", "font_size": 11, "color": 0, "bold": False},
                       "ocr": {"pack": pack, "confidence": sum(w["confidence"] for w in words) / len(words),
                               "words": words, 'reading_order': len(blocks),
                               "uncertain_words": [w for w in words if w["confidence"] < 60]},
                       "ocr_reflow": True})
    if not blocks:
        raise OCRUnavailable(f"OCR found no readable text on page {page + 1}; the page was not silently omitted.")
    return blocks


def extract_image(file_path, source_lang):
    from PIL import Image, UnidentifiedImageError
    # Direct uploads can be phone photos; a clean-scan pass cannot enable them.
    pack = require_ready(source_lang, "photo")
    try:
        with Image.open(file_path) as image:
            expected = "PNG" if Path(file_path).suffix.lower() == ".png" else "JPEG"
            if image.format != expected or getattr(image, "n_frames", 1) != 1:
                raise OCRUnavailable("Upload a single PNG or JPEG image matching its extension.")
            blocks = recognize_image(image, pack)
    except (OSError, Image.DecompressionBombError, UnidentifiedImageError) as exc:
        raise OCRUnavailable(f"Invalid or oversized image: {exc}") from exc
    return blocks, {"pages": [{"page": 0, "classification": "ocr"}],
                    "warnings": ["Image OCR: check extracted text against the original. PDF output uses a separate translated layout."]}


def complete_pdf(file_path, native_blocks, source_lang, column_mode="auto"):
    from document.pdf_regions import inventory_pdf
    return inventory_pdf(file_path, native_blocks, source_lang, column_mode)
