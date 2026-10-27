# TriLingua Current Translation Evaluation Report

## Decision

Keep Iteration 3 paused. NLLB is the only provider that completed full SONA translations in both target languages. GPT OSS has no valid SONA quality comparison because its unchanged-source safeguard rejects title and header blocks, and its full Filipino SONA run took 89.84 minutes before rejection.

## Full SONA Results

| Provider | Target | Result | Time | BLEU | chrF | Structure |
|---|---|---|---:|---:|---:|---|
| NLLB 200 600M | Filipino | Completed | 25.49 min | 29.42 | 69.47 | Pass |
| NLLB 200 600M | Cebuano | Completed | 29.39 min | 19.08 | 65.06 | Pass |
| GPT OSS 20B cloud | Filipino | Rejected | 89.84 min | N/A | N/A | No PDF |
| GPT OSS 20B cloud | Cebuano | Not run | N/A | N/A | N/A | N/A |

## Reduced Four Page SONA Test

The representative sample is physical PDF pages 3 to 6, the first four speech-content pages. It excludes cover/front matter that contain legitimate unchanged titles and branding.

- Filipino: failed in 11.15 min; no output PDF when the unchanged-source safety check rejects a block.
- Cebuano: failed in 11.29 min; no output PDF when the unchanged-source safety check rejects a block.

## Recommendation

Do not promote GPT OSS or begin Iteration 3. First revise the unchanged-source validation to permit documented non-translatable titles, proper names, and repeating headers without accepting genuine untranslated body text. Then rerun the four-page content sample in both languages and score it against matching official reference pages before considering a full SONA rerun.

## Limitations

Scope is English to Filipino and English to Cebuano only. BLEU and chrF use normalized extracted PDF text and do not replace bilingual human review. PSF and DFS lack verified aligned references and therefore have no quality score.
