# Local OCR feasibility and collection kit

**Drafts and diagnostic results are not acceptance evidence.** Diagnostic verdict bands are suggestions. The resumable workflow can invoke the existing evaluator and sign/verify its passing result only after genuine reviewed inputs are complete. A 100% synthetic result proves no real OCR accuracy. No completed review, production key or acceptance report is bundled.

Use the existing isolated environment; no new dependency is required. Tesseract, Pillow, PyMuPDF, NumPy and OpenCV are already in that environment. Examples use owner-chosen folders and do not imply completed evaluation. They make no provider/cloud calls. Keep source documents and keys outside Git.

## Prepare and resume a review packet

From repository root (use a new output directory):

```powershell
$py = (Resolve-Path .\trilingua-code\.venv-ocr-layout\Scripts\python.exe).Path
Set-Location .\trilingua-code\Model
& $py -m tools.ocr_kit prepare-review 'C:\path\source.pdf' --language English --output 'C:\OCR-work\review'
& $py -m tools.ocr_kit advance --workspace 'C:\OCR-work\review'
```

Preparation makes a source copy,300-DPI page previews, candidate text/region drafts, a local `review.html` with region overlays, `START_HERE.md`, blank rights/collector/capture fields and an unapproved corpus-review template. It does **not** compare OCR output with itself or assign accuracy. The seed is calibration-only, because it is already being inspected. The packet's source language determines its three required scan/photo/screenshot scopes; the translation target is irrelevant to recognition qualification. No provider/cloud request is made.

Correct draft text and boxes, add actual document metadata and additional independent calibration/held-out sources to `incoming/info.csv`, then run `advance`. Once intake gaps are resolved it creates a blank `second-review.csv`. An independent person must check the originals and complete that sheet. Corpus coverage review also needs actual human statements in `corpus-review.json`. `workflow-status.json` lists the exact missing step; it never invents a reviewer, acquisition, permission or capture classification.

After reviews and scope coverage are complete, `advance` freezes a new run, evaluates through the shared production OCR path at95%, and validates the report. If it passes, supply an existing private acceptance key with `--sign-key-file` to generate and verify a signed report. Key-generation commands appear below. Failed evaluations stay unsigned. Repeated runs preserve earlier frozen outputs. Live `.env` and service configuration are never changed automatically.

Source, transcript, metadata and region changes invalidate an existing review. Earlier intake/sheet formats without a region hash require a fresh intake and review sheet; preserve the old completed sheet, move it aside, and run `advance` to create a new blank one. A real review must then be completed again. This prevents boxes being changed after sign-off.

## Connected AI coordinator (optional preparation)

```powershell
& $py -m tools.ocr_kit coordinate --workspace 'C:\OCR-work\review'
```

This explicitly requests one advisory decision through the existing configured analysis route (`ANALYSIS_PROVIDER`, with the existing Gemini/Ollama fallback choice). It does not import/start the server or change provider defaults. Configured cloud usage may incur its normal provider cost. Ordinary `prepare-review` and `advance` remain offline unless the operator separately runs this command.

The coordinator sends bounded workflow facts and program-grounded observations about visible native PDF text absent from **calibration** drafts. It sends neither page images nor held-out text/geometry. It is text/geometry based, not a vision reviewer for scans/photos, and cannot certify translation meaning or OCR accuracy. Human identities, rights and capture classes are never inferred.

Only three actions are accepted: prepare separate draft proposals from known candidate IDs, ask known workflow questions, or stop. Unknown actions/IDs/arguments are rejected. No action can execute commands, overwrite canonical references, score acceptance, sign, change settings or activate OCR. Current fingerprints must still match before a proposal can be written. Inputs/outputs must stay inside the selected workspace. Inspection caps are50 listed documents,50 calibration PDF pages,100 repair candidates,1MB per text/region file,10MB per source and20,000 prompt characters.

Each run writes `coordinator-runs/<id>/coordinator.json` and a readable `review.html`. Accepted proposals are separate `.txt`/`.regions.json` drafts in that run; check their complete content, geometry and reading order before adopting them into intake and obtaining a fresh independent review. Existing references/review records remain unchanged. The program lists required human facts even if the AI omits them from its suggestion. No model response becomes approval.

