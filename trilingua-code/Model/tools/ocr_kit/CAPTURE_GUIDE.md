# One-page capture and reference guide

Collect 36 actual distinct documents: 3 languages (English, Cebuano, Filipino) x 3 acquisition classes (scan, photo, screenshot) x 4 documents per slice. Recommended starting collection target: at least 125 checked words/document, 500 words/slice. These are collection targets, not new gate thresholds or proof of representativeness. Add difficult captions, small print, tables, columns and mixed native/image pages deliberately.

Use 2 documents for calibration and 2 for held-out per slice. Keep every page, crop, screenshot, near-duplicate and translation of the same content in the same content group/split. Freeze held-out material before trying preprocessing. Do not convert a digital rendering into a claimed real scan/photo. Generated test fixtures are diagnostic only.

- **Scans:** actual paper scanned at 300 DPI or higher; page flat, edges complete, no clipping. Save a lossless PNG or an image-only PDF. Record the actual device/settings and acquirer in the rights note or accompanying notes.
- **Photos:** actual camera capture; even diffuse lighting, no glare/shadow across words, camera parallel to the flat page, all corners visible, steady focus. Preserve the original full-resolution image; avoid messaging-app recompression. Include representative imperfect photos separately from clean scans.
- **Screenshots:** actual source UI/browser/app at native resolution; capture the complete intended text, avoid rescaling, save PNG. Aim for at least 1200 pixels across the content where practical and legible body text at 100% zoom. Include representative smaller screenshots; do not inflate them and call that extra detail.

Files: one source PDF/PNG/JPEG, matching UTF-8 `.txt`, checked `.regions.json`, and one `info.csv` row per document. PDF boxes use300-DPI pixels; image boxes use full EXIF-transposed resolution. All regions must be included, in reading order, with exact punctuation, case, ñ and diacritics. Do not silently normalize recognition errors away.

The first person transcribes the entire source and records region boxes/order. A different person checks the text and geometry against the original, explicitly confirms or corrects each case, records their actual name/date/attestation, and resolves uncertainty before signing off. Neither OCR output nor a tool-generated score substitutes for that check. Keep original and corrected reference hashes/provenance.

The owner confirms actual acquisition, rights basis, representativeness and split isolation in the completed review sheet and corpus approval. Do not claim consent, rights or independent review merely because a field exists. Keep private/copyrighted material local and access-controlled. PyMuPDF licensing and font embedding/redistribution remain owner review items; this guide makes no legal determination.
