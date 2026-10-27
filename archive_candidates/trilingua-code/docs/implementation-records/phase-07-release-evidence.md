# Phase 7 — Release evidence (R8)

Date: 2026-09-28 · Branch: `walben` · Scope per plan package 7 (R8): spacing contract, deterministic Python suite, honest quality wording, acceptance matrix.

## Commands & results

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_properties.py -q` | **23 passed** (was 17 passed / 2 failed at baseline — the 2 failures are now green) |
| `python -m pytest tests -q --ignore=tests/test_concurrency_benchmark.py --ignore=tests/test_reference_gemini_workflow.py -m "not slow and not golden and not font_regression" -p no:cacheprovider` | **350 passed, 35 deselected** — deterministic gate, no network calls |
| (same, without `-m` filter to expose live dependencies) | 383 passed, 2 skipped — the 2 skips are live Gemini attempts in `test_units.py:2616,2694` (`@pytest.mark.slow`) |
| `python -m pytest tests/test_properties.py -q -k round_trip` (baseline) | Before fix: `FAILED Round-trip failed. Input '0  0' Expected '0 0'` — genuine red |
| `php artisan test` (after wording edits) | **366 passed, 1 skipped** (1506 assertions) — skip is `AuthCssRenderingTest > compiled css file contains custom styles` (requires compiled asset) |

## R8 decisions and code changes

1. **Spacing contract: NORMALIZED.** A whitespace run inside a block is layout-neutral; every downstream consumer of chunk output is word-token based (`text.split()` budgets, NLLB word-truncation, layout planners, validators), and the split path already rejoined with single spaces — so the verbatim `return [text]` fast path was the only divergent branch. Both splitters now normalize: `Model/document/chunker.py::ChunkSplitter` and `Model/document_translator_v3.py::Chunk_Splitter` return `[" ".join(tokens)]` on every non-recursive path (fast path, no-candidate path, short-tail merge) and document the contract: `" ".join(chunks) == " ".join(text.split())`. Docstrings updated. No document-fidelity damage: block structure/order/types carry layout, and translated output is rebuilt from translated text, never from source spacing.
2. **Focused regression** added to `Model/tests/test_properties.py` for both splitters (Property 2b):
   - `test_chunk_repeated_spaces_are_normalized` — the R8 evidence case `'0  0'`. 
   - `test_chunk_repeated_spaces_real_document_like_case` — “Mrs.  Smith   arrived.   Thank you.”
   - `test_chunk_no_sentence_boundary_still_normalizes` — no-candidate path.
   - `test_chunk_multi_chunk_normalized_round_trip` — split path across repeated spaces.
3. **Deterministic vs live separation.** The benchmark module (`test_concurrency_benchmark.py`) runs a load test at import/collection time and rewrites `Model/tests/concurrency_report.json` (an untracked artifact). It is excluded from the deterministic command above, as is `test_reference_gemini_workflow.py` (live model). The two `@pytest.mark.slow` Gemini-dependent tests in `test_units.py` are deselected with the `-m` filter so normal CI never issues live API calls; recorded as intentionally skipped live dependencies.
4. **Honest quality wording.** `quality_score` is an automated AI-review signal, not calibrated accuracy. Display copy changed (no test asserted the old labels):
   - Labels “Quality Score” → “AI Review Signal” (admin review text/document meta, history detail) and “Avg quality”/“Avg Quality Score” → “Avg AI Review Signal” (profile, user/admin dashboards).
   - Every dot/badge surface now carries a clear title/`aria-label`: “Automated AI review signal — not human-verified accuracy.” (`history`, `bookmarks`, `admin/queue`, block scores in review-document, `components/quality-badge`).
   - Admin dashboard sub text: “Automated AI review signal, not human-verified”.
   - Threshold colors (low/medium/high dots) are retained only as review-triage ordering, with the non-verified caveat attached.

## Acceptance matrix (R8 item 4)

Evidence codes: **V-auto** = verified by automated Laravel/Python tests (mock providers); **V-static** = verified by static code + rendering/browser-independent checks; **P-live** = pending: needs a real service, real producer application openability, or human meaning/layout judgment.

| Format | Intake/queue/completion (V-auto) | Preview path (V-auto/V-static) | Fallback honesty (V-auto) | Openability in real Office/PDF viewer (P-live) |
| --- | --- | --- | --- | --- |
| docx | V-auto (controller + job tests) | mammoth via `document-preview.js`, converter host rendered (`DocumentPreviewTest`); `write_docx` formatting properties round-trip (Python) | n/a | P-live |
| pdf | V-auto | same-origin iframe route (`DocumentPreviewTest`) | reached on error | P-live |
| txt | V-auto | plain-text renderer | n/a | P-live |
| md | V-auto | plain-text renderer | n/a | P-live |
| rtf | V-auto | stripped-text renderer | reached on error | P-live |
| odt | V-auto | block fallback only | V-auto (labeled text preview with layout caveat) | P-live |
| csv | V-auto | table renderer | n/a | P-live |
| pptx | V-auto | pptx-preview (src wiring) | reached on error | P-live |
| xlsx | V-auto | SheetJS (src wiring) | n/a | P-live |

| Dimension | Verified | Pending |
| --- | --- | --- |
| Language pairs | en↔fil mocked pipeline, dedup, quota, job-state tests | Real-engine meaning review across pairs |
| Document variety | short/long (property tests), structured (tables, formatting properties), layout overflow (mocked fitz) | Real scanned-document OCR accuracy on representative corpus; layout-sensitive PDF/DOCX human check |
| Storage backends | Local backend (StorageService + ownership tests) | Supabase-backed run (no credentials in this environment; `.env.example` only) |
| Downloads | Owner-authorized download + retranslate reuse (Laravel feature tests) | Real file open in MS Office/LibreOffice/Adobe |

## Remaining release conditions (unverified P-live items)
- Representative human meaning/layout review across the format × language-pair cells and pass thresholds per plan section 8 are not established; quality/layout acceptance criteria remain open until a human-evaluated sample set is run.
- Real-service provider validation (Gemini/live fallbacks) and Supabase integration not executed here.
- Browser-level keyboard/mobile/long-document measurement meaningful only against a served app; currently covered statically.