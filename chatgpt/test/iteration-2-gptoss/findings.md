# Iteration 2 — Current GPT-OSS Findings

Generated: 2026-09-21T11:11:12.707232+00:00

## Run Status

Stopped by user request before all planned measurements completed.

## Configuration

- Provider: `gptoss`
- Model: `gpt-oss:20b-cloud`
- Translation fallback: disabled.
- Translation cache: disabled.
- Processing mode: `fast` (translation provider isolated from AI review).

## Full PDF Runs

| Source | Target | Status | Elapsed | BLEU | chrF | Structural layout |
|---|---|---|---:|---:|---:|---|
| English PSF Brochure.pdf | Filipino | failed | 11.47 min | None | None | N/A |
| English PSF Brochure.pdf | Cebuano | completed | 21.76 min | N/A | N/A | pass |
| SONA_2019_English.pdf | Filipino | failed | 89.84 min | None | None | N/A |

The PSF Brochure has no verified Filipino or Cebuano reference translation; its BLEU and chrF values are intentionally N/A.

## Two-Page SONA Stability

Not run.

## Scope and Limitations

- Scope is English-to-Filipino and English-to-Cebuano only; reverse directions are out of scope.
- SONA BLEU/chrF uses normalized extracted PDF text against official reference editions and is not a substitute for human bilingual review.
- Structural layout is an automated page-count and non-empty-text check, not a visual review.
- The user stopped the remaining GPT-OSS SONA Cebuano and stability measurements to shorten evaluation time.
