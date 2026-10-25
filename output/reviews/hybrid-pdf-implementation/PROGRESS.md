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

## P4 - pending

## Release holds
No representative corpus, independent references, passing acceptance evidence, Linux runtime sign-off, visual release sign-off or licensing determination. No real category will be enabled.