There is one analysis decision per invocation, with a90-second request-local transport allowance and a final late-response check. Gemini gets one attempt; the existing Ollama fallback retains its bounded retry behavior. Transport/DNS/OS behavior is not a hard process-cancellation guarantee. Provider failures and invalid/stale decisions produce `advice_unavailable`, with no accepted preparation action. This command does not monitor or retry later automatically.

## Collect and inspect

Collect the [capture guide](CAPTURE_GUIDE.md) grid: English/Cebuano/Filipino x scan/photo/screenshot x 4 distinct documents. Keep document/content groups entirely within one split. A multi-page PDF remains one document. Use independent content for calibration and held-out; do not tune on held-out results.

Put each PDF/PNG/JPEG beside a matching UTF-8 `.txt` transcript. For `page.pdf`, use `page.txt` and `page.regions.json`. Do not use OCR output as an unchecked transcript. `info.csv` headers:

```csv
file,language,capture_class,content_group_id,split,author,rights_note
```

Fill one row per actual document; split is `calibration` or `heldout` (`held_out` is normalized). Author means the actual acquirer, and rights_note records the owner's actual rights basis; neither is a legal determination by the tool. Synthetic material must include the optional `material` column set to `test_fixture`; it can never be built into real evaluator material.

The geometry file is a JSON list of `{id,page,order,bbox,text}` records: zero-based page, unique region IDs/order, `[x0,y0,x1,y1]` in pixels, complete checked text. For PDF pages the coordinate basis is 300 DPI; for standalone images it is their full-resolution EXIF-transposed image at the 300 baseline. A second reviewer must check boxes, reading order and full text against the original. Preparation can propose OCR boxes, but never labels them checked. Without supplied geometry, feasibility reports word accuracy and `null` for layout scores.

From repository root, set paths for your actual local folders:

```powershell
$py = (Resolve-Path .\trilingua-code\.venv-ocr-layout\Scripts\python.exe).Path
Set-Location .\trilingua-code\Model
$source = 'C:\OCR-work\incoming'
$work = 'C:\OCR-work\review'
New-Item -ItemType Directory -Force $work | Out-Null
& $py -m tools.ocr_kit intake $source --output "$work\intake.json"
& $py -m tools.ocr_kit feasibility --intake "$work\intake.json" --dpi 300 400 --output "$work\raw-diagnostic.json"
& $py -m tools.ocr_kit feasibility --intake "$work\intake.json" --dpi 300 400 --deskew --binarize --output "$work\preprocessed-diagnostic.json"
```

Per-sample and per language/capture/split/variant slices report word accuracy, region recall and within-page reading order when checked geometry exists. Bands: >=95 reachable; 85-95 try preprocessing; <85 engine problem. Missing or failed samples remain unmeasured and visible. Do not select the best held-out variant and call it unbiased evidence. 400 DPI, deskew and binarization are diagnostic only; the production evaluator always uses the current fixed SETTINGS. Changing production preprocessing requires new matching evidence and a separate approved change.

## Independent reference check and manifest

```powershell
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv"
# STOP: an independent human completes the sheet after checking the actual originals.
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv" --ingest --output "$work\checks.json"
```

The sheet starts blank: reviewer, confirmed/corrected decision, corrected_text, review_date (YYYY-MM-DD), attestation, rights_verified, representative and real_capture_confirmed. The three confirmations must be explicitly `true` before manifest creation. The reviewer must differ from the acquirer. Ingestion records supplied statements and checked text with source/reference/region hashes; it does not independently establish that the statements are true. Changed source/transcript/region bytes invalidate the intake. Corrected text must also match the reviewed region text before building.

The owner must supply `$work\corpus-review.json` with actual `reviewers` (array of names including all reference reviewers), `review_date`, a substantive `attestation`, and `coverage_reviewed:true`. Do not fill these from this README or from generated text. Review rights, representativeness, split isolation and complete region coverage before attesting.

```powershell
& $py -m tools.ocr_kit build-manifest --intake "$work\intake.json" --checks "$work\checks.json" --approval "$work\corpus-review.json" --output "$work\frozen-corpus"
```

Use a new output directory. Build refuses incomplete checks, gaps or fixtures. It prepares evaluator schema v2 `manifest.json` (combined frozen catalog), `calibration.json`, `held_out.json`, per-page PNGs and checked per-page transcripts derived from the supplied complete regions. It issues no acceptance report. If construction fails, no valid manifest is published; preserve diagnostics and use a new output after correcting inputs.

## Evaluator, keys and signing

