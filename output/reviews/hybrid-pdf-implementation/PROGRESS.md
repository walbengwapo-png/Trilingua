# Hybrid PDF implementation progress

Branch: `codex/hybrid-pdf-p0-p4`.

## P0 â€” in progress
- Recorded initial dirty working tree and private byte snapshots/hashes of existing tracked application sources.
- Unrelated modifications must stay unstaged; commits will be scoped to task changes and necessary inherited OCR foundations, with mixed-file pre-existing hunks preserved separately.
- Live `.env` is hash-only, not copied or modified.
- Isolated Python 3.11 dependencies matched to the existing framework versions. Baseline: 113 Python tests passed; 24 PHP tests / 97 assertions passed.
- Offline runner initially blocked Windows internal socketpair; corrected harness, rerun passed. No application changes. Fixture, dependency and legacy font hashes: P0_BASELINE.json.
- Private baseline/source snapshots remain uncommitted. No live environment or service changes.

## P1â€“P4 â€” pending

## Release holds
No representative corpus, independent references, passing acceptance evidence, Linux runtime sign-off, visual release sign-off or licensing determination. No real category will be enabled.
