# Hybrid PDF implementation progress

Branch: `codex/hybrid-pdf-p0-p4`.

## P0 - complete
- Recorded initial dirty working tree and private byte snapshots/hashes of existing tracked application sources.
- Unrelated modifications must stay unstaged; commits will be scoped to task changes and necessary inherited OCR foundations, with mixed-file pre-existing hunks preserved separately.
- Live `.env` is hash-only, not copied or modified.
- Isolated Python 3.11 dependencies matched to the existing framework versions. Baseline: 113 Python tests passed; 24 PHP tests / 97 assertions passed.
- Offline runner initially blocked Windows internal socketpair; corrected harness, rerun passed. No application changes. Fixture, dependency and legacy font hashes: P0_BASELINE.json.
- Private baseline/source snapshots remain uncommitted. No live environment or service changes.

## P1 - implemented with conservative holds
- Region inventory covers native/raster mixed pages, hidden or occluded native text, shared occurrences and drawing candidates. Uncalibrated signals hold uncertain regions.
- Acceptance checked before recognition. No new PDF reflow. Strict native preflight holds overflow before redaction, without continuation pages.
- All-held output preserves original bytes, persists an empty-block v3 sidecar, exposes complete/partial/untranslated counts and warnings through history/status/review/download; backend verification refuses incomplete output.
- Tests: 119 Python tests passed; new PHP persistence/review tests: 2 tests, 10 assertions. Historical reflow-sidecar regeneration retained.
- Related inherited OCR foundations included. Unrelated Phase A changes remain unstaged. Local dedup helper tested; OCR-candidate integration and calibration remain P3/release work.

## P2 - code/schema complete; corpus absent
- Added v2 JSON schema and runtime checks for screenshots, calibration/heldout splits, document/content isolation, independent reference checks, real-capture provenance, byte hashes and complete expected region lists.
- Legacy cases remain diagnostic. Calibration never grants acceptance. Removed 5-10 ceiling; require valid reviewed frozen corpus, disjoint content and category calibration plus eligible heldout material.
- Separate word accuracy, region recall, missed/false-positive regions and reading order. 95% minimum remains unchanged; no live acceptance settings modified.
- Tests: 10 evaluator/contract tests passed. No corpus, scans or acceptance evidence created.

## P3 - renderer/code complete; real end-to-end exit blocked
- Added image_reconstructor.py: word-contained glyph masks, thin-rule/neighbor exclusions, multi-sample flatness/gradient checks, color extraction, residual checks, bounded 10 pt fit, source shape font estimates and per-asset validation.
- Single PDF assembly updates only the pixel stream of an asset proven to have one simple opaque, unclipped, non-overlapping occurrence. No global replace_image and no color-overlay source-removal claim. Other assets retain byte invariants. Saved edited images are verified by decoded pixel hashes and visible searchable target text.
- Eight Noto Sans/Serif family/weight font files and OFL source text pinned to upstream revision/hashes. Rights and PyMuPDF licensing review remain open; no legal determination made.
- OpenCV headless 4.13.0.92 installed only into isolated venv; requirements-ocr-layout.txt records dependencies. No live environment change.
- OCR now retains paragraph/word geometry; SETTINGS version 2 requires matching evidence for this changed extraction shape. 95% unchanged. Unknown capture origin requires all scan/photo/screenshot evidence scopes before OCR.
- Tests: 48 focused tests passed. Fixed-geometry tests cover real pixel cleanup, searchability/diacritics, non-flat holds, rules/neighbors/confidence, fit, shared assets, mixed native/link/vector and unchanged asset preservation. These are not acceptance material.
- Real scanned/mixed OCR acceptance and owner visual sign-off cannot be completed without genuine reviewed corpus; all real categories remain HOLD. P4 hardening continues independently.

## P4 - code/Windows checks complete; release exits held
- Sidecar v3 / render plan v2 freezes original, runtime, algorithm, font and mask hashes, geometry, fill colors and fit decisions. Regeneration uses saved masks and current block text with zero recognition/translation; rejects mismatches or unfittable edits before atomic publication. Updated fit plans persist with the published file through the PHP envelope/transaction.
- New PDF and image-upload jobs use strict image-preserving output. v1/v2 historical reflow sidecars retain their reconstruction path. Held native entries retain source text, are not editable as translations, and incomplete documents cannot be verified.
- Partial/untranslated labels propagate through response/status/download names, history/detail, My Documents (no false 100% label), admin region/font review and regeneration. Incomplete extraction does not become a full document word count.
- One isolated PDF process per operation, serialized across threads/processes with a file lock. PDF/OCR descendants are contained on timeout. 50 pages, 40 MP, 60 s Tesseract calls, 8 MB aggregate encoded masks, 16 MB plan and 24 MB sidecar/result bounds. Default 900 s deadline is reduced against service/job/worker budgets; late output is refused. In-flight provider requests retain existing transport timeouts.
- Windows verification: 179 Python tests passed; final affected-renderer/service checks 48 passed; PHP 49 tests / 239 assertions passed; browser 2 passed with all routes intercepted and no app server; pip check passed. A stale six-category readiness expectation was updated for screenshot support after the first final run failed.
- Font tests cover all eight packaged family/weights and English/Cebuano/Filipino glyph roundtrips, combining accents and strict native punctuation without host fonts. Actual Linux execution remains unverified.
- Index-only Python snapshot (without unrelated dirty hunks): 178 passed, 1 skipped; full working-tree suite: 179 passed. The private export contains Model files, not all external test fixtures.
- Preservation: unrelated tracked source hashes and .env match the starting snapshots. Pre-existing Phase A hunks stay unstaged. Git emitted a pre-existing stale-worktree metadata cleanup permission warning; commits succeeded, and no checkout was removed.
- Real OCR acceptance, independent reference review, Linux execution, visual sign-off and licensing/embedding review remain release holds. No live service or acceptance settings changed; no real category enabled.

## Release holds
No representative corpus, independent references, passing acceptance evidence, Linux runtime sign-off, visual release sign-off or licensing determination. No real category will be enabled.

## Engineering finish
Follow-up implementation on `codex/hybrid-pdf-finish`: report HMAC and evaluator issuance, signed plan v3 with immutable block metadata and PHP JSON canonicalization,120 MP default aggregate admission, disk-staged cleaned images, parent scratch cleanup/stale leases, provider timeout/retry caps, diagnostic OCR kit, and held/signed-fixture service smoke. All four requested safety mutations were killed in a private export and restored. Current package results, owner commands and remaining real-evidence/Linux/rights holds are in `FINISH.md`. No real input was processed or acceptance setting changed.
