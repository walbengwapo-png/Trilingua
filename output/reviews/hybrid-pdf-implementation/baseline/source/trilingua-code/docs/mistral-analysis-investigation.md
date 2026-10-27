# Mistral analysis failure investigation

Investigated on 2026-09-06 against the configured local application and Mistral API.

## Findings

- `GET https://api.mistral.ai/v1/models` returned **200** with the configured key and listed `mistral-small-latest`. Authentication and model discovery worked.
- A synthetic merged document-analysis request returned **429**, with `message: Rate limit exceeded`, `type: rate_limited`, and `code: 1300`. A separate minimal request with just 16 output tokens returned the same error. Neither response supplied `Retry-After`.
- The response does not identify which workspace rate/quota limit was exceeded. It does not establish whether the restriction is requests, tokens, or another account limit. Mistral workspace usage/limits must be checked to determine that. Historical console output from the original three attempts was not persisted; the current failure was reproduced directly.
- The old analysis provider retried after one and two seconds, slept another four seconds after the last failed request, and never saved the 429 error in `last_error`. It ultimately reported `Mistral analysis failed after 3 attempts:` without the cause.
- The server selected Ollama only if the Mistral key was missing. An authenticated but rate-limited Mistral account therefore never triggered runtime fallback; the document analyzer returned a default zero-confidence profile and empty prepass context.
- The environment loader ignored `OLLAMA_ANALYSIS_MODEL` and `MISTRAL_ANALYSIS_MODEL`. The legacy Ollama default, `llama3.1:8b`, was not among the installed models.
- Once the configured `llama3.2:1b` was actually loaded, a live merged-analysis test copied schema placeholders such as `str` and returned zero confidence. The already available `gpt-oss:20b-cloud` produced a document-specific summary, medical domain, sections, and eight translated terms in about 14 seconds on the same sample. The local analysis configuration now selects that model.

## Changes

- Mistral remains the preferred analyzer. The running server makes one primary attempt, then uses Ollama on failure. A shared cooldown prevents subsequent analysis phases/documents from repeatedly hitting Mistral during its retry window; Mistral is tried again when the window expires.
- Standalone Mistral analysis calls retain bounded retries for transient errors, use longer rate-limit backoff, and honor `Retry-After`. Permanent client errors fail immediately. Long retry windows are propagated without blocking a worker for the entire interval.
- Error reports retain the HTTP status, provider message, and code. Missing keys fail before a network request. Invalid/non-object/truncated JSON is reported as an analysis error.
- Both analysis backends request JSON output. The environment loader now reads engine settings, strips quoted values/comments, and preserves process-level overrides.
- `/health` exposes analysis configuration, the last primary error, and cooldown state. A configured provider is not presented as proof that a paid chat request will succeed. Document profiles record the model that actually performed analysis, including fallback results.

## Verification

- Focused failure/recovery tests: **18 passed**. Coverage includes repeated 429s, retry headers, permanent errors, timeouts, missing keys, invalid JSON, fallback, cooldown expiry, recovery to Mistral, both providers failing, environment loading, and merged prepass context.
- Relevant unit, document reconstruction, parallel DOCX, and instrumentation tests: **176 passed, 2 skipped**.
- Live merged analysis with the replacement fallback returned a populated document profile and prepass context. The Python service was restarted with the corrected configuration and UTF-8 log output.
- A live `POST /translate/document` in balanced mode, using a synthetic English community-health document and Cebuano target, returned **HTTP 200 in 25.19 seconds** with translated file contents while Mistral was still returning 429. The analysis health state retained the rate-limit cause and showed the remaining fallback cooldown.

The application can recover from Mistral rejection; these changes cannot increase the Mistral account's quota. Automatic fallback uses the existing Ollama service and requires its configured model to remain available.

## Provider documentation

- [Mistral error glossary](https://docs.mistral.ai/resources/error-glossary)
- [Mistral JSON mode](https://docs.mistral.ai/studio/conversations/structured-output/json_mode)
