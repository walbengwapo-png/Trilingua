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

## P3-P4 - pending

## Release holds
No representative corpus, independent references, passing acceptance evidence, Linux runtime sign-off, visual release sign-off or licensing determination. No real category will be enabled.
