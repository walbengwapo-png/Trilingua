# Layout-preserving image-text translation: investigation and proposed design

25 October 2026. **Investigation only. No application code/configuration was changed, no dependencies were installed, and no fresh paid OCR/translation requests were made.** Diagnostic PDFs, logs and this report were created under this investigation directory. Existing working-tree changes were retained. Tracked code and `.env` hashes were checked before/after the diagnostic run.

## 1. Conclusion: the problem is real, but the current mechanism needs clarification

The current system has OCR and can pass OCR text through the existing translator. It does **not** implement replacement of source characters inside image pixels.

There are two different failures:

1. **On a page with any extracted native blocks, image text is not OCR-translated.** The page is classified as native and receives a warning if images are present. A native page number/caption is enough to take this branch. The original image survives native PDF reconstruction, including its untranslated words.
2. **On an OCR page, the output deliberately reflows text onto a new A4 page.** It does not use OCR bounding boxes to redraw over the original artwork. One OCR block causes the document to take this reflow branch, so even native pages in a mixed document can lose their layout.

The request is therefore aligned with the missing capability. However, “the result should look exactly like the original for any PDF” cannot be guaranteed: original font identity may no longer exist, background pixels hidden behind source letters are unavailable, and longer translations may not fit their source boxes. The design needs explicit unsupported/review outcomes, not a universal seamless-output promise.

## 2. What the current code actually does

All locations below were read in the current checkout; line references refer to its present working tree.

| Stage | Confirmed implementation and consequence | Owning source |
|---|---|---|
| PDF extraction | PyMuPDF reads native text dictionaries/blocks. The rich dictionary path processes type-0 text blocks, not OCR of image pixels. Images are not normally extracted as translation units. | [extractor.py:386–420](C:/dev/Trilingua/trilingua-code/Model/document/extractor.py:386), [extractor.py:590–608](C:/dev/Trilingua/trilingua-code/Model/document/extractor.py:590) |
| Native structure/style | Native blocks retain page, bbox, alignment, original font name, size, color, bold/italic, line runs and links. | [extractor.py:549–587](C:/dev/Trilingua/trilingua-code/Model/document/extractor.py:549) |
| Image detection / page classification | `complete_pdf()` calls `get_image_info()`. Any native blocks win over OCR; image regions receive a warning but no OCR. Zero-native graphical pages can run full-page OCR, subject to the acceptance gate. There is no visible-text coverage test or region-level mixed-page OCR. | [ocr_extractor.py:171–217](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:171) |
| Existing OCR | Installed Tesseract/pytesseract recognizes at 300 DPI, with English `eng`, Cebuano `ceb`, Filipino `fil`. It records line text, bbox, average confidence and uncertain words. Grouping includes `line_num`, so a block called `paragraph` is actually an OCR line. Source font/size/color are not recovered: Helvetica, 11 pt and black are assigned. Word geometry is retained only for uncertain words; there is no recorded text-angle field. | [ocr_extractor.py:11–15](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:11), [ocr_extractor.py:110–151](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:110) |
| Readiness versus acceptance | Runtime readiness and the quality gate are separate. A category requires a matching representative report at at least 95% word accuracy, with matching runtime/model/settings evidence. Runtime installation does not enable normal OCR. | [ocr_extractor.py:33–97](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:33) |
| Translation | The document orchestrator sends blocks to either the legacy or unit route. The legacy route replaces text while copying structural fields; the unit route already has source IDs, bbox, reading order, context and style references. A second independent translator is unnecessary. | [document_pipeline.py:475–502](C:/dev/Trilingua/trilingua-code/Model/pipeline/document_pipeline.py:475), [translation_pipeline.py:1271–1322](C:/dev/Trilingua/trilingua-code/Model/pipeline/translation_pipeline.py:1271), [unit_adapters.py:53–74](C:/dev/Trilingua/trilingua-code/Model/pipeline/unit_adapters.py:53) |
| Original images in native output | The writer opens the original PDF, preserves images, redacts native text, and inserts translated text. `extract_image()` inside `_image_snapshot()` obtains bytes for an image-preservation check; it is not an OCR/translation extraction stage. `apply_redactions(images=0, graphics=0, text=0)` explicitly leaves image pixels unchanged. Changing those pixels is currently treated as an invariant failure. | [reconstructor.py:898–909](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:898), [reconstructor.py:1129–1139](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1129), [reconstructor.py:1593–1628](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1593) |
| OCR output | Every OCR block carries `ocr_reflow=True`; dispatch then calls `write_ocr_pdf()`. This creates new A4 pages with HTML paragraphs and ignores original artwork, bbox, text color and rotation when placing text. Its coverage check verifies that generated text reached the file, not that translation or visual matching is correct. | [ocr_extractor.py:144–149](C:/dev/Trilingua/trilingua-code/Model/document/ocr_extractor.py:144), [reconstructor.py:1955–2006](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1955) |
| Fit and overflow in native output | Existing native reconstruction measures fonts, wraps, tries bounded shrinking/free space, and moves whole blocks to continuation pages when necessary. That last fallback changes layout/page count and is not equivalent to a strict same-page result. | [reconstructor.py:1505–1554](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1505) |
| Background recovery | Existing `BackgroundSampler` compares only four corner pixels for exact equality. This is not a glyph mask, robust background segmentation or inpainting. It cannot reconstruct a photo/gradient hidden under words. | [layout.py:182–226](C:/dev/Trilingua/trilingua-code/Model/document/layout.py:182) |
| Saved review/regeneration | JSON sidecars preserve selected geometry/style/OCR fields and can carry extra document metadata. Laravel already saves the sidecar. Regeneration calls reconstruction without OCR or translation, but no current sidecar contains a complete pixel-replacement plan/mask. | [regenerator.py:18–57](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:18), [regenerator.py:89–104](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:89), [regenerator.py:243–258](C:/dev/Trilingua/trilingua-code/Model/document/regenerator.py:243), [BlockService.php:89–93](C:/dev/Trilingua/trilingua-code/app/Services/BlockService.php:89) |

