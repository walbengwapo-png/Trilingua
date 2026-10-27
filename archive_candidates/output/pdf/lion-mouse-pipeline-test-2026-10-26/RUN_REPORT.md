# Lion and Mouse: actual pipeline test

Result: **partial English-to-Cebuano output**, not a seamless fully translated document.

## Run and provenance
- Input: C:/Users/walbe/Downloads/Lion_and_Mouse_2_pages_10_blocks_2_image_text.pdf
- Source SHA256: df09eaad8e681a4c5792081db117b38d238f06a9bdadf7c8241b7b0c0b76e34f; original bytes unchanged after execution.
- Output: Lion_and_Mouse_Cebuano_pipeline_partial.pdf
- Existing FastAPI `/translate/document` route executed through an in-process ASGI TestClient, with real DocumentPipeline and configured providers. No externally listening service was started; browser/Laravel upload and database persistence were not exercised.
- Existing `fast` mode, English -> Cebuano. Fast mode disables extra AI analysis/quality review; this run does not test those modes.
- Primary/model: GPT-OSS / gpt-oss:20b-cloud. One observed HTTP POST to the configured localhost `/api/chat` endpoint returned 200 in 78.188 s. No Gemini fallback request was observed. Upstream execution/billing inside the local Ollama endpoint was not independently inspected.
- Service HTTP 200; elapsed 80.718 s. Pipeline validation says geometry/content coverage passed and linguistic accuracy unverified.
- A private operational render-plan key outside the repository was supplied only to the test process because no plan key was configured. The saved plan signature/source binding verifies. No OCR acceptance key/report/manifest was generated, installed or substituted. Application settings and all tracked source hashes match the pre-run snapshot.
- Unrelated import-time provider warmup connections were blocked. Translation and its result were not mocked, manually translated or patched.

## What the pipeline did
| Item | Observed behavior |
|---|---|
| Pages |2 original pages retained, original 612x792 pt dimensions retained, no continuation pages|
| Native content |8 extractable blocks including 2 page numbers; 6 candidate native regions processed|
| Reported content status |6 translated, 4 held, 0 passthrough; source coverage unknown|
| Actual text difference |5 of 6 returned native blocks changed; the credit line stayed identical while still marked translated|
| Image placements |4 placements: the same illustration appears twice, plus 2 dialogue text images|
| Image-text translation |0 image regions translated; both dialogue panels remain English|
| Image preservation |All 4 placements have identical decoded pixels AND identical encoded image streams at the same coordinates|
| Why image OCR stopped |Each image region records `ocr_acceptance_hold`: no genuine signed 95% report is configured. The repeated illustration additionally records shared-resource safety exclusion|

Four held regions are **image placements**, not four confirmed text blocks. Two contain dialogue; the other two are the shared illustration. No recognition/replacement was enabled merely because this sample was supplied.

## Findings from the rendered output
1. **The image gate behaves as designed**, retaining the two English dialogue images. This run provides no evidence that OCR recognition/translation/replacement works on accepted real material, and is not an acceptance corpus or 95% accuracy measurement.
2. **Native alignment is not preserved.** The source paragraphs are left-aligned; rebuilt paragraphs are centred. Longer text expanded from 4 to 6 lines on page 1 and from 5 to 7 on page 2. The moral and credit line also wrap to 2 lines. No clipped or overlapping text was visible in the two rendered pages, but the result differs materially from the original typesetting.
3. **Translation quality is weak in a manual spot-check.** The title is `Ang Leong ug ang Mouse`, leaving Mouse in English. The source moral `A kindness is never wasted.` becomes `Ang kabinantayon dili gayud malugaw.`; this wording appears semantically wrong and needs a bilingual reviewer. No BLEU, human accuracy score or linguistic acceptance is claimed.
4. **The translated-region count is not a changed-text count.** The credit string remains `Aesop | Illustration: Milo Winter (1919) | Source: Project Gutenberg #19994`, yet its region status is translated. This may reflect protection/provider behavior, but must not be presented as six visibly changed translations.

Source and output pages were rendered with Poppler at 110 DPI and visually inspected. Poppler logged the same Symbol/ArialUnicode display-font warnings for source and output; the reviewed pages rendered legibly. Native text remains extractable/searchable; image dialogue remains baked into unchanged pixels.

## Evidence
- source-inspection.json: initial native/image geometry and configuration-presence checks
- pipeline-run.log: actual pipeline progress
- observed-provider-requests.json: actual request statuses/timings, no credentials/payloads
- pipeline-response.json: returned blocks, content status, signed sidecar and validation
- run-result.json: entrypoint/model/status/timing and private-key location only (no key contents)
- verification.json: image-stream/pixel equality, text/geometry and source/config preservation
- original-poppler-1.png, original-poppler-2.png; output-poppler-1.png, output-poppler-2.png

Next engineering work indicated by this sample: correct native alignment inference/reconstruction and improve/validate the translation route's semantic quality. Image-text replacement still requires genuine checked signed acceptance evidence; this sample does not bypass that requirement. No application code was changed during this test.

Result: real configured-provider pipeline produced a partial PDF.
Checked: service route, provider request, both page renders, image bytes/pixels, saved plan and source/settings integrity.
Remaining: image acceptance HOLD, native alignment fidelity, translation meaning review; Laravel/browser flow not tested.
