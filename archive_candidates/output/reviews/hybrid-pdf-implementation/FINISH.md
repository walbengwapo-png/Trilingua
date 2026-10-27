# Hybrid PDF engineering finish

**Real-document image replacement remains HOLD.** Engineering packages are implemented on `codex/hybrid-pdf-finish`, based on `eb8dff7`. No genuine corpus, reference sign-off, production acceptance report, deployed key or live setting was created.

## Package results

| Package | Result | Commit | Before -> after Python / PHP tests(assertions) / browser |
|---|---|---|---|
| Baseline | Same offline handoff suites | eb8dff7 |217 / 52(254) /4|
| 1 Report trust | Evaluator-only issuance, HMAC-SHA256, corpus/reviewer/manifest verification, recomputed held-out scores and engine/pack/settings fingerprints. Calibration/legacy/fixture material fails closed. Keygen and verification CLI. |a5dbc75|217 ->229 /52(254) /4|
| 2 Plan trust | Signed plan v3 binds original hash and immutable block metadata. Regeneration verifies before reconstruction, re-signs fitted edits before publication, recomputes content status, and never calls OCR/providers. PHP passes opaque signatures unchanged. Historical v1/v2 sidecars retained; unsigned hybrid plans rejected. |d0ce01b|229 ->234 /52(255) /4|
| 3 Memory/scratch/timeouts |120 MP configurable default aggregate admission before hash-based decode; over-budget images held. Cleaned arrays stage to disk and are released per image. Parent-owned scratch leases/finally cleanup and startup stale sweep. Request-local remaining-budget transport/retry caps across translation/analysis providers. |72e9953|234 ->242 /52(255) /4|
| 4 Feasibility kit | Hashed intake/metadata, split checks, 300/400 DPI/deskew/binarize diagnostics, blank independent-review sheets, reference import and evaluator v2 manifest preparation. Missing geometry yields no invented layout scores. Capture guide and exact commands below. |36cc837|242 ->246 /52(255) /4|
| 5 Service smoke | Synthetic upload-equivalent image-only output is untranslated; mixed output is partial with zero translated raster regions (user-confirmed interpretation). Original pixels intact. Signed fixture replacement is demonstrated only under test-owned injection; every report body leaf is tamper-tested. |14e228f|246 ->250 /52(255) /4|
| 6 Cleanup/integration | Real PHP JSON round-trip regression, canonical HMAC representation, stricter reference/geometry checks, image-conversion admission and failed-lease cleanup; docs/inventory/preservation. |a410a7a|250 ->254 /52(255) /4|

Every package's after-suites also form the next package's before-suites; no intervening code change was omitted. All suites use the preserved local working tree, not a clean deployment. Expanded Python handoff command adds `test_ocr_trust.py`, `test_pdf_finish_resources.py`, `test_provider_job_budget.py`, `test_ocr_kit.py`, `test_hybrid_finish_smoke.py`. Raw `finish-<package>-{python,php,browser}.log` files stay local/uncommitted.

## Safety verification and limits

- All 4 isolated mutations were killed: report signature, plan signature, aggregate pixel budget, parent scratch cleanup. Every source was restored byte-for-byte after each probe; no application/live file was mutated. See `finish-mutations.json`.
- Synthetic memory probe: 16 distinct 240,000-pixel images with a 720,000-pixel test budget admitted 3 and held 13 before hash lookup. Peak was about 19.5 MB (19,523,120-19,523,851 bytes across focused runs), measured with tracemalloc; **MuPDF native heap is excluded**. This is a bounded small-fixture check, not a production 120 MP stress result.
- Real Windows worker timeout/hard-kill cleanup passes, including an owned child-process test inherited from review. Stale sweep skips live leases/unowned paths. Actual Linux execution remains unverified.
- HMAC canonicalization sorts keys and normalizes integral floats and empty JSON containers across Laravel/PHP associative serialization. The real PHP encode/decode + reconstruction regression failed before this correction and passes afterward. Changed numeric values, source hash, status, geometry and immutable block metadata are still authenticated.
- Fixture keys/material are rejected by production loaders; no environment test-mode switch exists. Fixture demonstrations patch dependencies inside tests only, use randomly generated temporary keys, and carry synthetic/non-human-review labels. The signed replacement smoke uses an in-process test worker to keep these patches out of real spawned workers; ordinary held smoke uses the real isolated worker. This proves plumbing, not real OCR accuracy.
- HMAC prevents accidental/casual enablement, **not a malicious administrator holding the key**. No key contents are stored in this report or Git.
- Provider transport connect/read/total settings and retry waits are capped to remaining job time. No forced thread/network cancellation was added. DNS, slow streaming and OS scheduling can exceed a hard wall-clock deadline despite transport settings; late publication is refused. Do not claim an absolute cancellation guarantee.
- The default aggregate budget is 120,000,000 pixels (`OCR_JOB_PIXEL_BUDGET`); 40 MP/image, 50 pages, 60 s OCR, 8 MB masks, 16 MB plans, 24 MB sidecar/result and 10 pt/95% limits remain unchanged. Pages whose xref hash lookup cannot be safely admitted have all images held. A standalone image above a deliberately smaller job budget is rejected before conversion, because producing its PDF template requires decode.

## Commands and owner checklist