Text drawn as vector outlines is another non-extractable case. The current no-native-text branch can OCR a page containing drawings, but a mixed native/vector-outline page is not analyzed region by region. A hidden or poor OCR layer also needs quality checks: extractable text does not necessarily mean accurate visible native text.

## 3. Diagnostic results on image-based PDFs

The samples use the existing DFS poster already on this PC. These are diagnostic raster PDFs, not representative physical-scan acceptance evidence. The exact records are in [diagnostic-results.json](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/diagnostic-results.json).

### A. Image-only PDF, normal pipeline

[Input sample](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/sample-image-only.pdf): one 259.2 × 324 point page, one image, **zero extractable characters and zero native blocks**.

1. `DocumentPipeline.translate()` starts normally in fast mode.
2. `read_pdf()` extracts zero blocks.
3. `complete_pdf()` detects a graphical page requiring OCR.
4. `require_ready('English', 'scan')` rejects it because representative acceptance evidence is missing.
5. Translation and reconstruction are not reached; zero provider calls and no translated output are produced.

The exact error is `OCR English / scan is on hold: a representative, checked 95% acceptance report is required.` See [pipeline log](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/image_only-pipeline.log). No gate was changed or bypassed in this investigation.

### B. Same-page native caption plus image text

[Mixed sample](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/sample-native-plus-image.pdf): the same poster plus **35 native characters** in a caption.

- Native extraction returns one block.
- Classification is `native`, not mixed; the image receives a warning.
- OCR block count is **zero**.
- An isolated full-pipeline diagnostic using the existing mock translation provider processes only that native caption. The poster's image digest remains identical in the output: its baked words are untranslated.
- This diagnostic also exercised the existing continuation fallback: the expanded mock caption moved to a second page. This is software-path evidence, not a real translation-quality result.

The output and mock provenance are recorded in the JSON and [mixed pipeline log](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/same_page_mixed-pipeline.log).

### C. Existing OCR and reconstruction, independently of release acceptance

Direct local recognition of sample A took **2.375 seconds** in this run and returned **13 OCR lines**. Every line received 11 pt black styling; none had a text-rotation field. This is one local diagnostic measurement, not a multi-page throughput prediction or a 95% accuracy result.

