# Existing poster: live translation and reconstruction test

**Result: the pipeline ran, but the output is not an acceptable translated poster.**

Input: the existing DFS five-second-test poster (`day-03-five-second-test-1080x1350.png`). Source: English. Target: Cebuano. One live request used the configured `gpt-oss:20b-cloud` provider. The run took about 34 seconds and produced a one-page PDF from 13 OCR blocks (10 translated, 3 numeric passthrough blocks).

## Observed failures

- OCR read “TEST” as “rest”; the translation consequently used “pahulay” (rest).
- “CAN PEOPLE TELL” became “MAKASUGOD BA ANG MGA TAO”, changing the meaning.
- “WHAT YOU DO” became “ANO ANG IMONG GINABUHAT”, with nonstandard/mixed wording for the requested Cebuano output.
- “WHO IT’S FOR” became the unclear “KINIYA KINSA”.
- The reconstructed PDF is a plain translated-text page. It does not retain the poster background, frames, typography or original placement. It contains zero embedded images.

## What passed

The provider returned a real translation response. The PDF opened, rendered, and passed saved-text coverage validation. All generated text was present. This checks file integrity/content placement, not translation accuracy or preservation of source artwork.

The rendered PDF was visually inspected against the original poster. Translation findings are a qualitative spot check, not a measured bilingual score. The original image was not edited. OCR errors were intentionally left uncorrected to test the actual path. No application quality gate or upload setting was changed; the gate was stubbed only in this isolated diagnostic process.

## Files

- `translated_DFS_5_second_poster.pdf`: actual generated output.
- `translated-page-1.png`: rendered output inspected during review.
- `source-and-translation.json`: block-by-block comparison.
- `provider-requests.json`: request count, elapsed time and provider-reported token usage.
- `result.json`: functional results and reviewed findings.

Actual replacement of words inside the original poster artwork remains unimplemented. This diagnostic does not approve normal image support or satisfy the 95% acceptance gate.
