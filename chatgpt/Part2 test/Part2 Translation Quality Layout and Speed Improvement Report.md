# Part2 Translation Quality Layout and Speed Improvement Report

## Executive Finding

NLLB completed both 25-page Part2 translations with intact page counts and deterministic short-sample outputs. However, the supplied GPT-OSS artifacts have higher automatic quality scores in both directions. Engine-recorded model-call time accounts for most NLLB runtime, so the next improvement should use a quality-first mode and review workflow for user-facing documents, while optimizing the NLLB inference path separately and only retaining speed changes that pass the same quality gate.

## Evidence

| Direction | NLLB BLEU | NLLB chrF | NLLB time | NLLB calls | Model-call share | GPT-OSS BLEU | GPT-OSS chrF |
|---|---:|---:|---:|---:|---:|---:|---:|
| English to Cebuano | 26.67 | 58.44 | 3.27 min | 49 | 79.3% | 29.68 | 61.86 |
| Cebuano to English | 31.03 | 57.0 | 2.45 min | 48 | 90.6% | 52.52 | 74.33 |

Both NLLB outputs contain 25 pages and extractable text. Three repeated short samples per direction produced one output hash each. Visual checks of first, middle, and last output pages found no clipping, overlap, or page-count regression in this story-book corpus. This corpus contains no complex tables, so it does not establish table-layout quality.

## Quality Improvements

1. Keep the completed `fast` run as the speed baseline, but evaluate `balanced` as the normal user-facing NLLB path. Fast disables document analysis, document memory, semantic chunking, specialized prompts, AI quality review, cache, prepass, and layout planning. Balanced enables the first six quality features and the prepass.
2. Add a bilingual review set and score grammar, naturalness, tone, coherence across pages, terminology consistency, and meaning preservation. Use the reviewer for final acceptance, not BLEU or chrF alone.
3. Enable document memory and a glossary for recurrent names, theological terms, labels, headers, and book terminology. Save approved terminology by language pair and expose it to the review/retranslation workflow.
4. Enable AI quality review and the opt-in coherence-polish pass for Cebuano and Filipino only after it has passed the bilingual gate. Re-translate only flagged blocks, then rerun the review so a repair cannot silently worsen tone or meaning.
5. Treat titles, headers, brand names, URLs, page numbers, and source-language labels as protected or explicitly allowed passthrough spans. This prevents quality checks from either forcing awkward translations or accepting genuine untranslated body text.

## Layout Improvements

The current PDF reconstructor preserves source coordinates and tries, in order, a larger text rectangle, smaller font, and a continuation box. It can reduce text to 6 pt and a continuation box can reach the page boundary. That is a safety mechanism, not a layout-quality guarantee.

1. Add a preflight fit check before painting text: measure translated text in its original rectangle, evaluate a limited set of font and line-spacing adjustments, and choose the best fit before writing to the page.
2. Record an overflow event for every block that needs expansion, font reduction, continuation, or clipping. Fail layout QA when a continuation is clipped or a text box overlaps another content box.
3. Create a separate layout fixture set with tables, long table cells, captions, multicolumn pages, headers/footers, mixed fonts, and image-adjacent labels. The current story-book evidence cannot validate these structures.
4. Preserve the source font family and style when supported; apply a target-language fallback font only when the original cannot render the required glyphs. Use a document-specific minimum readable font rule approved by the reviewer rather than relying on the hard 6 pt fallback.
5. Add rendered-image comparison checks for page count, text-box collisions, text outside the media/crop area, and unreadable/blank text. Review all changed pages when a layout intervention occurs.

## Speed Improvements

Do not optimize extraction or reconstruction first: engine-recorded model-call time consumed 79.3% of the English-to-Cebuano runtime and 90.6% of the Cebuano-to-English runtime. NLLB currently processes one item at a time, serializes generation with a lock, and uses four beams by default.

1. Add a batched NLLB translation path that tokenizes compatible blocks together, generates in an ordered batch, and keeps per-block retry/error handling. Benchmark batch sizes 2, 4, and 8 under the same corpus and memory limit.
2. Sweep `NLLB_TORCH_THREADS` using the actual host core count, recording latency, CPU utilization, and output hashes. Keep the fastest stable setting that does not change the approved quality result.
3. Compare beam counts 4, 2, and 1 against the bilingual quality gate. A lower beam count is accepted only if it does not introduce a critical meaning/grammar/tone regression and stays within the agreed automatic-score tolerance.
4. Keep the model warm and enable the privacy-reviewed exact-block cache for production only. The controlled evaluation correctly kept cache disabled; caching improves repeated content, not first-pass translation quality.
5. Run GPT-OSS and NLLB under one identical timed protocol before choosing a production provider. GPT-OSS scored higher in the supplied artifacts, but no elapsed-time, configuration, or provider metadata was supplied, so it cannot yet be called faster or promoted on this evidence alone.

## Acceptance Gate

For each language direction and document type, release a change only when: every output page renders cleanly; no table/text box is clipped or overlaps; no protected span becomes a false translation failure; the bilingual reviewer finds no critical meaning, grammar, tone, or cohesion defect; automatic scores do not regress beyond the agreed threshold; and median latency improves or remains acceptable for the selected quality mode.

## Recommended Order

First, establish bilingual and layout fixture acceptance tests. Second, evaluate NLLB balanced mode plus glossary, memory, review, and coherence polish against the fast baseline. Third, implement and benchmark batched inference, thread tuning, and beam-count variants. Finally, run an identical GPT-OSS benchmark before any provider decision.
