# TriLingua Provider Neutral Pipeline Improvement Report

## Decision

Improve the document-translation pipeline independently of NLLB or GPT-OSS. NLLB is not the architecture reference; it is only the reproducible local benchmark from the requested Part2 run. GPT-OSS is not a permanent default either. The pipeline must supply the same document context, terminology controls, quality gate, layout protection, scheduling, and observability to every provider. A provider is selected only after it passes the same quality, reliability, and measured-latency gate.

## Evidence

| Direction | NLLB BLEU / chrF | NLLB elapsed | Supplied GPT-OSS BLEU / chrF | Structure |
|---|---:|---:|---:|---|
| English to Cebuano | 26.67 / 58.44 | 3.27 min | 29.68 / 61.86 | 25 pages; non-empty text for both |
| Cebuano to English | 31.03 / 57.0 | 2.45 min | 52.52 / 74.33 | 25 pages; non-empty text for both |

Both NLLB outputs were 25-page, non-empty PDFs and had deterministic three-run short samples. The supplied GPT-OSS artifacts scored higher automatically in both directions, but they include no reproducible elapsed time, configuration, cache/fallback state, or provider metadata. Therefore the evidence supports GPT-OSS as a quality candidate, not an unconditional production choice.

## Target Pipeline

```text
extract PDF structure
→ build document map and reading order
→ identify protected spans and glossary terms
→ group semantic translation units with local context
→ schedule provider-neutral translation tasks
→ apply quality review and selective repair
→ preflight layout fit and reconstruct
→ render and validate
→ persist privacy-safe metrics and audit evidence
```

## Provider Neutral Interfaces

1. `TranslationUnit`: stable unit ID, page, reading order, bounding box, element role, parent section, prior/next context, table row/column headers, source text, and protected spans.
2. `ProviderCapabilities`: supported language pairs, maximum batch size, concurrency limit, context limit, streaming support, and cost/latency metadata. The scheduler reads capabilities rather than branching on provider name.
3. `translate_many(units, context, glossary)`: ordered batch result with one status/error per unit. It must preserve the unit ID even when one item fails or retries.
4. `QualityResult`: quality score, issue category, source/target snippets, repair eligibility, and reviewer provenance. It is independent from the translation provider.
5. `LayoutResult`: original/final rectangle, original/final font, expansion/reduction/continuation actions, collision status, and clipping status.

## Quality Improvements

### Context and Cohesion

- Replace isolated PDF blocks with semantic units. A paragraph keeps its heading and adjacent paragraphs; a table cell keeps its row/column header; repeated headers/footers are identified as document furniture.
- Build one document summary and terminology memory once per document. Pass only the relevant section summary, adjacent context, and glossary terms to each unit rather than repeatedly sending the entire file.
- Mark URLs, numbers, product names, page labels, brand names, and approved proper nouns as protected spans. They should survive unchanged without being mistaken for untranslated body text.
- Use a bilingual human rubric for grammar, naturalness, tone, coherence, cohesion, terminology, and meaning preservation. BLEU and chrF remain regression signals, not acceptance criteria.

### Review and Repair

- Run a provider-independent quality reviewer after initial translation. It flags missing content, source-language echoes, grammar/tone defects, inconsistent terms, and broken cross-reference context.
- Retry only the failed unit with its document context and the reviewer issue. Re-review the repaired unit and retain the original if the repair is worse.
- Offer a reviewer-approved glossary per language pair so the same educational or subject-specific term is never independently guessed on every page.

## Layout Improvements

- Preserve each source block's reading order, bounding box, alignment, font family, weight, color, and paragraph spacing where the target glyphs can render.
- Preflight every translated unit against its target rectangle before painting it. Choose an approved font/line-spacing adjustment before reconstruction instead of relying on a last-resort 6 pt minimum font or a continuation that can reach the page boundary.
- Emit a layout event whenever text expands, shrinks, continues, collides, or clips. A clipped continuation, overlap, or text outside the page box is a release failure.
- Add fixtures for tables, long table cells, columns, headings, captions, headers/footers, images, and mixed fonts. The current story-book corpus has no complex tables, so it cannot prove table quality.
- Render all changed pages and run visual regression checks for clipping, bleed/out-of-page text, collisions, blank text, and unexpected font substitution.

## Speed Improvements

- Use a capability-based scheduler: batch compatible units, obey the active provider's bounded concurrency, preserve output order, and isolate per-unit retries.
- For local sequence-to-sequence models, benchmark padded batched generation, host-specific Torch thread counts, and beam counts. Keep only variants that pass the same bilingual and layout gate.
- For remote models, limit inflight requests, combine only compatible short units, apply retry/backoff per unit, and record queue wait separately from provider latency.
- Cache only approved exact translations keyed by a privacy-safe hash of source, target, provider/model revision, glossary version, and quality profile. Do not use cache results across models or quality profiles.
- Keep model startup warm and run document analysis once per file. Do not spend effort optimizing PDF extraction/reconstruction before provider latency, because NLLB model calls dominate the measured Part2 run.

## Provider Selection Policy

Use a registry rather than a hard-coded NLLB or GPT-OSS path. Every provider must run the same corpus, quality rubric, layout fixtures, and timed protocol. Promote a provider for a quality profile only when it has no critical bilingual-review defects, passes every layout check, has reproducible configuration and metadata, meets the agreed latency target, and has an acceptable failure/retry rate.

Current recommendation: retain GPT-OSS as the leading final-quality candidate because the supplied Part2 artifacts scored higher, but do not make it mandatory or remove NLLB until GPT-OSS completes the controlled reproducibility, latency, and reliability gate. Retain NLLB as a local baseline and possible draft/offline provider, not as the pipeline design authority.

## Implementation Order

1. Introduce document-map, protected-span, and provider-capability interfaces with tests.
2. Add semantic unit grouping, section context, and glossary memory.
3. Add provider-neutral review/repair and bilingual acceptance fixtures.
4. Add layout preflight, layout events, table/column fixtures, and rendered regression checks.
5. Add capability-based batching/scheduling, cache namespace controls, and stage timing.
6. Run NLLB and GPT-OSS through the identical benchmark and select the provider per quality profile.
