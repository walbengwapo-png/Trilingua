# -*- coding: utf-8 -*-
"""
GPT-OSS (Ollama Cloud) translation provider.

Communicates with Ollama Cloud API at http://localhost:11434/api/chat.
Always uses stream=false.
Returns only assistant.message.content.
Never exposes reasoning or provider-specific JSON.
"""

from provider_usage import ProviderStopped, ollama_post, ollama_headers, reported_tokens
import os
import json
import re
import time as _time
import requests
from dto.responses import TranslationResponse
from dto.pipeline import ProviderCapabilities, TranslationUnitResult
from .base import TranslationProvider


# Opt-in metadata-only diagnostics (GPTOSS_DIAGNOSTIC=1). Fires only on EMPTY
# responses, where the existing token counters are otherwise lost. Logs done_reason
# and counters — no model content — so 'length' (token-cap) vs 'stop'/'load'
# (genuine non-generation) can be distinguished before changing budgets.
_GPTOSS_DIAGNOSTIC = os.environ.get("GPTOSS_DIAGNOSTIC", "").lower() in ("1", "true", "yes")

# Error-message fragments that classify a failure as systemic (a provider-wide
# outage instead of an isolated per-block problem).
_SYSTEMIC_MARKERS = (
    "rate limit", "timed out", "cannot connect", "connection",
    "provider failed", "unavailable", "http 5",
)


def _diag(message: str) -> None:
    if _GPTOSS_DIAGNOSTIC:
        print(f"  [GPTOSS-DIAG] {message}")


class GPTOSSProviderError(RuntimeError):
    """Systemic GPT-OSS failure (rate limit / timeout / connection / 5xx).

    Raised only for provider-wide outages so the pipeline can fail fast
    instead of silently shipping the source text as a "successful" output.
    """


def _classify_failure(message: str) -> str:
    lowered = (message or "").lower()
    if "rate limit" in lowered:
        return "rate_limit"
    if "timed out" in lowered:
        return "timeout"
    if "cannot connect" in lowered or "connection" in lowered:
        return "connection"
    return "provider_error"


def _record_failure(ctx, category: str, count: int = 1) -> None:
    if ctx is not None:
        ctx.add_provider_failures(category, count)