To inspect the renderer without making another cloud request, the previously recorded **real GPT-OSS Cebuano translation** was replayed through `reconstruct_document()` against the scanned PDF. The result is **one A4 page (595 × 842 points), zero embedded images**, and all recorded translated text present. Visual inspection confirms the artwork is absent. [Recorded-translation replay](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/recorded-live-translation-reflow.pdf).

This replay is not a new complete translation run. It isolates the writer's behavior. The earlier live result already showed OCR errors propagating into translation and independent translation errors; changing the renderer will not fix those linguistic problems.

## 4. Libraries and OCR choice

**Recommendation:** keep **PyMuPDF + Pillow + Tesseract/pytesseract** for the first geometry-preserving proof. Add **OpenCV headless** in an isolated environment when implementing glyph masks, deskew and background cleanup. Do not replace the translator, or install a second OCR framework before a common-corpus comparison demonstrates a need.

Verified installed versions: PyMuPDF **1.27.2.3**, Pillow **12.2.0**, pytesseract **0.3.13**, Tesseract **5.4.0.20240606**. `eng`, `ceb`, `fil`, `osd` packs are present. OpenCV, PaddleOCR and EasyOCR are not installed in this Python environment. Latest online PyMuPDF documentation now includes newer 2.0 behavior; local method signatures were inspected rather than assuming those features exist here.

| OCR option | Supported-language evidence | Geometry and style | Local/speed/license implications |
|---|---|---|---|
| **Tesseract** | Explicit `eng`, `fil`, `ceb` data available and installed. | Words, rectangles, confidence, block/paragraph/line IDs; optional orientation detection. Exact source font/color/curved baselines are not recovered by the current TSV route. | Offline CPU baseline; already integrated. Apache-2.0 code/official fast data. Same-corpus accuracy needs measurement. |
| **PaddleOCR** | Current official language tables list English and Tagalog; no explicit Cebuano entry. Latin character recognition is not proof of Cebuano language accuracy. | Polygons, scores, orientation/rectification facilities; source typography still needs separate analysis. | Local CPU/GPU, larger inference/model footprint. Apache-2.0 project and selected official models, with exact artifact notices to verify. No local timing or fair accuracy comparison performed. |
| **EasyOCR** | English and Tagalog listed; no explicit Cebuano entry. | Four-point geometry, confidence, rotation trials/paragraph merging; not exact font/background recovery. | Local PyTorch CPU/GPU and model downloads; larger footprint. Apache-2.0 code; verify exact model-weight notices separately. No local comparative benchmark. |
| **Cloud OCR, e.g. Google Vision** | English/Filipino supported; Cebuano is listed as experimental/not regularly evaluated. | Detailed word/symbol hierarchy and geometry; no automatic target-language image reconstruction. | Network/account/paid API usage and document upload required. Not recommended for this local-first increment. |

