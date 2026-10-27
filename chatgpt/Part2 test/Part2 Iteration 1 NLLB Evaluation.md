# Part2 Iteration 1 NLLB Evaluation

## Outcome

The Part2 NLLB evaluation completed the English-to-Cebuano and Cebuano-to-English translations using the supplied 25-page parallel story-book editions. The accompanying JSON artifacts preserve source/reference hashes, engine evidence, output hashes, structural checks, quality scores, and repeat-run results.

## Configuration

- Provider: `nllb`
- Model: `facebook/nllb-200-distilled-600M@f8d333a098d19b4fd9a8b18f94170487ad3f821d`
- Processing: `fast` mode, automatic PDF column detection
- Fallback: disabled
- Translation cache: disabled
- Quality method: corpus BLEU and chrF using all extracted PDF pages with whitespace normalization only

## Full Document Results

| Direction | Status | Elapsed | BLEU | chrF | Structural check |
|---|---|---:|---:|---:|---|
| English to Cebuano | Completed | 3.27 min | 26.67 | 58.44 | Pass |
| Cebuano to English | Completed | 2.45 min | 31.03 | 57.0 | Pass |

## Stability Results

| Direction | Successful runs | Median latency | Output hashes | Stable output |
|---|---:|---:|---:|---|
| en-to-ceb | 3/3 | 0.25 min | 1 | True |
| ceb-to-en | 3/3 | 0.17 min | 1 | True |

## Method and Limits

The English original was scored against the supplied Cebuano edition, and the Cebuano edition was scored against the supplied English original. BLEU and chrF measure overlap with those particular editions; they do not replace bilingual review for naturalness, theology, age appropriateness, or page-level visual quality. Structural validation verifies page count and extractable text, while the rendered-output review checks for visible layout defects.

## Traceability

The report is reconciled with `iteration-1-nllb-200-600m/benchmark-manifest.json`, `findings.json`, and `run-metadata.json`. The source and reference PDFs are not modified.
