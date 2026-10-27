# Part2 Iteration Comparison and Current State Logging Audit

## Outcome

This report compares the newly measured NLLB Part2 outputs with the existing GPT-OSS PDFs and audits current TriLingua logging and metric capture. GPT-OSS PDFs are scored as supplied artifacts; no GPT-OSS translation is rerun and no runtime-performance claim is made for that iteration.

## Quality and Structure Comparison

| Direction | Iteration | BLEU | chrF | Structural check | Runtime |
|---|---|---:|---:|---|---|
| English to Cebuano | NLLB | 26.67 | 58.44 | Pass | 3.27 min |
| English to Cebuano | GPT OSS | 29.68 | 61.86 | Pass | Not supplied |
| Cebuano to English | NLLB | 31.03 | 57.0 | Pass | 2.45 min |
| Cebuano to English | GPT OSS | 52.52 | 74.33 | Pass | Not supplied |

The score method uses all-page extracted text after whitespace normalization. Both GPT-OSS PDFs have 25 pages and non-empty extracted text. Their file hashes are preserved in the comparison metadata. GPT-OSS model, provider settings, cache/fallback state, and elapsed time are not available from the supplied files.

## Current Logging and Metrics

- Laravel defaults to a stack containing the `single` file channel; a 14-day `daily` channel is defined but is not the default stack member.
- The document job logs failures and non-fatal persistence/notification issues, including job IDs, user IDs, filenames, exception messages, and a full trace on terminal translation failures.
- The Python service writes diagnostic messages to process output, including filename, language pair, size, provider/model, elapsed time, and exception text.
- `translation_history`, `translation_jobs`, `translation_blocks`, `translation_edit_logs`, and `translation_metrics` preserve operational and review evidence in the application database.
- `translation_metrics` stores provider/model, mode, durations, calls, block counts, cache counts, retranslation counts, and token counts when supplied.

## Audit Findings

- Filenames, user identifiers, exception messages, and stack traces can expose sensitive operational information in logs.
- Python diagnostic output can include language/source context; log calls should be audited before assuming document content never reaches a log sink.
- Laravel and Python do not currently emit a clearly shared correlation identifier that traces one request across the web app, queue worker, Python service, storage, and review records.
- The default single-file channel has no configured rotation, while the defined daily channel has a 14-day retention setting; retention is therefore not consistently enforced.
- Metrics, database audit records, and operational logs have different retention/security behavior and should not be treated as one equivalent log source.

## Recommended Next Steps

Adopt structured, correlation-aware operational events; minimize or hash file identifiers; remove full traces from routine production logs; define retention and access controls per data class; and test that source/translated text is never emitted to production logs. These are recommendations only and are not implemented by this report.