HMAC stops accidental/casual enablement, **not a malicious administrator holding the signing key**. Protect the acceptance key for the evaluator owner, and a separate render-plan key for the service. Keys are 32 random bytes in purpose-tagged key files, created exclusively outside the repository without overwrite. POSIX mode is 0600; on Windows restrict the enclosing folder ACL to the intended account/service. Never commit, paste or send a key. Plan-key rotation invalidates existing signed plans. Old unsigned hybrid plans are rejected rather than silently trusted; historical v1/v2 reflow sidecars remain compatible.

```powershell
$keys = 'C:\OCR-private-keys'
New-Item -ItemType Directory -Force $keys | Out-Null
& $py -m tools.ocr_trust keygen --purpose acceptance --output "$keys\acceptance.json"
& $py -m tools.ocr_trust keygen --purpose render-plan --output "$keys\render-plan.json"
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\calibration.json" --minimum-accuracy 95 --output "$work\calibration-diagnostic.json"
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\held_out.json" --minimum-accuracy 95 --output "$work\held-out-diagnostic.json"
# Final issuance remeasures the combined frozen catalog, keeping calibration excluded from scope scores.
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\manifest.json" --minimum-accuracy 95 --sign-key-file "$keys\acceptance.json" --output "$work\signed-evaluator-report.json"
& $py -m tools.ocr_trust verify --report "$work\signed-evaluator-report.json" --key-file "$keys\acceptance.json" --manifest "$work\frozen-corpus\manifest.json"
```

Split-only outputs are diagnostic and cannot enable the gate. Final issuance validates the complete combined manifest, actual sample/reference hashes, review attestations, engine binary/pack/settings fingerprints and recomputed case/scope scores. Only held-out results count toward 95%. A below-threshold scope remains rejected. Verification also compares the installed runtime. Review region recall, misses and order separately; 95% spelling does not prove complete extraction.

After genuine evidence and owner approval, configure the service deployment's `OCR_ACCEPTANCE_REPORT`, `OCR_ACCEPTANCE_KEY_FILE`, `OCR_CORPUS_MANIFEST` and `OCR_PLAN_KEY_FILE` to durable local paths. This task did not set them or edit `.env`. Missing keys fail closed; no keys are generated on startup. Production always rejects fixture-marked material/keys; there is no test-mode configuration flag. The synthetic smoke uses test-owned dependency replacements only.

Resource configuration: `OCR_JOB_PIXEL_BUDGET` defaults to 120,000,000 decoded pixels, while 40 MP/image and 50 pages remain unchanged. A page whose hash lookup would exceed the budget has all its images held with an explicit reason. `OCR_SCRATCH_ROOT` defaults to an owned temp folder; `OCR_SCRATCH_MAX_AGE_SECONDS` defaults to 86400. Parent leases protect active jobs during startup stale-directory sweeps. Provider connect/read/total transport settings are capped to the remaining request-local PDF budget, and impossible retries are refused. Requests still use transport timeouts, not forced thread cancellation: slow response streaming/DNS/OS scheduling can exceed a wall-clock deadline; late publication is rejected. No absolute cancellation guarantee is claimed.

Real-document replacement remains HOLD until genuine signed held-out evidence passes, followed by Linux/font parity, visual sign-off and owner PyMuPDF/font-rights review.

Current production SETTINGS v3 reads hOCR word/line geometry and allows one 4/3-scale retry per uncertain paragraph. A retry must agree on NFC-normalized text (including case, punctuation and diacritics), leave every word at confidence 80 or higher, and fit the shared decoded-pixel allowance and original 60-second OCR time allowance. The evaluator calls this same policy. Older settings reports cannot qualify it. Renderer algorithm v2 also invalidates earlier v3 render plans carrying algorithm v1; existing downloaded PDFs remain readable, but those plans require a fresh translation rather than silent regeneration under the new renderer.

Plan/report HMAC canonicalization sorts keys and normalizes integral floats and empty JSON containers to the representations preserved by Laravel associative JSON decoding. Numeric value changes, geometry, status, source identity and block metadata remain authenticated; a real PHP encode/decode plus reconstruction regression covers this boundary. A standalone image larger than a deliberately reduced job budget is rejected before PDF conversion; it cannot safely produce a PDF template without decoding. Diagnostic Tesseract lookup uses the installed executable or the process OCR_TESSERACT_CMD override.
