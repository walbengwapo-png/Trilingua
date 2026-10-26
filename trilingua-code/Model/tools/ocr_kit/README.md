# Local OCR feasibility and collection kit

**DIAGNOSTIC, NOT ACCEPTANCE EVIDENCE.** This kit cannot sign or issue an acceptance report. Its verdict bands are suggestions. A 100% synthetic result proves no real OCR accuracy. No data, completed review, production key or acceptance report is bundled.

Use the existing isolated environment; no new dependency is required. Tesseract, Pillow, PyMuPDF, NumPy and OpenCV are already in that environment. These commands are instructions for the owner, not commands executed against real material during implementation. They make no provider/cloud calls. Keep source documents and keys outside Git.

## Collect and inspect

Collect the [capture guide](CAPTURE_GUIDE.md) grid: English/Cebuano/Filipino x scan/photo/screenshot x4 distinct documents. Keep document/content groups entirely within one split. A multi-page PDF remains one document. Use independent content for calibration and held-out; do not tune on held-out results.

Put each PDF/PNG/JPEG beside a matching UTF-8 `.txt` transcript. For `page.pdf`, use `page.txt` and `page.regions.json`. Do not use OCR output as an unchecked transcript. `info.csv` headers:

```csv
file,language,capture_class,content_group_id,split,author,rights_note
```

Fill one row per actual document; split is `calibration` or `heldout` (`held_out` is normalized). Author means the actual acquirer, and rights_note records the owner's actual rights basis; neither is a legal determination by the tool. Synthetic material must include the optional `material` column set to `test_fixture`; it can never be built into real evaluator material.

The geometry file is a JSON list of `{id,page,order,bbox,text}` records: zero-based page, unique region IDs/order, `[x0,y0,x1,y1]` in pixels, complete checked text. For PDF pages the coordinate basis is300 DPI; for standalone images it is their full-resolution EXIF-transposed image at the300 baseline. A second reviewer must check boxes, reading order and full text against the original. The kit does not invent geometry. Without it, feasibility reports word accuracy and `null` for layout scores.

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

Per-sample and per language/capture/split/variant slices report word accuracy, region recall and within-page reading order when checked geometry exists. Bands:>=95 reachable;85-95 try preprocessing;<85 engine problem. Missing or failed samples remain unmeasured and visible. Do not select the best held-out variant and call it unbiased evidence.400 DPI, deskew and binarization are diagnostic only; the production evaluator always uses the current fixed SETTINGS. Changing production preprocessing requires new matching evidence and a separate approved change.

## Independent reference check and manifest

```powershell
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv"+# STOP: an independent human completes the sheet after checking the actual originals.
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv" --ingest --output "$work\checks.json"
```

The sheet starts blank: reviewer, confirmed/corrected decision, corrected_text, review_date (YYYY-MM-DD), attestation, rights_verified, representative and real_capture_confirmed. The three confirmations must be explicitly `true` before manifest creation. The reviewer must differ from the acquirer. Ingestion records supplied statements and checked text with source/reference hashes; it does not independently establish that the statements are true. Changed source/transcript bytes invalidate the intake. Corrected text must also match the reviewed region text before building.

The owner must supply `$work\corpus-review.json` with actual `reviewers` (array of names including all reference reviewers), `review_date`, a substantive `attestation`, and `coverage_reviewed:true`. Do not fill these from this README or from generated text. Review rights, representativeness, split isolation and complete region coverage before attesting.

```powershell
& $py -m tools.ocr_kit build-manifest --intake "$work\intake.json" --checks "$work\checks.json" --approval "$work\corpus-review.json" --output "$work\frozen-corpus"
```

Use a new output directory. Build refuses incomplete checks, gaps or fixtures. It prepares evaluator schema v2 `manifest.json` (combined frozen catalog), `calibration.json`, `held_out.json`, per-page PNGs and checked per-page transcripts derived from the supplied complete regions. It issues no acceptance report. If construction fails, no valid manifest is published; preserve diagnostics and use a new output after correcting inputs.

## Evaluator, keys and signing

HMAC stops accidental/casual enablement, **not a malicious administrator holding the signing key**. Protect the acceptance key for the evaluator owner, and a separate render-plan key for the service. Keys are32 random bytes in purpose-tagged key files, created exclusively outside the repository without overwrite. POSIX mode is0600; on Windows restrict the enclosing folder ACL to the intended account/service. Never commit, paste or send a key. Plan-key rotation invalidates existing signed plans. Old unsigned hybrid plans are rejected rather than silently trusted; historical v1/v2 reflow sidecars remain compatible.

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

Split-only outputs are diagnostic and cannot enable the gate. Final issuance validates the complete combined manifest, actual sample/reference hashes, review attestations, engine binary/pack/settings fingerprints and recomputed case/scope scores. Only held-out results count toward95%. A below-threshold scope remains rejected. Verification also compares the installed runtime. Review region recall, misses and order separately;95% spelling does not prove complete extraction.

After genuine evidence and owner approval, configure the service deployment's `OCR_ACCEPTANCE_REPORT`, `OCR_ACCEPTANCE_KEY_FILE`, `OCR_CORPUS_MANIFEST` and `OCR_PLAN_KEY_FILE` to durable local paths. This task did not set them or edit `.env`. Missing keys fail closed; no keys are generated on startup. Production always rejects fixture-marked material/keys; there is no test-mode configuration flag. The synthetic smoke uses test-owned dependency replacements only.

Resource configuration: `OCR_JOB_PIXEL_BUDGET` defaults to120,000,000 decoded pixels, while40MP/image and50 pages remain unchanged. A page whose hash lookup would exceed the budget has all its images held with an explicit reason. `OCR_SCRATCH_ROOT` defaults to an owned temp folder; `OCR_SCRATCH_MAX_AGE_SECONDS` defaults to86400. Parent leases protect active jobs during startup stale-directory sweeps. Provider connect/read/total transport settings are capped to the remaining request-local PDF budget, and impossible retries are refused. Requests still use transport timeouts, not forced thread cancellation: slow response streaming/DNS/OS scheduling can exceed a wall-clock deadline; late publication is rejected. No absolute cancellation guarantee is claimed.

Real-document replacement remains HOLD until genuine signed held-out evidence passes, followed by Linux/font parity, visual sign-off and owner PyMuPDF/font-rights review.
