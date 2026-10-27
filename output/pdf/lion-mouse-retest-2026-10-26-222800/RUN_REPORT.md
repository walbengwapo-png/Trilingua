# Same-file Cebuano pipeline retest

Result: PARTIAL. Required image-text translation did not run because the OCR acceptance gate remains closed. This is a test output, not a publishable translation.

- Input: the supplied Downloads Lion_and_Mouse_2_pages_10_blocks_2_image_text.pdf, unchanged SHA256 `df09eaad8e681a4c5792081db117b38d238f06a9bdadf7c8241b7b0c0b76e34f`.
- Current checkout: `6af226dd3d780492ed5308ed271af6decc016aba`. Original retained prompts; no application or live .env changes.
- Existing FastAPI `/translate/document` service route through in-process TestClient; no external server started. English to Cebuano, fast mode, translation cache disabled for this process.
- HTTP200; elapsed 35.234 seconds. One actual configured GPTOSS request to localhost `/api/chat`, HTTP200,31.453 seconds. No fallback request observed.
- Five native blocks changed; one credit block stayed unchanged. Four raster placements held with `ocr_acceptance_hold`: two illustration placements and two image-text dialogue panels. No raster-text replacement was performed.
- All decoded image pixels, raw image streams, image placement boxes and page geometry match the original. Native paragraphs remain left aligned. Both current output pages were rendered and visually inspected.
- Semantic failure remains: title `Ang Leona ug ang Suso`; moral `Ang kalooy dili gayud malubha.` for `A kindness is never wasted.` These observations do not constitute independent bilingual acceptance.
- Saved render-plan signature and original-file identity verified. Output SHA256 `16792f4527c39c26b2c641f8c431f29254b92688b29b73db2fa6c40c4e48c0f5`.
- A verification helper initially read the previous run folder. Its path was corrected; verification.json and final-checks.json now refer to this actual new output. The live run itself was unaffected.

Evidence in this folder: run-result.json, observed-provider-requests.json, pipeline-response.json, pipeline-run.log, starting-hashes.json, verification.json, final-checks.json, page-1.png and page-2.png.

Remaining: genuine reviewed source-language OCR acceptance evidence, configured translation quality, and an ordinary accepted end-to-end run that actually replaces the image dialogue text. The gate was not disabled, weakened or bypassed.
