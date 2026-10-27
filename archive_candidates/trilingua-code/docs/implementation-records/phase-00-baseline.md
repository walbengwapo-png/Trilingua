# Phase 0 — Baseline & failure reproductions

Date: 2026-09-28 · Branch: `walben` · Work tree: 96 modified files + untracked artifacts (preserved).

## Commands & results

| Command | Result |
| --- | --- |
| `php tests/assert-safe-test-env.php` | OK (APP_ENV=testing, sqlite `:memory:`, no cached config) |
| `php artisan test` | **294 passed, 1 skipped** (1150 assertions, 23.8s) |
| `python -m pytest Model/tests -q --ignore=Model/tests/test_concurrency_benchmark.py -m "not slow and not golden and not font_regression"` | 354 passed, 3 failed, 35 deselected |
| `python -m pytest Model/tests/test_properties.py -q` | 17 passed, 2 failed |
| `python -m pytest Model/tests/test_properties.py::test_chunk_content_round_trip -q` | 1 passed (seed-dependent) |
| Direct repro: `Chunk_Splitter().split('0  0')` | `['0  0']` → reconstructed `'0  0'` ≠ expected `'0 0'` (**genuinely red**) |

## Findings

1. **Laravel baseline green**: 294/1. No fixed-admin test evidence needed to change yet.
2. **Python deterministic suite baseline is flaky at the edges**:
   - `test_context_hint_truncation_triggered_for_long_hints` — Hypothesis `DeadlineExceeded` (stable under load).
   - `test_table_structural_preservation` — Hypothesis `DeadlineExceeded` (stable under load).
   - `test_docx_paragraph_formatting_preservation` — Hypothesis `DeadlineExceeded` (flaky; passes when run alone).
   - All three pass individually → performance/deadline flakes, not logic failures. Phase 7 will add explicit `deadline=None`/`@settings` for these I/O-heavy property tests.
3. **Spacing round-trip is a genuine latent defect**, seed-dependent: the chunker fast path returns short inputs verbatim (`'0  0'`), violating the test's normalized-equality contract. The plan's "red test" is real; the earlier passing run did not generate a multi-space input. Phase 7 fixes the contract (normalize per chunk) per the layout-preservation rule.
4. Live/benchmark file `test_concurrency_benchmark.py` excluded throughout; it is the only writer of `concurrency_report.json` and is reserved for the separate real-service acceptance activity.

## Remaining risk
- Hypothesis deadline flakes may reappear under high load until Phase 7 settings adjustments.
- Baseline excludes live-provider/real-storage/browser checks by design (separate gates).