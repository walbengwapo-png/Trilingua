# Iteration 1 — Local NLLB-200 600M Findings

Generated: 2026-09-21T10:57:50.378475+00:00

## Run Status

Completed.

## Configuration

- Provider: `nllb`
- Model: `facebook/nllb-200-distilled-600M@f8d333a098d19b4fd9a8b18f94170487ad3f821d`
- Translation fallback: disabled.
- Translation cache: disabled.
- Processing mode: `fast` (translation provider isolated from AI review).

## Full PDF Runs

| Source | Target | Status | Elapsed | BLEU | chrF | Structural layout |
|---|---|---|---:|---:|---:|---|
| English PSF Brochure.pdf | Filipino | completed | 4.69 min | N/A | N/A | pass |
| English PSF Brochure.pdf | Cebuano | failed | 4.92 min | None | None | N/A |
| SONA_2019_English.pdf | Filipino | completed | 25.49 min | 29.42 | 69.47 | pass |
| SONA_2019_English.pdf | Cebuano | completed | 29.39 min | 19.08 | 65.06 | pass |

The PSF Brochure has no verified Filipino or Cebuano reference translation; its BLEU and chrF values are intentionally N/A.

## Two-Page SONA Stability

| Target | Successful runs | Median latency | Stable output |
|---|---:|---:|---|
| Filipino | 3/3 | 1.61 min | True |
| Cebuano | 3/3 | 1.52 min | True |

## Scope and Limitations

- Scope is English-to-Filipino and English-to-Cebuano only; reverse directions are out of scope.
- SONA BLEU/chrF uses normalized extracted PDF text against official reference editions and is not a substitute for human bilingual review.
- Structural layout is an automated page-count and non-empty-text check, not a visual review.
