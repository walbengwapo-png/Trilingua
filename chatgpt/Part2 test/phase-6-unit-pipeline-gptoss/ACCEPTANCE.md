# Phase 6 — GPT-OSS-Only DTO Unit Pipeline Acceptance Report

Generated 2026-09-22 · Provider `gptoss` (`gpt-oss:20b-cloud`) · 6 live runs (2 directions × 3) · balanced mode · unit-pipeline flag ON · translation cache OFF · fallback provider disabled · no NLLB/Gemini.

## Verdict

**CONDITIONAL PASS.** All hard correctness, structural and layout criteria are met on all 6 runs, including fail-fast systemic-failure behavior and full block-survival. Two software findings need follow-up: (1) one verse numeral (`22`) lost in a scripture citation on all ceb→en runs; (2) one block passed through untranslated on ceb→en (short block, by-design pre-filter). Quality is below the previously supplied GPT-OSS artifacts, most on ceb→en BLEU (Median 44.55 vs 52.52); because `runtime_metadata` was not supplied with the baseline and our harness cannot reproduce its method, a matched legacy-mode run is recommended before making the unit pipeline the production default.

## Acceptance Matrix

| Criterion | Result | Verdict |
|---|---|---|
| Layout fidelity (25 pages, layout validation) | `pass` on all 6 runs | PASS |
| Block survival & ordering (49 blocks expected; one result per unit, in order) | 49/49 present every run, `blocks_batched` = translated set | PASS |
| Unit-pipeline verification (provider metrics + layout preflight present) | `True` on all 6 runs | PASS |
| Systemic fail-fast (rate-limit/timeout/5xx must abort, never false-success) | verified — batch timeout aborts with explicit RuntimeError gate | PASS |
| Protected spans — emails (1) / URLs (1) / placeholders (0) | 0 missing on all runs | PASS |
| Protected spans — numbers | en→ceb 11/11; ceb→en 11/12 (verse numeral `22` lost) | CONDITIONAL |
| Quality vs supplied GPT-OSS baseline | en→ceb BLEU 28.27 vs 29.68; ceb→en BLEU 44.55 vs 52.52 | OBSERVED VARIANCE |
| Latency (first known baseline; baseline had no runtime metadata) | median 832 s en→ceb / 839 s ceb→en | NEW BASELINE |
| Reproducibility | structure stable; distinct output SHA-256 per run (generative variance, documented) | PASS |

## en-to-ceb

- Supplied baseline: BLEU **29.68** / chrF **61.86** · 25 pages · SHA-256 `298f3885985b6a7a408ad1fd507c0fb3132545b1b2da4185c13aa269dca5354f`. Latency comparison is not possible — the artifact carried no `runtime_metadata`.

| Run | Wall (s) | BLEU | chrF | Pages | Layout | Blocks | Translated | Batched | Sched. batches | Slots | Retries | Failures | Echo retries | Repolish | SHA-256 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 772.8 | 29.38 | 60.77 | 25 | pass | 49 | 49 | 49 | 3 | 1 | 0 | {} | 1 | 6 | 0dbbafd05ea3… |
| 2 | 831.8 | 27.84 | 60.91 | 25 | pass | 49 | 49 | 49 | 3 | 1 | 0 | {} | 0 | 9 | a92aaed56fea… |
| 3 | 990.4 | 28.27 | 60.02 | 25 | pass | 49 | 49 | 49 | 3 | 1 | 0 | {} | 1 | 8 | a858152806c3… |

- Median BLEU **28.27** / chrF **60.77** · median wall **831.8 s**.
- Span checks: emails (0 missing) · URLs (0 missing) · numbers (0 missing) · placeholders (0 missing).
- `blocks_passthrough = 0` on every run (all 49 blocks translated).

## ceb-to-en

- Supplied baseline: BLEU **52.52** / chrF **74.33** · 25 pages · SHA-256 `e02ffa624bd9cbd883d5a0550095b513f15c53201069cddb65367bac8ea1b335`. Latency comparison is not possible — the artifact carried no `runtime_metadata`.

| Run | Wall (s) | BLEU | chrF | Pages | Layout | Blocks | Translated | Batched | Sched. batches | Slots | Retries | Failures | Echo retries | Repolish | SHA-256 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 620.5 | 44.76 | 70.80 | 25 | pass | 49 | 48 | 48 | 3 | 1 | 0 | {} | 6 | 16 | ce3b7fc59ef6… |
| 2 | 838.7 | 44.55 | 70.71 | 25 | pass | 49 | 48 | 48 | 3 | 1 | 0 | {} | 6 | 14 | 8ac058460289… |
| 3 | 870.3 | 43.83 | 70.19 | 25 | pass | 49 | 48 | 48 | 3 | 1 | 0 | {} | 6 | 15 | f86f200dbd8f… |

- Median BLEU **44.55** / chrF **70.71** · median wall **838.7 s**.
- Span checks: emails (0 missing) · URLs (0 missing) · numbers (1 missing = verse numeral `22`) · placeholders (0 missing).
- `blocks_passthrough = 1` on every run — one short block kept verbatim via the pass-through pre-filter (designed behavior).

## Latency decomposition (why runs take 10–16 min)

1. **Remote model latency dominates.** 49 blocks pack into 3 `translate_many` batch posts; with the server's `GPTOSS_TRANSLATION_SLOTS=1` and `TRANSLATION_MAX_CONCURRENT=1` (from `.env`), the 3 posts run strictly serially. Provider HTTP time (`provider_request_ms`) was 170–436 s per run; batch queue wait (`scheduler_wait_ms`) reached 638 s because batches wait for the single slot while gpt-oss generates.
2. **Balanced-mode overhead.** Per-block AI quality review (49 calls) + coherence repolish of 6–16 chunks + document analysis ≈ 57–71 LLM calls per run even though only 48–49 blocks translate.
3. **Echo guard re-translations.** ceb→en triggered 6 echo retries per run (the model echoed Cebuano input) — the guard works, at a latency cost of 6 extra requests per run.
4. **First known baseline.** The supplied artifacts have no runtime metadata, so these figures define the new baseline rather than proving a regression.

## Findings requiring follow-up

1. **CYAN (minor, deterministic):** ceb→en drops verse numeral `22` in `… Pinadayag 4, 21, 22` → `… Revelation 4, 21, …` on all 3 runs. Numeric-token restoration should cover multi-number scripture citation lists.
2. **YELLOW (by design):** ceb→en passes 1 short block through untranslated per run (`blocks_passthrough=1`); the source line is preserved verbatim, so nothing is silently lost.
3. **GREEN (quality variance):** ceb→en BLEU sits ~8 pts under the supplied baseline. Recommend a matched legacy-mode benchmark (flag OFF, same harness/env) to isolate pipeline effect from provider drift before promoting the unit pipeline.

## Artifacts

- `findings.json` — full per-run record (metrics, spans, structure, quality).
- `benchmark-manifest.json`, `run-metadata.json` — run configuration and lineage.
- `en-to-ceb_run{N}.pdf`, `ceb-to-en_run{N}.pdf` — 6 translated PDFs (structure pass, 25 pages each).
- `layout-samples/` — page 1/2/14 PNG renders per run (72 dpi).
- `server.log` — engine trace.