# Hybrid OCR preview — 2026-10-27

## Try it locally

1. Start `trilingua-code/start-all.bat`. Existing services must finish and stop before restarting. The launcher now prefers the installed `.venv-ocr-layout` Python environment, including OpenCV.
2. Upload a PDF or PNG/JPEG on the normal translation page.
3. Select English → Cebuano and enable **Try OCR preview (unverified)**.
4. Translate and review the downloaded PDF. Preview warnings also appear in history, documents and admin review.

Preview is opt-in for each upload. Default strict mode still requires the qualifying OCR acceptance report. Preview skips only that report check: runtime/language packs, confidence, fit, geometry, pixel budgets and signed render plans still apply. Preview results cannot be marked production-verified. Preview and strict uploads have different deduplication identities. No `.env` changes or new packages were needed for this task.

## Actual supplied PDF test

Input: `C:\Users\walbe\Downloads\Lion_and_Mouse_2_pages_10_blocks_2_image_text.pdf`.

Output: `output/pdf/lion-mouse-ocr-preview-final-2026-10-27/Lion_and_Mouse_Cebuano_OCR_preview.pdf`.

The real `/translate/document` endpoint ran through an in-process ASGI client, real Tesseract and configured GPTOSS `gpt-oss:20b-cloud`. Translation caching was disabled only in the test process. One observed provider request succeeded; total elapsed time was 38.156 seconds. No external web/API service was started.

Both image-text panels were translated and reconstructed. Summary: 7 translated regions, 2 held illustration placements, 1 passthrough. Status remains partial/unverified because the shared illustration placements are conservatively held. Neither held placement is one of the dialogue panels.

Pixel verification confirmed 31,428 original glyph pixels erased on page 1 and 37,072 on page 2. Pixels outside the masks and both illustration images remained unchanged. Old text-panel image objects are absent from the saved PDF; translated dialogue is searchable PDF text. Page count, page dimensions and rotation are unchanged. Text fits at approximately 15 and 12.8 pt, above the unchanged 10 pt minimum. Both rendered pages were inspected visually. Input bytes remained unchanged.

Evidence is saved beside the output: `run-result.json`, `observed-provider-requests.json`, `verification.json`, `pipeline-response.json`, `page-1.png` and `page-2.png`.

## Root fix and compatibility

The original image replacement safety check rejected the sample's flat page-background drawing, although that drawing was painted before the opaque image. It now checks paint order: earlier drawings covered by the image are allowed, while later or ambiguous overlapping drawings remain held. Image reconstruction algorithm version is now 3; older saved version 1/2 render plans require retranslation. Previously downloaded PDFs remain readable.

OCR mode propagates through upload validation, queued jobs, engine requests, signed plans, regeneration and download labels. Old serialized queued jobs default to strict. Regeneration retains the preview marker without repeating OCR or translation. The regeneration handler now catches structured PDF validation errors before their general ValueError superclass.

## Verification and limits

- 360 Python tests passed, including strict/preview separation, replacement and regeneration, and drawing paint order.
- 80 PHP tests passed (370 assertions), including upload forwarding, deduplication and review restrictions.
- 6 browser tests passed, including checkbox opt-in/reset and preview completion warnings.
- Deployment timeout/migration preflight passed. Queue inspection found no queued work; historical failed jobs were left untouched.

Translation meaning still needs review: some provider wording is poor. Font matching is approximate. Conservative flat-background replacement does not promise support for every scan, shared image, textured background, curved text or outlined vector text. Preview provides behavior testing, not OCR accuracy certification or publication readiness.

Automatic approval review rejected starting local web/API/queue services with only “blocked by policy.” The user must start the updated launcher to exercise the upload UI. Separate controller, queue forwarding, browser and real in-process endpoint checks passed; a running full-stack browser upload was not performed.