class GPTOSSProvider(TranslationProvider):
    """Translation provider using GPT-OSS via Ollama Cloud."""

    # Document work is globally scheduled by TranslationPipeline.  Keep the
    # provider pool aligned with that shared eight-request capacity.
    _POOL_SIZE = int(os.environ.get("GPTOSS_TRANSLATION_SLOTS", "8"))

    def __init__(self, api_url: str = "", model: str = ""):
        self._api_url = api_url or os.environ.get("OLLAMA_CLOUD_URL", "http://localhost:11434/api/chat")
        self._model = model or os.environ.get("OLLAMA_CLOUD_MODEL", "gpt-oss:20b-cloud")
        self._headers = ollama_headers(self._api_url)
        # keep_alive: how long Ollama keeps the model loaded between requests.
        # Default 30m avoids GPU spin-up on every request without pinning the
        # model in memory indefinitely. "-1" pins it forever.
        self._keep_alive = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_maxsize=self._POOL_SIZE)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
    @property
    def max_concurrency(self) -> int:
        return self._POOL_SIZE

    @property
    def name(self) -> str:
        return "gptoss"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def batch_limits(self) -> dict:
        return {"max_batch_chars": 4000, "max_batch_items": 12}

    def translate(self, text: str, source_lang: str, target_lang: str,
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "", response_format: str = "text") -> TranslationResponse:
        """Translate a single text block using GPT-OSS via Ollama Cloud."""
        start_time = _time.time()

        # Build messages using the prompts module
        from prompts.specialized import get_system_prompt
        from prompts.translation import build_translation_prompt

        system_msg = get_system_prompt(document_type, target_lang)
        user_msg = build_translation_prompt(text, source_lang, target_lang, block_type)

        # Add context hint if provided
        if context_hint:
            user_msg = f"Previous context: {context_hint}\n\n{user_msg}"

        max_attempts = max(1, int(os.environ.get("GPTOSS_MAX_ATTEMPTS", "3")))
        request_timeout = max(10, int(os.environ.get("GPTOSS_REQUEST_TIMEOUT_SECONDS", "180")))
        # A zero normal cap lets Ollama use its model default, matching the
        # older fast/stable deployment. GPT-OSS can spend thousands of hidden
        # reasoning tokens even with think=false, so a 2k cap can return an
        # empty message. Only empty replies receive explicit larger budgets.
        normal_output_cap = int(os.environ.get("GPTOSS_MAX_OUTPUT_TOKENS", "0"))
        retry_output_cap = int(os.environ.get(
            "GPTOSS_EMPTY_RETRY_OUTPUT_TOKENS", "16384"
        ))
        num_predict = normal_output_cap if normal_output_cap > 0 else None

        for attempt in range(max_attempts):
            try:
                options = {
                    "temperature": 0.3,
                    # Leash the reasoning stage when the backend honors it.
                    "think": False,
                }
                if num_predict is not None:
                    options["num_predict"] = min(num_predict, retry_output_cap)

                payload = {
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        "stream": False,
                        "keep_alive": self._keep_alive,
                        "options": options,
                }
                if response_format == "json":
                    payload["format"] = "json"
                resp = ollama_post(self._session.post,
                    self._api_url,
                    headers=self._headers,
                    json=payload,
                    timeout=(10, request_timeout),
                )

                if resp.status_code == 429:
                    retry_header = resp.headers.get("Retry-After", "")
                    try:
                        retry_after = max(1.0, float(retry_header))
                    except (TypeError, ValueError):
                        retry_after = float(2 ** attempt)
                    if _GPTOSS_DIAGNOSTIC:
                        body = ""
                        try:
                            body = resp.text[:200].strip()
                        except ProviderStopped:
                            raise
                        except Exception:
                            pass
                        _diag(
                            f"http_429 status={resp.status_code} "
                            f"retry_after='{retry_header}' "
                            f"attempt={attempt + 1}/{max_attempts} "
                            f"body={body!r}"
                        )
                    if attempt < max_attempts - 1:
                        print(f"  [GPTOSS] Rate limited; retrying in "
                              f"{retry_after:.1f}s ({attempt + 1}/{max_attempts})")
                        _time.sleep(retry_after)
                        continue
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message="GPT-OSS rate limit reached after paced retries",
                        execution_time_ms=(_time.time() - start_time) * 1000,
                    )

                resp.raise_for_status()
                data = resp.json()

                # Extract only assistant.message.content — never expose reasoning
                result = data.get("message", {}).get("content", "").strip()

                if not result:
                    if _GPTOSS_DIAGNOSTIC:
                        _diag(
                            f"empty_response done_reason={data.get('done_reason')!r} "
                            f"eval_count={data.get('eval_count')} "
                            f"prompt_eval_count={data.get('prompt_eval_count')} "
                            f"eval_duration_ms={round((data.get('eval_duration') or 0) / 1e6, 1)} "
                            f"total_duration_ms={round((data.get('total_duration') or 0) / 1e6, 1)} "
                            f"num_predict={num_predict} prompt_chars={len(user_msg)}"
                        )
                    # A reasoning spike can occasionally consume even a large
                    # budget. Double it per retry so the attempt actually has a
                    # different (bigger) chance instead of replaying the same
                    # failure three times.
                    if attempt < max_attempts - 1:
                        if num_predict is None:
                            num_predict = min(8192, retry_output_cap)
                        else:
                            num_predict = min(max(num_predict * 2, 8192), retry_output_cap)
                        print(f"  Warning: GPT-OSS returned empty response, retrying "
                              f"with a larger budget ({attempt + 2}/"
                              f"{max_attempts})...")
                        _time.sleep(1)
                        continue
                    raise RuntimeError(
                        f"GPT-OSS returned empty response for: {text[:60]}..."
                    )

                # OPTIMIZATION: Skip hallucination detection for very short blocks (<5 words)
                src_word_count = len(text.split())
                if response_format != "json" and src_word_count >= 5:
                    from validators.hallucination_detector import sanitize_translation, detect_hallucination

                    try:
                        result = sanitize_translation(result, text)
                    except ProviderStopped:
                        raise
                    except RuntimeError as sanitize_err:
                        if ("Hallucinated repetition" in str(sanitize_err)
                                and attempt < max_attempts - 1):
                            print(f"  ⚠️  Repeated hallucination detected, retrying "
                                  f"({attempt + 1}/{max_attempts})...")
                            _time.sleep(1)
                            continue
                        elif "Hallucinated repetition" in str(sanitize_err):
                            print(f"  ⚠️  Using raw output after repetition hallucination")

                    is_hallucinated, reason = detect_hallucination(result, text)
                    if is_hallucinated and attempt < max_attempts - 1:
                        print(f"  ⚠️  Hallucination detected ({reason}), retrying "
                              f"({attempt + 1}/{max_attempts})...")
                        _time.sleep(1)
                        continue

                reported = reported_tokens(data)
                token_usage = {key: value for key, value in reported.items() if value is not None}

                elapsed_ms = (_time.time() - start_time) * 1000
                return TranslationResponse(
                    translated_text=result,
                    provider=self.name,
                    model=self._model,
                    token_usage=token_usage,
                    execution_time_ms=elapsed_ms,
                )

            except requests.exceptions.ConnectionError:
                if attempt == max_attempts - 1:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message="Cannot connect to Ollama Cloud at " + self._api_url +
                                      ". Ensure it is running.",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Connection error, retrying "
                      f"({attempt + 1}/{max_attempts})...")
                _time.sleep(1)

            except requests.exceptions.Timeout:
                if attempt == max_attempts - 1:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message="GPT-OSS request timed out",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Timeout, retrying ({attempt + 1}/{max_attempts})...")
                _time.sleep(1)

            except ProviderStopped:
                raise
            except Exception as e:
                if attempt == max_attempts - 1:
                    elapsed_ms = (_time.time() - start_time) * 1000
                    return TranslationResponse(
                        translated_text="",
                        provider=self.name,
                        model=self._model,
                        success=False,
                        error_message=f"GPT-OSS error: {str(e)}",
                        execution_time_ms=elapsed_ms,
                    )
                print(f"  Warning: Error: {e}, retrying "
                      f"({attempt + 1}/{max_attempts})...")
                _time.sleep(1)

        elapsed_ms = (_time.time() - start_time) * 1000
        return TranslationResponse(
            translated_text="",
            provider=self.name,
            model=self._model,
            success=False,
            error_message=f"GPT-OSS translation failed after {max_attempts} attempt(s).",
            execution_time_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Batch translation (DTO unit pipeline)
    #
    # One HTTP request per sub-batch. Each sub-batch is packed greedily from
    # the semantic groups the pipeline already produced, so batch boundaries
    # never cross semantic groups that OTHER batches still need for context.
    # Entries are keyed by the unit id so the response can be mapped back
    # one-to-one, in input order, with no lost or reordered blocks.
    # ------------------------------------------------------------------

    def translate_many(self, units, source_lang, target_lang,
                       context_hint="", document_type="", ctx=None):
        """Translate many TranslationUnit inputs with native GPT-OSS batching.

        Packs units into sub-batches that respect the provider batch limits,
        sends one ID-keyed JSON request per sub-batch, returns exactly one
        TranslationUnitResult per input unit in input order with the original
        unit_id intact. Every unit.context_hint rides along unchanged.

        Raise: GPTOSSProviderError for SYSTEMIC failures only (rate limit,
        timeout, connection, 5xx) so the pipeline can fail fast. Malformed
        (but HTTP-successful) batch responses retry unresolved units one by
        one. Individual per-unit failures return a `failed` result instead.
        """
        capabilities = ProviderCapabilities.from_provider(self)
        max_items = self._eff_limit(capabilities.max_batch_items,
                                    self.batch_limits["max_batch_items"])
        max_chars = self._eff_limit(capabilities.max_batch_chars,
                                    self.batch_limits["max_batch_chars"])

        ordered_ids = [u.unit_id for u in units]
        if not ordered_ids:
            return []

        sub_batches = self._pack_units(units, max_items, max_chars)
        results = {}
        aggregate_ms = 0.0

        for batch in sub_batches:
            if len(batch) == 1:
                result, elapsed = self._translate_unit_individual(
                    batch[0], source_lang, target_lang,
                    context_hint=context_hint or batch[0].context_hint,
                    document_type=document_type, ctx=ctx,
                )
            else:
                result, elapsed = self._translate_unit_batch(
                    batch, source_lang, target_lang, context_hint=context_hint,
                    document_type=document_type, ctx=ctx,
                )
            aggregate_ms += elapsed
            if isinstance(result, list):
                for r in result:
                    results[r.unit_id] = r
            else:
                results[result.unit_id] = result

        if ctx is not None:
            ctx.add_provider_request(aggregate_ms)

        return [results[unit_id] for unit_id in ordered_ids]

    @staticmethod
    def _eff_limit(provider_value, provider_limits_value):
        # Respect the tighter of ProviderCapabilities and the provider's own
        # batch_limits; 0 means "not configured" and is treated as unbounded.
        candidates = []
        if provider_value and provider_value > 0:
            candidates.append(provider_value)
        if provider_limits_value and provider_limits_value > 0:
            candidates.append(provider_limits_value)
        return min(candidates) if candidates else 1

    @staticmethod
    def _pack_units(units, max_items, max_chars):
        """Greedy sub-batch packing. Char budget counts source text only
        (metadata like context_hint is a fixed overhead per entry). Unit texts
        larger than max_chars stay in their own single-unit sub-batch."""
        batches = []
        current = []
        current_chars = 0
        for unit in units:
            unit_chars = len(unit.source_text)
            if current and (
                len(current) >= max_items or current_chars + unit_chars > max_chars
            ):
                batches.append(current)
                current = []
                current_chars = 0
            current.append(unit)
            current_chars += unit_chars
            if len(current) >= max_items:
                batches.append(current)
                current = []
                current_chars = 0
        if current:
            batches.append(current)
        return batches

    def _translate_unit_individual(self, unit, source_lang, target_lang,
                                   context_hint="", document_type="", ctx=None):
        """Single-request path via translate(). Preserves unit.context_hint
        intact. Systemic failures raise GPTOSSProviderError; isolated failures
        return a `failed` unit result so the pipeline keeps the source block."""
        start = _time.time()
        response = self.translate(
            text=unit.source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            block_type=unit.role,
            context_hint=unit.context_hint or context_hint,
            document_type=document_type,
        )
        elapsed_ms = (_time.time() - start) * 1000
        if response.success and response.translated_text:
            return (
                TranslationUnitResult(
                    unit_id=unit.unit_id,
                    status="translated",
                    translated_text=response.translated_text,
                    provider=self.name,
                    model=self._model,
                    execution_time_ms=elapsed_ms,
                ),
                elapsed_ms,
            )
        message = response.error_message or "unknown"
        if not self._single_unit_failure_is_systemic(response):
            _record_failure(ctx, "per_unit_failure")
            return (
                TranslationUnitResult(
                    unit_id=unit.unit_id,
                    status="failed",
                    translated_text=unit.source_text,
                    provider=self.name,
                    model=self._model,
                    error=message,
                    execution_time_ms=elapsed_ms,
                ),
                elapsed_ms,
            )
        category = _classify_failure(message)
        _record_failure(ctx, category)
        raise GPTOSSProviderError(message)

    @staticmethod
    def _single_unit_failure_is_systemic(response):
        message = (getattr(response, "error_message", "") or "").lower()
        return any(marker in message for marker in _SYSTEMIC_MARKERS)

    def _translate_unit_batch(self, batch, source_lang, target_lang,
                              context_hint="", document_type="", ctx=None):
        """One ID-keyed JSON batch request. HTTP-successful but malformed
        responses retry the unresolved entries individually."""
        from prompts.specialized import get_system_prompt
        system_msg = get_system_prompt(document_type, target_lang)
        user_msg = self._build_batch_user_prompt(batch, source_lang, target_lang)
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        start = _time.time()
        content = self._request_batch_chat(messages, ctx=ctx)
        elapsed_ms = (_time.time() - start) * 1000

        valid, invalid_ids = self._parse_id_keyed(content, batch)

        results = []
        if invalid_ids:
            _record_failure(ctx, "invalid_response", count=len(invalid_ids))
            print(f"  Warning: GPT-OSS batch response missing/invalid "
                  f"{len(invalid_ids)}/{len(batch)} entries; retrying individually")

        for unit in batch:
            if unit.unit_id in valid:
                results.append(
                    TranslationUnitResult(
                        unit_id=unit.unit_id,
                        status="translated",
                        translated_text=valid[unit.unit_id],
                        provider=self.name,
                        model=self._model,
                        execution_time_ms=elapsed_ms / max(1, len(valid)),
                    )
                )
                continue
            single_result, single_elapsed = self._translate_unit_individual(
                unit, source_lang, target_lang,
                context_hint=context_hint or unit.context_hint,
                document_type=document_type, ctx=ctx,
            )
            if ctx is not None:
                ctx.add_provider_retries(1)
            results.append(single_result)
            elapsed_ms += single_elapsed

        return results, elapsed_ms

    def _request_batch_chat(self, messages, ctx=None, num_predict=None):
        """POST one chat completion with the same pacing as translate() but
        raising GPTOSSProviderError on final systemic failure so the pipeline
        never turns the batch failure into a silent source-text success."""
        max_attempts = max(1, int(os.environ.get("GPTOSS_MAX_ATTEMPTS", "3")))
        request_timeout = max(10, int(os.environ.get("GPTOSS_REQUEST_TIMEOUT_SECONDS", "180")))
        normal_output_cap = int(os.environ.get("GPTOSS_MAX_OUTPUT_TOKENS", "0"))
        retry_output_cap = int(os.environ.get(
            "GPTOSS_EMPTY_RETRY_OUTPUT_TOKENS", "16384"
        ))

        for attempt in range(max_attempts):
            try:
                options = {"temperature": 0.3, "think": False}
                if num_predict is not None:
                    options["num_predict"] = min(num_predict, retry_output_cap)

                payload = {
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": self._keep_alive,
                    "format": "json",
                    "options": options,
                }
                resp = ollama_post(self._session.post,
                    self._api_url,
                    headers=self._headers,
                    json=payload,
                    timeout=(10, request_timeout),
                )

                if resp.status_code == 429:
                    retry_header = resp.headers.get("Retry-After", "")
                    try:
                        retry_after = max(1.0, float(retry_header))
                    except (TypeError, ValueError):
                        retry_after = float(2 ** attempt)
                    if attempt < max_attempts - 1:
                        print(f"  [GPTOSS] Rate limited (batch); retrying in "
                              f"{retry_after:.1f}s ({attempt + 1}/{max_attempts})")
                        _time.sleep(retry_after)
                        continue
                    _record_failure(ctx, "rate_limit")
                    raise GPTOSSProviderError(
                        "GPT-OSS rate limit reached after paced retries"
                    )

                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")

                if not content or not content.strip():
                    if attempt < max_attempts - 1:
                        if num_predict is None:
                            num_predict = min(8192, retry_output_cap)
                        else:
                            num_predict = min(max(num_predict * 2, 8192), retry_output_cap)
                        print(f"  Warning: GPT-OSS returned empty batch response, "
                              f"retrying with a larger budget ({attempt + 2}/"
                              f"{max_attempts})...")
                        _time.sleep(1)
                        continue
                    _record_failure(ctx, "empty_response")
                    raise GPTOSSProviderError(
                        "GPT-OSS returned an empty batch response after retries"
                    )
                return content.strip()

            except GPTOSSProviderError:
                raise
            except requests.exceptions.ConnectionError:
                if attempt == max_attempts - 1:
                    message = (f"Cannot connect to Ollama Cloud at {self._api_url}. "
                               "Ensure it is running.")
                    _record_failure(ctx, "connection")
                    raise GPTOSSProviderError(message)
                print(f"  Warning: Connection error (batch), retrying "
                      f"({attempt + 1}/{max_attempts})...")
                _time.sleep(1)
            except requests.exceptions.Timeout:
                if attempt == max_attempts - 1:
                    _record_failure(ctx, "timeout")
                    raise GPTOSSProviderError("GPT-OSS batch request timed out")
                print(f"  Warning: Timeout (batch), retrying "
                      f"({attempt + 1}/{max_attempts})...")
                _time.sleep(1)
            except ProviderStopped as error:
                _record_failure(ctx, "rate_limit" if error.status_code == 429 else "authentication_or_allowance")
                raise
            except Exception as e:
                if attempt == max_attempts - 1:
                    _record_failure(ctx, "provider_error")
                    raise GPTOSSProviderError(f"GPT-OSS batch error: {str(e)}")
                print(f"  Warning: Batch error: {e}, retrying "
                      f"({attempt + 1}/{max_attempts})...")
                _time.sleep(1)

        _record_failure(ctx, "provider_error")
        raise GPTOSSProviderError(f"GPT-OSS batch request failed after {max_attempts} attempt(s).")

    @staticmethod
    def _build_batch_user_prompt(batch, source_lang, target_lang):
        lines = [
            f"Translate the entries below from {source_lang} to {target_lang}.",
            "Return ONLY one valid JSON object. Each key must be one of these "
            "exact entry numbers and each value its translation.",
            f"Exact keys: {', '.join('U' + str(u.unit_id) for u in batch)}.",
            "Do not omit, add, merge, or reorder keys. Preserve names, initials, "
            "numbers, dates, URLs, and identifiers exactly. Keep the original "
            "meaning, tense, and formality; add no explanations.",
            "",
        ]
        for unit in batch:
            lines.append(f"U{unit.unit_id}: {unit.source_text}")
            if unit.context_hint:
                lines.append(f"Context for U{unit.unit_id}: {unit.context_hint}")
        return "\n".join(lines)

    @staticmethod
    def _extract_json_object(text):
        """Return the biggest balanced brace-delimited region, tolerating
        markdown fences and prose around the JSON block."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:]) if len(lines) > 1 else ""
            text = text.strip()
            if text.endswith("```"):
                text = text[:-3].rstrip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start:end + 1]
        return ""

    @classmethod
    def _parse_id_keyed(cls, content, batch):
        """Map an ID-keyed batch response back onto the expected units.

        Returns (valid: {unit_id: text}, invalid_ids: set of unit_ids that
        must be retried individually). Duplicate, missing, unexpected, and
        empty entries all land in invalid_ids.
        """
        expected_ids = {u.unit_id for u in batch}
        duplicates = set()

        def _dupe_detecting(pairs):
            seen = {}
            for key, value in pairs:
                if key in seen:
                    duplicates.add(key)
                seen[key] = value
            return seen

        extracted = cls._extract_json_object(content)
        try:
            raw = json.loads(extracted, object_pairs_hook=_dupe_detecting)
        except ProviderStopped:
            raise
        except Exception:
            # Not even a parseable JSON object — every entry is unresolved.
            return {}, expected_ids

        if not isinstance(raw, dict):
            return {}, expected_ids

        valid = {}
        invalid = set()
        regex = re.compile(r"^U?(\d+)$", re.IGNORECASE)

        for key, value in raw.items():
            match = regex.match(str(key).strip())
            if not match:
                # Unexpected/hallucinated key — reject the text entirely.
                invalid.add(None)
                continue
            unit_id = int(match.group(1))
            if unit_id not in expected_ids:
                invalid.add(unit_id)
                continue
            if key in duplicates or unit_id in valid:
                invalid.add(unit_id)
                continue
            text = (value or "").strip()
            if not text:
                invalid.add(unit_id)
                continue
            valid[unit_id] = text

        for unit in batch:
            if unit.unit_id not in valid:
                invalid.add(unit.unit_id)

        return valid, invalid

    def warmup(self) -> bool:
        """Force model loading into GPU memory by sending a tiny prompt.

        Ollama Cloud unloads models from GPU after periods of inactivity.
        This sends a minimal "hello" request so the first real translation
        doesn't pay the GPU spin-up penalty.
        """
        if os.environ.get("ALLOW_PROVIDER_WARMUP") != "1":
            return False
        try:
            resp = ollama_post(self._session.post,
                self._api_url, purpose="warmup",
                headers=self._headers,
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "user", "content": "hello"},
                    ],
                    "stream": False,
                    "keep_alive": self._keep_alive,
                    "options": {"temperature": 0.1},
                },
                timeout=120,
            )
            resp.raise_for_status()
            return True
        except ProviderStopped:
            raise
        except Exception:
            return False

    def health(self) -> dict:
        """Check if Ollama Cloud is accessible."""
        try:
            # Use the list models endpoint or just check connectivity
            base_url = self._api_url.replace("/api/chat", "")
            resp = self._session.get(f"{base_url}/api/tags", headers=self._headers, timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                available = self._model in model_names or not model_names
                return {
                    "status": "ok" if available else "degraded",
                    "provider": self.name,
                    "model": self._model,
                    "available_models": model_names[:5] if model_names else [],
                }
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": f"Ollama returned status {resp.status_code}",
            }
        except ProviderStopped:
            raise
        except Exception as e:
            return {
                "status": "unavailable",
                "provider": self.name,
                "model": self._model,
                "error": str(e),
            }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        return len(text.split())
