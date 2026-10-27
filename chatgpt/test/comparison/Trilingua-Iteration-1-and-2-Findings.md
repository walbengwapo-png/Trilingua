# TriLingua Iteration 1 and 2 Findings

Generated: 2026-09-21T14:24:07.437225+00:00

## Scope

This controlled evaluation covers English-to-Filipino and English-to-Cebuano only. Reverse translation directions were not tested.

## Current Evaluation Status

The NLLB iteration completed. The GPT-OSS iteration was stopped by user request after its Filipino SONA run failed and before its Cebuano SONA run and stability repetitions began.

## SONA 2019 Results

| Provider | Target | Status | BLEU | chrF | Time (ms) | Structural layout |
|---|---|---|---:|---:|---:|---|
| gptoss | Filipino | failed | None | None | 5390690.19 | None |
| nllb | Filipino | completed | 29.42 | 69.47 | 1529123.51 | pass |
| gptoss | Cebuano | None | None | None | None | None |
| nllb | Cebuano | completed | 19.08 | 65.06 | 1763559.85 | pass |

## Rating Method

SONA scores use automatically normalized PDF text and official Filipino/Cebuano editions as references. BLEU and chrF measure lexical overlap; they do not replace bilingual human evaluation. The PSF Brochure has no verified reference translation, so its output is reported only for completion and structural layout.

## Operational Findings

- NLLB completed both SONA translations with passing automated structural checks. Its two-page excerpt was stable across all three runs for both targets.
- NLLB rejected the Cebuano brochure after three blocks remained unchanged; no false-success PDF was produced.
- GPT-OSS rejected the Filipino brochure after one unchanged block and rejected Filipino SONA after two unchanged blocks.
- GPT-OSS completed the Cebuano brochure with a passing automated structural check, but its planned Cebuano SONA and all stability measurements were not run after the user-requested stop.

## Full Artifact Inventory and Failures

| Provider | Source | Target | Status | Time | Output file | Failure/validation note |
|---|---|---|---|---:|---|---|
| nllb | English PSF Brochure.pdf | Filipino | completed | 4.69 min | English PSF Brochure__en-to-fil.pdf | pass |
| nllb | English PSF Brochure.pdf | Cebuano | failed | 4.92 min | — | {"detail":"Translation error: Translation failed for 3 block(s). block 57: Translation failed: providers returned the source text unchanged for target language Cebuano.; block 71: Translation failed: providers returned the source text unchanged for target lang… |
| nllb | SONA_2019_English.pdf | Filipino | completed | 25.49 min | SONA_2019_English__en-to-fil.pdf | pass |
| nllb | SONA_2019_English.pdf | Cebuano | completed | 29.39 min | SONA_2019_English__en-to-ceb.pdf | pass |
| gptoss | English PSF Brochure.pdf | Filipino | failed | 11.47 min | — | {"detail":"Translation error: Translation failed for 1 block(s). block 56: Translation failed: providers returned the source text unchanged for target language Filipino.. The source document was not returned as a false successful translation."} |
| gptoss | English PSF Brochure.pdf | Cebuano | completed | 21.76 min | English PSF Brochure__en-to-ceb.pdf | pass |
| gptoss | SONA_2019_English.pdf | Filipino | failed | 89.84 min | — | {"detail":"Translation error: Translation failed for 2 block(s). block 3: Translation failed: providers returned the source text unchanged for target language Filipino.; block 187: Translation failed: providers returned the source text unchanged for target lan… |

## NLLB Stability Detail

| Target | Runs | Median latency | Distinct output hashes | Result |
|---|---:|---:|---:|---|
| Filipino | 3/3 | 1.61 min | 1 | stable |
| Cebuano | 3/3 | 1.52 min | 1 | stable |

The two-page excerpt source is pages 3–4 of the English SONA PDF (5,131 extracted characters). GPT-OSS stability samples were not run because the user stopped the remaining evaluation.

## Reproducibility

- Inputs are recorded with SHA-256 hashes in `benchmark-manifest.json`; the original source PDFs were not modified.
- NLLB model: `facebook/nllb-200-distilled-600M` at revision `f8d333a098d19b4fd9a8b18f94170487ad3f821d`, local-only CPU execution.
- GPT-OSS model: `gpt-oss:20b-cloud` through the current configured service.
- Both providers ran with fallback disabled, translation cache disabled, and `fast` mode.

## Decision Gate

GPT-OSS qualifies for a future Iteration 3 only when it meets or exceeds NLLB on both BLEU and chrF for both tested targets, without a structural regression.

**Result:** No provider promotion is recommended from this run.

## Pause

No GPT-OSS translation-logic change was made. Iteration 3 remains paused pending review of these artifacts.
