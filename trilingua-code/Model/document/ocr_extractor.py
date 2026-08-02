# -*- coding: utf-8 -*-
"""
OCR text extractor for scanned/image-based PDFs.

Provides a fallback extraction method when PyMuPDF cannot extract
text from a PDF (e.g., scanned documents, image-based PDFs).

Uses pytesseract (Tesseract OCR) for text extraction.
Requires:
  - pip install pytesseract Pillow
  - Tesseract OCR installed on the system
    (https://github.com/tesseract-ocr/tesseract)
"""

import os
import tempfile


def ocr_extract_pdf(file_path: str, lang: str = "eng") -> list[dict]:
    """Extract text from a PDF using OCR.

    Converts each PDF page to an image, then runs Tesseract OCR
    on each image. Returns blocks in the same format as the
    PyMuPDF extractor for compatibility.

    Args:
        file_path: Path to the PDF file.
        lang: Tesseract language code (default: "eng").

    Returns:
        List of block dicts with 'type', 'text', 'style' keys.
        Returns empty list if OCR fails or is unavailable.
    """
    try:
        import fitz
        from PIL import Image
        import pytesseract
    except ImportError:
        print("  [OCR] pytesseract or PIL not installed. Skipping OCR.")
        return []

    blocks = []
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        print(f"  [OCR] Processing {total_pages} page(s) with Tesseract OCR...")

        for page_num in range(total_pages):
            page = doc[page_num]

            # Render page to image at 300 DPI for good OCR quality
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Run Tesseract OCR
            ocr_data = pytesseract.image_to_data(
                img, lang=lang, output_type=pytesseract.Output.DICT
            )

            # Group recognized text into blocks by block_num
            # Each block_num represents a text block/paragraph
            current_block_num = -1
            current_text = ""

            for i in range(len(ocr_data["text"])):
                text = ocr_data["text"][i].strip()
                block_num = ocr_data["block_num"][i]
                conf = int(ocr_data["conf"][i]) if ocr_data["conf"][i] != "-1" else 0

                # Skip low-confidence text
                if conf < 30:
                    continue

                if not text:
                    # End of current block
                    if current_text and current_block_num >= 0:
                        blocks.append({
                            "type": "paragraph",
                            "text": current_text.strip(),
                            "style": {"font_size": 11, "font": "helv",
                                      "color": 0, "bold": False},
                            "page": page_num,
                        })
                        current_text = ""
                    current_block_num = -1
                    continue

                if block_num != current_block_num:
                    # New block
                    if current_text and current_block_num >= 0:
                        blocks.append({
                            "type": "paragraph",
                            "text": current_text.strip(),
                            "style": {"font_size": 11, "font": "helv",
                                      "color": 0, "bold": False},
                            "page": page_num,
                        })
                    current_block_num = block_num
                    current_text = text
                else:
                    # Continue current block
                    if current_text:
                        current_text += " " + text
                    else:
                        current_text = text

            # Flush last block
            if current_text and current_block_num >= 0:
                blocks.append({
                    "type": "paragraph",
                    "text": current_text.strip(),
                    "style": {"font_size": 11, "font": "helv",
                              "color": 0, "bold": False},
                    "page": page_num,
                })

        doc.close()
        print(f"  [OCR] Extracted {len(blocks)} text block(s) from {total_pages} page(s)")
        return blocks

    except Exception as e:
        print(f"  [OCR] Error during OCR extraction: {e}")
        return []