Use `trilingua-code/Model/tools/ocr_kit/README.md` and `CAPTURE_GUIDE.md` for formats, sheet fields, coordinate basis, diagnostic bands and constraints. No extra dependency was added. From repository root (replace folders with actual local collection locations):

```powershell
$py = (Resolve-Path .\trilingua-code\.venv-ocr-layout\Scripts\python.exe).Path
Set-Location .\trilingua-code\Model
$source = 'C:\OCR-work\incoming'
$work = 'C:\OCR-work\review'
$keys = 'C:\OCR-private-keys'
New-Item -ItemType Directory -Force $work, $keys | Out-Null
& $py -m tools.ocr_kit intake $source --output "$work\intake.json"
& $py -m tools.ocr_kit feasibility --intake "$work\intake.json" --dpi 300 400 --output "$work\raw-diagnostic.json"
& $py -m tools.ocr_kit feasibility --intake "$work\intake.json" --dpi 300 400 --deskew --binarize --output "$work\preprocessed-diagnostic.json"
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv"
# An independent human checks originals and completes the sheet; owner supplies corpus-review.json.
& $py -m tools.ocr_kit reference-check --intake "$work\intake.json" --sheet "$work\second-review.csv" --ingest --output "$work\checks.json"
& $py -m tools.ocr_kit build-manifest --intake "$work\intake.json" --checks "$work\checks.json" --approval "$work\corpus-review.json" --output "$work\frozen-corpus"
& $py -m tools.ocr_trust keygen --purpose acceptance --output "$keys\acceptance.json"
& $py -m tools.ocr_trust keygen --purpose render-plan --output "$keys\render-plan.json"
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\calibration.json" --minimum-accuracy 95 --output "$work\calibration-diagnostic.json"
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\held_out.json" --minimum-accuracy 95 --output "$work\held-out-diagnostic.json"
# Final issuance remeasures the frozen combined catalog; only held-out case scores count toward acceptance.
& $py -m benchmarks.ocr_feasibility --manifest "$work\frozen-corpus\manifest.json" --minimum-accuracy 95 --sign-key-file "$keys\acceptance.json" --output "$work\signed-evaluator-report.json"
& $py -m tools.ocr_trust verify --report "$work\signed-evaluator-report.json" --key-file "$keys\acceptance.json" --manifest "$work\frozen-corpus\manifest.json"
```

1. Collect 3 languages x 3 real capture classes x 4 distinct documents: 36 documents, separate content groups across calibration/held-out. Supply actual originals, matching UTF-8 transcripts, complete region boxes/text/order and info.csv metadata. Do not relabel generated renderings as scans/photos.
2. A second person, independent of acquisition/transcription, checks text and geometry against originals and supplies their actual name/date/decision/attestation. Owner confirms rights, representativeness and split isolation; no tool field substitutes for those acts.
3. Freeze/tune calibration separately. Feasibility variants and split-only evaluator reports are diagnostic; they cannot enable the application. Final signed issuance requires the complete frozen manifest and genuine checked material. Production preprocessing remains unchanged.
4. Protect the acceptance key for the evaluator owner and a separate plan key for the service, outside Git. Restrict Windows folder ACLs; POSIX creation uses 0600. Do not overwrite/reuse keys casually: rotation invalidates prior signatures. No automatic signing/migration of old unsigned hybrid plans.
5. After genuine evidence passes and owner approval, configure durable `OCR_ACCEPTANCE_REPORT`, `OCR_ACCEPTANCE_KEY_FILE`, `OCR_CORPUS_MANIFEST`, `OCR_PLAN_KEY_FILE` paths in the deployment. This task did not set them. Missing keys fail closed. Finish actual Linux/font parity, visual sign-off and PyMuPDF/font-rights review before release.

## Preservation and failure notes

`finish-verification.json`: 561 starting hash entries, zero unrelated hash mismatches; 35 initially dirty tracked files: 32 byte-identical and 3 mixed files contain only the exact approved task replacements over original dirty contents. The live .env, acceptance configuration and unrelated hunks remain unchanged. No service start/restart, real provider/network connection or real-document OCR run occurred. Private snapshots and raw logs remain uncommitted. `CHANGED_FILES.txt` now lists 91 cumulative phase/review/finish paths.

Recorded transient checks: one floating-point comparison tolerance in a new test; two new Gemini mocks initially used the wrong response format for the imported configuration; initial smoke assertions used the wrong warning-envelope path and overly broad test key policy. These were corrected without production configuration changes. The PHP round-trip check exposed and fixed a real canonicalization bug. Git's existing stale-worktree cleanup permission warning remains; commits succeed and no checkout was removed.

Result: all six engineering packages completed and committed; real-document replacement remains HOLD.
Checked: final 254 Python tests, 52 PHP tests/255 assertions, 4 browser tests passed; per-package suites, four mutations, synthetic memory/scratch/service smoke and preservation.
Remaining: genuine signed held-out evidence and deployment configuration; Linux, visual and licensing owner approval.

Final cleanup verification: 254 Python passed (81.94 s), 52 PHP/255 assertions passed, 4 browser passed. No skipped tests in these final suites. Cleanup source commit: a410a7a; this final report update changes documentation/evidence only. A transient index lock was removed only after confirming no Git process was running; no source reset/stash operation was used.
