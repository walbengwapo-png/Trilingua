# Hybrid PDF engineering finish

Branch: `codex/hybrid-pdf-finish`, based on `eb8dff7`.
Real-document replacement remains HOLD. No real corpus, reviewer sign-off or production acceptance report will be created.

## Packages
1. Report HMAC trust, evaluator issuance, key/verify CLI: implemented. P1 full suites:229 Python,52 PHP/254 assertions,4 browser passed.
2. Signed render-plan provenance and PHP persistence: implemented. P2 full suites:234 Python,52 PHP/255 assertions,4 browser passed.
3. Aggregate pixel budget, bounded assembly, parent scratch and provider deadline cap: implemented; focused72 tests passed. Full suites follow its commit.
4. Diagnostic intake/feasibility/reference/manifest kit — pending.
5. Held-state service smoke and isolated signed-fixture test — pending.
6. Mutation checks, inventory/docs/preservation — pending.

## Baseline
217 Python tests;52 PHP tests/254 assertions;4 browser tests passed. Same handoff suites, outbound Python sockets denied and browser traffic intercepted. No services started.

Production loaders will reject fixture-marked keys and material unconditionally. The signed-fixture demonstration will use test-owned monkeypatches only, with no configuration flag enabling fixture evidence. HMAC protects against accidental/casual enablement, not an administrator holding the key.

Private starting hashes and dirty snapshots are in `baseline/finish-start/`; .env is hash-only. Per-package suite logs and outcomes follow as work completes.

P1 post-package:229 Python,52 PHP/254 assertions,4 browser passed. P2 full suites follow its commit.

Resource probe:16 synthetic images x240,000 pixels,720,000-pixel test budget:3 admitted,13 held before hash lookup. Peak19,523,120 bytes via tracemalloc (does not include MuPDF native heap); arrays stage per image to owned scratch before any stream mutation. Hard-kill scratch cleanup and active/stale lease tests pass. Provider transport caps and retry waits use request-local remaining deadlines; no provider call was made. First focused run had one floating-point assertion boundary failure, corrected with a1-microsecond comparison tolerance.

First resource full run:240 passed,2 mock failures. Server import selected the configured Interactions model while new mocks supplied generateContent responses. Tests now select their mocked model explicitly; no production model/configuration change. Full rerun follows.