These statements come from [Tesseract data documentation](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html), [pytesseract](https://github.com/madmaze/pytesseract), [PaddleOCR's language/output tables](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html), [EasyOCR language list](https://www.jaided.ai/easyocr/), and [Google's language-status list](https://docs.cloud.google.com/vision/docs/languages). The [primary-source research note](C:/dev/Trilingua/output/reviews/layout-preserving-ocr-investigation-2026-10-25/ocr-options-primary-sources.md) contains the detailed comparison and license sources. **No engine is established as most accurate for our corpus.** The existing preliminary scores do not rank untested alternatives.

PyMuPDF already provides image occurrence transforms, page rasterization, pixel redaction, positioned text, rotation/morph, font embedding, Story/HTML wrapping and searchable visible text. Local signatures confirm these methods exist. `images=0` leaves raster pixels intact; image-pixel redaction is a different operation. [Official page/redaction/text API](https://pymupdf.readthedocs.io/en/latest/page.html). A blanket change to `images=2` would damage image content without supplying correct masks/background repair.

PyMuPDF/MuPDF have **AGPL/commercial licensing**; confirm the project's existing arrangement before production distribution/hosting changes. This is already a dependency constraint, not a new OCR-engine requirement. Bundled fallback fonts must also have suitable embedding/distribution rights. [Publisher licensing](https://pymupdf.io/licensing).

### Supported languages and typography

The application currently supports **English, Cebuano and Filipino**, all configured with Latin-script codes. There is no current Arabic/RTL, Indic or CJK target-language requirement ([requests.py:13–18](C:/dev/Trilingua/trilingua-code/Model/dto/requests.py:13)). Preserve ñ, accented vowels, combining marks and punctuation; OCR pack `fil` and translation code `tgl_Latn` belong to different systems and should not be interchanged blindly.

The native PDF writer already checks glyph availability and embeds fallback fonts, which is useful to reuse ([reconstructor.py:1037–1117](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:1037)). Its fallback file paths are Windows-specific, so matching output on Linux requires explicitly provisioned fonts rather than assuming `C:\Windows\Fonts` exists ([reconstructor.py:975–987](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:975)). Embedded PDF fonts may be subsetted; a raster image does not retain its original font program.

The code has expansion coefficients such as 1.25 for English→Cebuano and 1.35 for English→Filipino. These are implemented heuristics; this investigation did not establish their empirical accuracy. Fit must measure each actual translated paragraph with its selected font, rather than assume a fixed expansion ratio ([reconstructor.py:719–740](C:/dev/Trilingua/trilingua-code/Model/document/reconstructor.py:719)). Adding non-Latin targets later would require a separate font/shaping/bidirectional-text acceptance scope, not just another language name.

## 5. Recommended design

### 5.1 Classify visible regions, not just whole pages

Keep the original PDF immutable. Inventory native spans, displayed image occurrences/transforms, drawings, page rotation and cropbox. Distinguish usable visible native text from hidden/stale/gibberish OCR layers. Detect remaining text-bearing visual regions with a page/region raster analysis, then OCR those regions. A low native-text count is a trigger to inspect, not proof that a page is scanned.

Deduplicate OCR/native candidates using overlapping geometry and text agreement in the same region. Do not deduplicate globally by text, because repeated labels can be legitimate. Cover raster images and outlined/vector text; a PDF image is not automatically a text-bearing image.

Retain every pixel-to-page transform, including region crop, image occurrence, page rotation, scaling and any deskew/perspective transform. Axis-aligned boxes alone are insufficient after rotation/perspective correction.

### 5.2 Preserve recognition, layout and translation identities

Extend existing blocks/sidecars rather than creating a separate translation system. Each paragraph needs a stable source ID, page/region/occurrence ID, source kind, reading order, bbox and quad, raw OCR words/line/paragraph IDs, word confidence, source language/pack, transform chain, text mask, and estimated style with its own confidence/provenance.

Group lines into paragraphs or semantic labels before translation, while retaining their internal geometry. The multi-line poster headline should remain one contextual unit. Tables need cell boundaries/row-column relationships; columns need region-local order; repeated headers/footers need consistent grouping. Current column ordering and document-map/context helpers can be reused, but they do not discover these OCR relationships automatically.

Estimate font size from source pixel geometry and chosen font metrics; estimate foreground color from glyph pixels in the **original color image**, not the grayscale OCR input. Infer alignment and baseline angle; record font family/weight as estimates unless a native font/resource supplies reliable evidence. Exact font recovery from a raster cannot be promised.

### 5.3 Translate through the existing pipeline

Feed paragraph-level units to the existing batching/context/provider route and keep source IDs mapped to source geometry. Existing translation caches stay separate from OCR/geometry caches. Preserve brand names, numeric labels, units, links and protected content. A valid ID/geometry mapping does not imply a correct translation: OCR review and translation assessment remain separate gates.

### 5.4 Plan fit before removing anything

Measure the actual target text with a glyph-covering font. Try wrapping/alignment in the available region, then bounded shrinking and only verified free space. Do not truncate, silently paraphrase or reduce text to illegibility to manufacture a fit.

For strict same-layout output, a block that cannot fit must stop/require review. Continuation pages or a separate text export are optional fallbacks requiring a clear user choice; the current automatic continuation behavior is not strict layout preservation.

### 5.5 Remove source glyph pixels and reconstruct the background

Build word/glyph masks, not one large paragraph rectangle. Exclude table rules, borders, icons, photos and neighboring text. For verified flat backgrounds, fill masked glyph pixels from robust local background samples. For textured backgrounds, a separately evaluated OpenCV inpainting path is possible, but it invents plausible pixels rather than recovering the exact hidden original. [OpenCV inpainting](https://docs.opencv.org/4.x/df/d3d/tutorial_py_inpainting.html).

First prove clean printed text on simple backgrounds. Complex artwork, curved text, ambiguous masks or background damage should remain unchanged in the original and produce a review/unsupported outcome, not a “complete translation” claim. Leave no faint source glyph edges or old hidden OCR layer in an edited region.

Commit the planned edits on a copy only after translation, masks, fit and background checks succeed. Merely drawing a colored rectangle/text over the original image is not sufficient to claim source pixels were removed.

### 5.6 Draw searchable target text and preserve unaffected content

For a scanned page, retain the cleaned raster background at its original page geometry and add visible target-language PDF text at the mapped locations. One visible target text layer is already searchable; do not add a duplicate invisible target layer.

For a native/image mixed page, retain untouched native/vector content and links, and modify only approved image occurrences. **Do not blindly call `replace_image(xref)` when an image is reused:** replacement can affect every occurrence. First prove unique non-overlapping image-object replacement; repeated/shared, clipped, transparent and overlapping occurrences need a tested per-occurrence isolation method or an explicit hold outcome. Re-rasterizing an entire mixed page would sacrifice native/vector quality and is a separate tradeoff, not an automatic fallback.

Native and image edits must share one page assembly, not two independent writers that overwrite each other's results. Restrict the image-unchanged invariant to **unmodified** assets, and compare edited assets outside approved masks. Keep original page size, crop/rotation, annotations and page count in strict mode.

### 5.7 Persist a deterministic reconstruction plan

Save original-file hash, stable IDs, transforms, masks, selected font IDs/licenses, colors, fit decisions, rendering version and review findings. Do not reference temporary files: the server deletes its request directory after responding ([server.py:726–731](C:/dev/Trilingua/trilingua-code/Model/server.py:726)).

For the initial flat-background path, bounded compressed masks plus deterministic fill parameters can live in the existing JSON sidecar and regenerate from the durable original without another OCR/model call. If later inpainting creates large cleaned assets, persist them through existing storage/cleanup ownership rather than embedding unbounded bitmaps in JSON. Preserve old reflow sidecar behavior on regeneration; do not reinterpret historical records as if they contain a new image-rendering plan.

### 5.8 Validate output, not merely successful function returns

Reopen/render the PDF. Check target-text coverage, clipping, overlap, source-glyph removal, unchanged pixels outside approved edit areas, unchanged unedited native/vector content, correct page transforms, and search-text correctness without duplicate/old hidden text. Keep OCR accuracy, translation quality, visual fidelity and document completeness as distinct results. Existing saved-text coverage cannot approve image replacement by itself.

## 6. Confidence, difficult layouts, performance and failure behavior

- **Confidence:** retain the approved **95% corpus word-accuracy gate**. It is not a per-word Tesseract confidence threshold. Current words below 60 are merely marked uncertain; a high-confidence OCR word can still be wrong. Calibrate any proposed automatic/review/reject bands on representative source images before adopting numbers. No new threshold is silently selected here.
- **Low confidence or unsafe repair:** recommend strict review/hold before erasure. If a partial original-preserving download is offered, mark the untranslated regions and incompleteness explicitly; do not count them as translated. The owner needs to choose this policy.
- **Tables/forms:** identify ruled cells before grouping; never merge across cells or erase grid lines. Preserve cell/column alignment, headers, footers, footnotes and diagrams. Merged cells or unclear structure require review.
- **Rotation:** page quarter-turns, image transforms and line rotation are different. Support straight-line orientations with tested inverse transforms first; perspective and curved/stylized text require a measured extension. Curved writing is not solved by rotating a rectangle.
- **Cache:** key recognition/layout results by source bytes, page/region transform, OCR engine/packs/settings/preprocessing; cache translation separately by text/language/provider/context rules already used. Invalidate masks/layout after source or OCR corrections.
- **Parallelism:** start with bounded sequential page analysis, then benchmark a small process pool if necessary. Each PyMuPDF worker must open its own document; assemble output in a single owner process. Do not share one `Document/Page` across translation threads. [PyMuPDF multiprocessing guidance](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).
- **Resources:** retain pixel limits and OCR timeouts; also bound total rendered pixels, active OCR processes, pages, mask/sidecar sizes and output time. A4 at 300 DPI is roughly 8.7 million pixels, so full-document bitmap buffering is unnecessary.
- **Failure cases:** unreadable scans, encrypted/malformed PDFs, stale hidden OCR, incorrect reading order, poor language recognition, font substitution, translation expansion, shared images, overlapping transparency, damaged backgrounds and partial provider failures need explicit outcomes. Keep the original intact and avoid partial destructive commits.

## 7. Implementation order and files, pending approval

These are proposed edits, **not changes made during this investigation**. Exact splitting of new helper functions should follow the first prototype rather than introducing a general document framework.

| Order | Create/modify | Concrete completion condition |
|---|---|---|
| 1 | Extend `Model/tests/test_ocr_documents.py`; create `Model/tests/test_pdf_image_layout.py` and representative fixture/reference manifest. Extend `Model/benchmarks/ocr_feasibility.py` only for missing region/order metrics. | Reproduce zero-native, caption+scan, embedded screenshot and expected original-image survival. Known translations isolate rendering tests from model variability. |
| 2 | Modify `Model/document/extractor.py`, `ocr_extractor.py`; create focused `Model/document/pdf_regions.py`. | Produce native/visual region inventory, stable occurrences/transforms, usable-native coverage and deduplicated OCR candidates; preserve words/paragraphs/quads and estimates instead of fixed black 11 pt. |
| 3 | Modify `Model/pipeline/document_pipeline.py`, `document/map.py`, `pipeline/unit_adapters.py`; extend `dto/pipeline.py` only where existing fields cannot carry required identity. | Both legacy and unit routes preserve paragraph context and exact source-to-output mappings without changing the provider interface. |
| 4 | Create focused `Model/document/image_reconstructor.py`; extend `document/layout.py` for reusable fitting/font/mask helpers; add a tested OpenCV pin to `Model/requirements.txt` only after isolated proof. | Plan masks/background/fit, then prove same-position replacement for a clean flat-background scanned page and a unique image on a mixed page. No text-over-old-text artifact. |
| 5 | Modify `Model/document/reconstructor.py`. | Integrate native and image edits on one original-sized page. New complete render plans use image-preserving output; historical `ocr_reflow` sidecars retain their old explicit path. Unsafe cases do not silently reflow or appear complete. |
| 6 | Modify `Model/document/regenerator.py`, `validators/translation_validator.py` and focused tests. | Version and persist the complete render plan; regenerate edits without OCR/provider calls; validate source removal, target coverage and unchanged outside-mask content. |
| 7 | Modify `Model/server.py` response/validation metadata as needed and `resources/views/admin/review-document.blade.php` for region-level review. Existing `BlockService.php`/download-warning paths already persist sidecars/warnings; change them only if new completeness fields or durable render assets require it. | User/reviewer can identify uncertain/untranslated regions and layout failures. No hidden incomplete success. |
| 8 | Representative OCR/language/visual acceptance, then local authenticated upload/queue/review/regenerate/download pilot; update `.env.example`/setup docs and service launcher/deployment dependencies where actually needed. | All accepted categories pass the unchanged quality gate plus visual/completeness tests. Deployment remains separate. |

The current launcher invokes generic `python`, so an isolated prototype environment must be started explicitly; it is not automatically adopted by the application ([start-all.bat:24–25](C:/dev/Trilingua/trilingua-code/start-all.bat:24)).

## 8. Exact commands and their status

**Nothing below was installed/executed as an implementation change.** The first checks run against the current system. The isolated environment/install and new renderer tests are for **after plan approval**. There is currently no command that turns the existing reflow writer into seamless image replacement.

### Verify what is already installed on this PC

```powershell
Set-Location C:\dev\Trilingua\trilingua-code
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --version
& 'C:\Program Files\Tesseract-OCR\tesseract.exe' --list-langs --tessdata-dir 'C:\Users\walbe\AppData\Local\TriLingua\ocr\tessdata'
py -3.11 -c "import fitz,PIL,pytesseract; print(fitz.VersionBind,PIL.__version__,pytesseract.__version__)"
```

Tesseract and the three required language packs are already installed; this PC does not need another installer for the baseline.

### After approval: isolated local prototype dependencies

```powershell
Set-Location C:\dev\Trilingua\trilingua-code
py -3.11 -m venv .venv-ocr-layout
$ocrPython = 'C:\dev\Trilingua\trilingua-code\.venv-ocr-layout\Scripts\python.exe'
& $ocrPython -m pip install -r .\Model\requirements.txt 'PyMuPDF==1.27.2.3' 'pillow==12.2.0' 'pytesseract==0.3.13' 'numpy==2.4.6' 'opencv-python-headless==4.13.0.92'
& $ocrPython -m pip install -r .\requirements-dev.txt
& $ocrPython -m pip check
$env:OCR_TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
$env:TESSDATA_PREFIX = 'C:\Users\walbe\AppData\Local\TriLingua\ocr\tessdata'
```

The first three library pins reproduce the inspected OCR/PDF stack. OpenCV 4.13.0.92 is a **proposed isolated prototype pin**, not a tested dependency here; its official [PyPI metadata](https://pypi.org/pypi/opencv-python-headless/4.13.0.92/json) confirms a Windows wheel and NumPy >=2 dependency for Python >=3.9. Do not install GUI/headless OpenCV variants together. A successful isolated prototype and dependency check are required before updating the application's normal environment.

### Existing tests and OCR evaluator

```powershell
Set-Location C:\dev\Trilingua\trilingua-code\Model
& $ocrPython -m pytest tests/test_ocr_documents.py tests/test_ocr_feasibility.py tests/test_regeneration.py tests/test_regression.py -q
& $ocrPython -m benchmarks.ocr_feasibility --manifest C:\dev\Trilingua\output\reviews\ocr-2026-10-25\manifest.json --minimum-accuracy 95 --output C:\dev\Trilingua\output\reviews\layout-preserving-ocr-investigation-2026-10-25\recheck-existing-diagnostics.json
```

The existing manifest is diagnostic and should remain HOLD. Replace it with a genuinely representative, checked acceptance manifest when available; do not relabel generated crops as real scans/photos. The proposed new rendering test command is `& $ocrPython -m pytest tests/test_pdf_image_layout.py -q`; that file **does not exist yet** and must be implemented in step 1.

### After implementation and accepted evidence: start and exercise the service

```powershell
Set-Location C:\dev\Trilingua\trilingua-code\Model
# Use only an actual accepted report, not the current HOLD diagnostic report.
$env:OCR_ACCEPTANCE_REPORT = 'C:\dev\Trilingua\output\reviews\ocr-layout-acceptance\report.json'
& $ocrPython -u -m uvicorn server:app --host 127.0.0.1 --port 5000 --log-level info
```

The acceptance-report path above is a **future artifact**, not an existing pass. Stop/restart only the intended service after confirming active jobs are finished; do not start a second server on the occupied port. This endpoint test uses configured translation providers and therefore may consume the existing cloud allowance/billing; record its budget before running.

In a second PowerShell terminal, the following posts one PDF using the existing service contract and saves its JSON/base64 response correctly:

```powershell
Set-Location C:\dev\Trilingua\trilingua-code\Model
$ocrPython = 'C:\dev\Trilingua\trilingua-code\.venv-ocr-layout\Scripts\python.exe'
@'
import base64, json, os
from pathlib import Path
import requests
from config.environment import load_engine_environment
load_engine_environment('../.env')
folder = Path('../../output/reviews/layout-preserving-ocr-investigation-2026-10-25')
token = os.environ.get('PYTHON_SERVICE_TOKEN', '')
headers = {'X-Service-Token': token} if token else {}
with (folder/'sample-image-only.pdf').open('rb') as source:
    response = requests.post('http://127.0.0.1:5000/translate/document',
        headers=headers, files={'file': ('sample.pdf', source, 'application/pdf')},
        data={'source_lang': 'English', 'target_lang': 'Cebuano', 'mode': 'fast'}, timeout=300)
response.raise_for_status()
payload = response.json()
(folder/'accepted-run-envelope.json').write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
(folder/'accepted-run.pdf').write_bytes(base64.b64decode(payload['file_base64'], validate=True))
print(folder/'accepted-run.pdf')
'@ | & $ocrPython -X utf8 -
```

This is the real Python endpoint, not Laravel authentication/queue testing. Until valid category evidence and the proposed renderer exist, it will still reject or use the current behavior; these commands do not bypass acceptance. The final Laravel pilot is separate and must verify the service launcher uses the approved Python environment. Do not publish the base64 envelope or any credentials.

## 9. Test plan and acceptance criteria

| Case | Required assertions |
|---|---|
| Fully scanned PDF, zero native text | OCR detects every text region; correct page/rotation mapping; source glyphs actually removed; readable target text in source positions; same strict-mode page dimensions/count; searchable target text. |
| Native page plus separate scanned page | Native page retains its layout/vector quality; scan gets replacement; no whole-document reflow triggered merely by one OCR block. |
| Native caption/page number plus screenshot on the same page | Both content types translated exactly once; caption cannot suppress image OCR; no duplicate hidden/native/OCR text. |
| Embedded image text on a page with otherwise substantial native text | Region OCR/masks affect only the correct displayed image occurrence; surrounding image/native/vector content stays unchanged. |
| Repeated/shared image XObject | Changing one selected occurrence does not change an unrelated occurrence/page. Until this is proved, strict hold is expected. |
| Columns, table rules, merged cells, headers/footers | Correct reading order and context; no cross-cell paragraph merging; no erased grid lines or shifted labels. |
| Rotations, cropboxes, skew and perspective | Bounding quads and masks round-trip through all transforms; unsupported curvature/perspective fails explicitly rather than painting in the wrong place. |
| White/color/gradient/photo backgrounds; small fonts and decorative headings | Outside-mask visual difference within defined tolerance; no halos/flat patches/remaining source letters; unsupported repair requires review. |
| English, Filipino and Cebuano output | Checked target translations and rendered ñ/diacritics/quotes/dashes; test all six directed language pairs where supported, with shorter and longer translations. OCR scoring is per source language/input category. |
| Low-confidence and incorrect high-confidence OCR | No blind destructive edit; raw/source-review findings visible; numeric labels, names and punctuation checked independently. |
| Translation failures / overflow | No partially erased final PDF; no truncation/illegible shrinking; strict mode does not silently add pages. |
| Review edits and regeneration | Same background/geometry/masks after edits; no OCR/provider calls; source hash mismatch and stale render-plan versions are rejected. |
| Regression/resource limits | Native-only DOCX/PDF and other formats remain intact; malformed/encrypted/oversized PDFs have explicit outcomes; measure cold/warm multi-page time and peak memory on this PC. |

Use fixed known translations for deterministic rendering tests, plus a bounded live-provider pilot to assess language quality. Do not let an AI-review score substitute for checked translations. Retain **95% minimum word accuracy per accepted source-language/input category**, and add explicit region recall, reading-order, visual fidelity, search and completeness checks. Visual thresholds and minimum readable font size need to be agreed/calibrated before release; no arbitrary exact scores are assigned here.

## 10. Decisions needed before implementation

1. **Initial visual scope:** start with clean printed scans/forms and uniform backgrounds, or include decorative posters/photos/gradients in the first release? The latter requires substantially more background reconstruction and visual review. Recommendation: prove the former first, while classifying and honestly holding unsupported regions in any input PDF.
2. **Strict layout versus readability:** if a correct translation cannot fit, should the document stop for review, or may it use continuation pages/a separate readable export? Recommendation for the stated goal: strict same-page output must stop rather than silently change layout.
3. **Low-confidence/unsupported regions:** stop the final translated download until reviewed, or allow an explicitly incomplete version retaining those originals? This changes risk and user-facing completion semantics.
4. **Typography tolerance:** is a licensed fallback with matching family/weight acceptable, or is exact brand-font reproduction required? Exact reproduction may require original design assets/fonts and permission to embed them.
5. **Distribution/licensing:** confirm the existing PyMuPDF/MuPDF arrangement and intended deployment before packaging the expanded renderer. No paid OCR API is recommended; cloud OCR or generative inpainting would need a separate cost/privacy decision.

No implementation starts until the plan is approved. The investigation does not select new risk tolerance, lower the quality gate, enable uploads, or replace the production OCR/translation engine.
