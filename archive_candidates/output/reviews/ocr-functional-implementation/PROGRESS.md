# Functional OCR corrections

Branch: `codex/hybrid-ocr-functional`; base: `6e1f131`; implementation commit: `9d8d3af`.

## Completed engineering
- hOCR word boxes, paragraph/line IDs and actual baselines replace word-bottom inference. Real descenders pass; curved/skewed/missing/nonfinite geometry holds.
- One deterministic uncertain-paragraph 4/3 upscale retry, exact NFC text agreement, all words >=80; inverse-mapped boxes use original RGB pixels. Shared job pixel accounting and a total 60-second OCR allowance cover retries.
- Short-strip letter stems no longer masquerade as long vertical rules. Long table rules and protected neighbors still hold.
- Font comparisons ignore OCR-box background padding. Family/weight remains an estimate among bundled fonts.
- Native paragraphs use line alignment; unchanged text is counted as passthrough and stays editable. Regeneration recomputes the counts.
- Generic prompt clarifications were exercised, did NOT solve the live provider's Cebuano meaning errors, and were reverted; final provider prompts match the starting bytes.
- SETTINGS v3 and renderer algorithm v2 invalidate incompatible acceptance evidence/render plans.

## Checked
- Baseline: 254 Python, 52 PHP (255 assertions), 4 browser checks passed.
- Final code checks: 280 Python, 52 PHP (255 assertions), 4 browser checks passed. Python was rerun after restoring the original prompt:280 passed in65.98s. Automated Python checks deny outbound sockets.
- Actual supplied PDF: source-text-only OCR/reconstruction probe plans both dialogue panels. Page1 retry accepted at minimum confidence85; page2 did not retry, minimum83. This is NOT measured accuracy or an accepted replacement PDF.
- Normal service rerun without cache: HTTP200, one actual configured-provider POST /api/chat HTTP200. 5 translated / 1 passthrough / 4 held. Native paragraphs now left aligned; all image streams/pixels and page geometry unchanged. No OCR gate bypass.
- Real output rendered with Poppler and both pages visually inspected. It remains partial and linguistically unsuitable for publication; the moral appears reversed.
- All pre-existing unrelated tracked bytes and live .env match the starting hash snapshot. No packages installed, services restarted or live acceptance settings changed.

## Remaining - release HOLD
1. Owner supplies genuine representative material, rights basis, complete source text/regions and independent review through the existing OCR kit. No references, attestations or signed acceptance reports were fabricated.
2. Calibrate only on calibration material, then evaluate frozen unseen held-out material at unchanged95% word accuracy. Review missed regions/ordering separately. English-source OCR evidence is required for the supplied English-to-Cebuano file.
3. Qualify the configured translation route with bilingual review. The live fast-mode provider still makes meaning errors despite prompt clarification; no default model was changed.
4. Only after valid evidence and owner release approval: configure durable keys/report/manifest, rerun the normal pipeline and verify actual translated dialogue removal/redraw/searchability, plus Linux/font/licensing parity.

Evidence: baseline-*.log, final-*.log, committed-python.log, diagnostic.json, preservation-final.json, check-commands.json; ordinary cached rerun under output/pdf/lion-mouse-functional-rerun-2026-10-26 and fresh provider rerun under output/pdf/lion-mouse-functional-live-2026-10-26.
