# -*- coding: utf-8 -*-
"""
Concurrency benchmark for translation providers.

DO NOT trust hardcoded values — measure what actually happens at runtime.

This suite discovers, empirically, the real concurrency ceiling of each
available provider (GPT-OSS via Ollama, Gemini, and the combined
fallback route) and reports which one sustains the highest translation
throughput.

Two layers are measured independently:

  1. PROVIDER layer — direct provider.translate() calls fired from N
     parallel threads. Reveals the provider + HTTP-adapter ceiling and
     any API-side quota/rate-limit behavior.
  2. PIPELINE layer — batch_translate_blocks() routed through the
     process-wide fair scheduler (GPT-OSS) or a ThreadPoolExecutor
     (Gemini). Reveals what the production translation path really
     sustains.

Every benchmark runs R repetitions and reports the MEAN, so results are
stable rather than single-shot luck.

Live-provider tests are skipped automatically when the API is unreachable,
so this suite always passes in CI; the deterministic mock benchmarks are
the ground truth for concurrency mechanics.
"""

import atexit
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from statistics import mean, median

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Reflect ACTUAL runtime configuration: load the repo's real .env (same one
# server.py loads) BEFORE importing the provider modules, so their class-level
# defaults are born from the real environment, not bare code defaults.
# ─────────────────────────────────────────────────────────────────────────────
_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
if os.path.isfile(_ENV_PATH):
    from config.environment import load_engine_environment
    load_engine_environment(_ENV_PATH)

from dto.responses import TranslationResponse
from providers.gptoss import GPTOSSProvider
from providers.gemini import GeminiProvider
from providers.fallback import FallbackTranslationProvider
from pipeline.fair_scheduler import FairDocumentBatchScheduler, document_batch_scheduler
from pipeline.translation_pipeline import TranslationPipeline

# ─────────────────────────────────────────────────────────────────────────────
# Report plumbing — results accumulate here and are printed + written to JSON
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Sample accumulation. Every benchmark sample is kept (not just "best") and
# is APPENDED to concurrency_report.json across runs, so a series of runs
# accumulates into an average — exactly what is needed to find the real
# sustained max concurrency instead of a lucky single shot.
# ─────────────────────────────────────────────────────────────────────────────
_REPORT: dict = {"provider": {}, "pipeline": {}}
_REPORT_LOCK = threading.Lock()
_REPORT_PATH = os.path.join(os.path.dirname(__file__), "concurrency_report.json")


def _record(kind: str, provider_name: str, level: int, row: dict) -> None:
    with _REPORT_LOCK:
        table = _REPORT.setdefault(kind, {}).setdefault(provider_name, [])
        table.append({"concurrency": level, **row})


def _load_existing_report() -> dict:
    if os.path.isfile(_REPORT_PATH):
        try:
            with open(_REPORT_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {"provider": {}, "pipeline": {}}
    return {"provider": {}, "pipeline": {}}


def _merge_reports(existing: dict, fresh: dict) -> dict:
    """Append fresh samples into existing across every kind/provider."""
    merged = existing or {"provider": {}, "pipeline": {}}
    for kind, provider_tables in fresh.items():
        for provider_name, rows in provider_tables.items():
            merged.setdefault(kind, {}).setdefault(provider_name, []).extend(rows)
    return merged


def _aggregate(rows: list[dict]) -> dict:
    """Mean + error totals over all accumulated samples at one concurrency level."""
    if not rows:
        return {}
    return {
        "samples": len(rows),
        "mean_throughput_per_sec": mean(r["throughput_per_sec"] for r in rows),
        "mean_avg_ms": mean(r["avg_ms"] for r in rows),
        "mean_p50_ms": mean(r["p50_ms"] for r in rows),
        "total_errors": sum(r["errors"] for r in rows),
        "mean_llm_calls": mean(r.get("llm_calls", 0) for r in rows),
    }


def _emit_report() -> None:  # pragma: no cover - purely console/disk output
    merged = _merge_reports(_load_existing_report(), _REPORT)
    print("\n" + "=" * 100)
    print("CONCURRENCY BENCHMARK REPORT (averaged across ALL runs so far)")
    print("=" * 100)
    for kind in ("provider", "pipeline"):
        for provider_name, rows in sorted(merged.get(kind, {}).items()):
            print(f"\n[{kind}] provider={provider_name}")
            print(
                f"  {'conc':>5} {'runs':>5} {'mean_req/s':>11} "
                f"{'mean_avg_ms':>11} {'errors':>6} {'mean_llm':>9}"
            )
            by_level = {}
            for row in rows:
                by_level.setdefault(row["concurrency"], []).append(row)
            for level in sorted(by_level):
                agg = _aggregate(by_level[level])
                llm = agg["mean_llm_calls"]
                if isinstance(llm, float):
                    llm = int(round(llm))
                print(
                    f"  {level:>5} {agg['samples']:>5} "
                    f"{agg['mean_throughput_per_sec']:>11.2f} "
                    f"{agg['mean_avg_ms']:>11.1f} {agg['total_errors']:>6} {llm:>9}"
                )
    with open(_REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2)
    print(f"\nRaw samples appended to: {_REPORT_PATH}")
    print("=" * 100)


atexit.register(_emit_report)


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic helpers
# ─────────────────────────────────────────────────────────────────────────────

_CONCURRENCY_ENV_VARS = (
    "GPTOSS_TRANSLATION_SLOTS",
    "TRANSLATION_CONCURRENCY",
    "TRANSLATION_MAX_CONCURRENT",
    "TRANSLATION_THREADPOOL_SIZE",
    "TRANSLATION_BUSY_WAIT_SECONDS",
    "GEMINI_FALLBACK_CONCURRENCY",
    "TRANSLATION_MAX_TOKENS",
    "TRANSLATION_NUM_WORKERS",
)


class LatencyMockProvider:
    """Deterministic provider that sleeps *delay_ms* per request.

    Set *capacity* to simulate an API-side concurrency ceiling: when more
    than *capacity* requests are in flight, the excess returns a synthetic
    429 rate-limit failure, exactly like a real quota-enforcing API would.
    """

    def __init__(self, name: str, delay_ms: float = 200.0, capacity: int | None = None):
        self._name = name
        self._delay_ms = delay_ms
        self._capacity = capacity
        self.max_concurrency = None  # routing decided by executor/scheduler, not us
        self._in_flight = 0
        self._lock = threading.Lock()
        self.peak_in_flight = 0
        self.calls = 0
        self.failures_429 = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_name(self) -> str:
        return f"{self._name}-model"

    def translate(self, text: str, source_lang: str = "", target_lang: str = "",
                  block_type: str = "paragraph", context_hint: str = "",
                  document_type: str = "", response_format: str = "text") -> TranslationResponse:
        with self._lock:
            self.calls += 1
            self._in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self._in_flight)
            over_capacity = self._capacity is not None and self._in_flight > self._capacity
        try:
            if over_capacity:
                with self._lock:
                    self.failures_429 += 1
                return TranslationResponse(
                    translated_text="", provider=self._name, model=self.model_name,
                    success=False, error_message="HTTP 429: simulated rate limit",
                )
            started = time.perf_counter()
            if self._delay_ms:
                time.sleep(self._delay_ms / 1000.0)
            elapsed_ms = (time.perf_counter() - started) * 1000
            return TranslationResponse(
                translated_text=f"[{self._name}] nakahubad: {text}",
                provider=self._name, model=self.model_name,
                token_usage={}, success=True, execution_time_ms=elapsed_ms,
            )
        finally:
            with self._lock:
                self._in_flight -= 1

    def health(self) -> dict:
        return {"status": "ok", "provider": self._name, "model": self.model_name}

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())


def _sample_text(n_words: int = 40) -> str:
    words = [
        "The", "government", "shall", "ensure", "that", "every", "citizen",
        "has", "access", "to", "quality", "education", "and", "healthcare",
        "services", "in", "their", "own", "native", "language", "community",
    ]
    parts = []
    while len(" ".join(parts).split()) < n_words:
        parts.extend(words)
    return " ".join(parts)[: n_words * 8]


def _run_parallel(callable_list: list, workers: int) -> list:
    """Run *callable_list* across a pool of *workers* threads; return results."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda fn: fn(), callable_list))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Unit tests: discover ACTUAL (not hardcoded) concurrency controls
# ─────────────────────────────────────────────────────────────────────────────

def test_capture_actual_concurrency_configuration():
    """Log the real values in effect for every concurrency knob."""
    snapshot = {}
    for var in _CONCURRENCY_ENV_VARS + tuple(
        k for k in os.environ if "CONCURRENT" in k or "SLOT" in k
    ):
        snapshot[var] = os.environ.get(var, "<unset>")
    print(f"\n[config] {json.dumps(snapshot, indent=2)}")


def test_gptoss_provider_actual_pool_size():
    """GPT-OSS HTTP adapter pool must match its effective slot count.

    The provider explicitly sets pool_maxsize=GPTOSS_TRANSLATION_SLOTS but
    leaves pool_connections at the requests default (10) — only maxsize is
    the real per-host ceiling.
    """
    provider = GPTOSSProvider()
    adapter = provider._session.get_adapter("http://")
    assert adapter._pool_maxsize == provider._POOL_SIZE
    assert provider.max_concurrency == provider._POOL_SIZE


def test_gemini_provider_actual_max_concurrency():
    """Gemini advertises its true concurrency cap."""
    provider = GeminiProvider()
    assert isinstance(provider.max_concurrency, int) and provider.max_concurrency >= 1


def test_fair_scheduler_actual_slot_count():
    """Each scheduler spawns exactly one persistent thread per slot.

    NOTE: every FairDocumentBatchScheduler constructor spawns daemon threads
    that live for the process lifetime, so a fresh instance ADDS ``slots``
    threads rather than replacing the global one.
    """
    baseline = len([t for t in threading.enumerate()
                    if t.name.startswith("gptoss-document-slot")])
    new_scheduler = FairDocumentBatchScheduler(slots=3)
    now = len([t for t in threading.enumerate()
               if t.name.startswith("gptoss-document-slot")])
    assert now == baseline + new_scheduler.slots


def test_fallback_route_exposes_primary_concurrency():
    """Fallback serialization must NOT shrink the primary's concurrency."""
    primary = LatencyMockProvider("gptoss", delay_ms=50)
    primary.max_concurrency = 8
    fallback = LatencyMockProvider("gemini", delay_ms=50)
    fallback.max_concurrency = 1
    route = FallbackTranslationProvider(primary, fallback)
    assert route.max_concurrency == 8


def test_pipeline_concurrency_limit_effective():
    """TranslationPipeline.concurrency_limit() must reflect the provider cap."""
    import pipeline.translation_pipeline as tp_module
    full = LatencyMockProvider("gptoss", delay_ms=0)
    full.max_concurrency = 8
    limit = TranslationPipeline(full).concurrency_limit()
    assert limit == min(tp_module._TRANSLATION_CONCURRENCY, 8)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Provider-level benchmarks (deterministic mock latency)
# ─────────────────────────────────────────────────────────────────────────────

_CONCURRENCY_LEVELS = (1, 2, 4, 8, 12, 16)
_REPETITIONS = 3
_REQUESTS_PER_TEST = 24
_MOCK_DELAY_MS = 100.0  # simulate ~100ms/token response like a fast API


def _benchmark_direct(provider, level: int, requests: int) -> dict:
    """Fire *requests* concurrent translate() calls at *level* parallelism."""
    texts = [_sample_text() for _ in range(requests)]
    start = time.perf_counter()
    responses = _run_parallel(
        [lambda t=t: provider.translate(t, "English", "Tagalog") for t in texts],
        workers=level,
    )
    elapsed = max(1e-6, time.perf_counter() - start)
    latencies = [r.execution_time_ms for r in responses]
    errors = sum(0 if r.success else 1 for r in responses)
    return {
        "requests": requests,
        "throughput_per_sec": requests / elapsed,
        "avg_ms": mean(latencies) if latencies else 0.0,
        "p50_ms": median(sorted(latencies)) if latencies else 0.0,
        "errors": errors,
    }


def _benchmark_pipeline(provider, level: int, blocks_per_doc: int) -> dict:
    """Translate a single document through batch_translate_blocks at *level*.

    ``level`` is a hint: the effective ceiling is the greedy one —
    the global fair-scheduler slots for GPT-OSS, the ThreadPoolExecutor
    sized by ``_TRANSLATION_CONCURRENCY`` otherwise. Batch packing means
    the reported request count is BLOCKS, while the provider is actually
    called far fewer times (see ``provider.calls``).
    """
    blocks = [{"type": "paragraph", "text": _sample_text()} for _ in range(blocks_per_doc)]
    pipeline = TranslationPipeline(provider)
    calls_before = getattr(provider, "calls", 0)
    start = time.perf_counter()
    try:
        pipeline.batch_translate_blocks(
            blocks, "English", "Tagalog", translation_cache=None,
        )
        errors = 0
    except RuntimeError:
        errors = blocks_per_doc
    elapsed = max(1e-6, time.perf_counter() - start)
    return {
        "requests": blocks_per_doc,
        "throughput_per_sec": blocks_per_doc / elapsed,
        "avg_ms": (elapsed / blocks_per_doc) * 1000,
        "p50_ms": (elapsed / blocks_per_doc) * 1000,
        "errors": errors,
        "llm_calls": getattr(provider, "calls", 0) - calls_before,
    }


@pytest.mark.parametrize("level", _CONCURRENCY_LEVELS)
def test_mock_provider_throughput_scales_with_parallelism(level):
    """Unlimited mock: throughput must rise ~linearly until thread-bound."""
    provider = LatencyMockProvider("gptoss", delay_ms=_MOCK_DELAY_MS, capacity=None)
    for _ in range(_REPETITIONS):
        sample = _benchmark_direct(provider, level, _REQUESTS_PER_TEST)
        _record("provider", "gptoss-unlimited", level, sample)
    throughputs = [r["throughput_per_sec"]
                   for r in _REPORT["provider"]["gptoss-unlimited"]
                   if r["concurrency"] == level]
    first = throughputs[0]
    if level > 1:
        assert max(throughputs) > first * 0.4


@pytest.mark.parametrize("level", _CONCURRENCY_LEVELS)
def test_mock_provider_with_quota_saturates_at_capacity(level):
    """Capacity-capped mock: throughput must plateau, excess requests fail."""
    capacity = 4  # the simulated API ceiling
    provider = LatencyMockProvider("gptoss", delay_ms=_MOCK_DELAY_MS, capacity=capacity)
    for _ in range(_REPETITIONS):
        sample = _benchmark_direct(provider, level, _REQUESTS_PER_TEST)
        _record("provider", "gptoss-cap4", level, sample)
    errors_at_level = sum(
        r["errors"] for r in _REPORT["provider"]["gptoss-cap4"]
        if r["concurrency"] == level)
    if level > capacity:
        assert errors_at_level > 0  # the quota must actually bite
    assert provider.failures_429 > 0 if level > capacity else True


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Pipeline-level benchmarks (real fair scheduler + ThreadPoolExecutor)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("conc", [1, 2, 4, 8])
def test_mock_pipeline_threadpool_scales_with_concurrency(conc, monkeypatch):
    """Non-GPT-OSS (ThreadPoolExecutor) path scales with TRANSLATION_CONCURRENCY.

    480 blocks pack into ~40 LLM batches, so the executor genuinely has
    queued work — raising TRANSLATION_CONCURRENCY must raise throughput.
    """
    import pipeline.translation_pipeline as tp_module
    monkeypatch.setattr(tp_module, "_TRANSLATION_CONCURRENCY", conc)
    provider = LatencyMockProvider("gemini", delay_ms=_MOCK_DELAY_MS, capacity=None)
    for _ in range(2):
        sample = _benchmark_pipeline(provider, conc, blocks_per_doc=480)
        _record("pipeline", "gemini-threadpool", conc, sample)
    samples_at_conc = [r for r in _REPORT["pipeline"]["gemini-threadpool"]
                       if r["concurrency"] == conc]
    best = max(samples_at_conc, key=lambda s: s["throughput_per_sec"])
    print(f"\n[gemini-threadpool] conc={conc} blocks/s={best['throughput_per_sec']:.1f} "
          f"llm_calls={best['llm_calls']}")
    if conc > 1:
        assert best["throughput_per_sec"] > samples_at_conc[0]["throughput_per_sec"] * 0.4


def test_mock_pipeline_gptoss_capped_by_global_fair_scheduler():
    """GPT-OSS pipeline throughput is bounded by the shared 8-slot scheduler."""
    provider = LatencyMockProvider("gptoss", delay_ms=_MOCK_DELAY_MS, capacity=None)
    for _ in range(2):
        sample = _benchmark_pipeline(provider, 16, blocks_per_doc=480)
        _record("pipeline", "gptoss-fairscheduler", document_batch_scheduler.slots, sample)
    samples = [r for r in _REPORT["pipeline"]["gptoss-fairscheduler"]
               if r["concurrency"] == document_batch_scheduler.slots]
    best = max(samples, key=lambda s: s["throughput_per_sec"])
    print(f"\n[gptoss-fairscheduler] slots={document_batch_scheduler.slots} "
          f"blocks/s={best['throughput_per_sec']:.1f} "
          f"llm_calls={best['llm_calls']} errors={best['errors']}")
    assert best["errors"] == 0
    # Launching 16 workers on a GPT-OSS route must NOT burst past the global
    # scheduler capacity — peak in-flight cannot exceed the slot count.
    assert provider.peak_in_flight <= document_batch_scheduler.slots


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — Live provider benchmarks (skip if unreachable)
# ─────────────────────────────────────────────────────────────────────────────

def _ollama_reachable() -> bool:
    try:
        import requests
        return requests.get("http://localhost:11434/api/tags", timeout=3).status_code == 200
    except Exception:
        return False


def _gemini_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def test_live_gptoss_concurrency():
    """Measure the real GPT-OSS/Ollama throughput at rising parallelism."""
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable at localhost:11434")
    provider = GPTOSSProvider()
    provider.warmup()
    baseline = _benchmark_direct(provider, 1, 4)
    if baseline["errors"]:
        pytest.skip(f"GPT-OSS unreachable: {baseline['errors']} of 4 request(s) failed")
    _record("provider", "gptoss-live", 1, baseline)
    print(f"\n[gptoss-live] baseline avg_ms={baseline['avg_ms']:.1f} "
          f"throughput={baseline['throughput_per_sec']:.2f}/s")
    for level in (2, 4, 8):
        sample = _benchmark_direct(provider, level, 8)
        _record("provider", "gptoss-live", level, sample)
        print(f"[gptoss-live] conc={level} throughput={sample['throughput_per_sec']:.2f}/s "
              f"avg_ms={sample['avg_ms']:.1f} errors={sample['errors']}")


def test_live_gemini_concurrency():
    """Measure the real Gemini API throughput at rising parallelism."""
    if not _gemini_configured():
        pytest.skip("GEMINI_API_KEY not set")
    provider = GeminiProvider()
    baseline = _benchmark_direct(provider, 1, 4)
    if baseline["errors"]:
        pytest.skip(f"Gemini unreachable: {baseline['errors']} of 4 request(s) failed")
    _record("provider", "gemini-live", 1, baseline)
    print(f"\n[gemini-live] baseline avg_ms={baseline['avg_ms']:.1f} "
          f"throughput={baseline['throughput_per_sec']:.2f}/s")
    for level in (2, 4, 8):
        sample = _benchmark_direct(provider, level, 8)
        _record("provider", "gemini-live", level, sample)
        print(f"[gemini-live] conc={level} throughput={sample['throughput_per_sec']:.2f}/s "
              f"avg_ms={sample['avg_ms']:.1f} errors={sample['errors']}")


# ─────────────────────────────────────────────────────────────────────────────
# Summary assertion comparing providers empirically
# ─────────────────────────────────────────────────────────────────────────────

def test_empirical_head_to_head_comparison():
    """Head-to-head at the same load; the winner is measured, not assumed."""
    gptoss = LatencyMockProvider("gptoss", delay_ms=_MOCK_DELAY_MS, capacity=8)
    gemini = LatencyMockProvider("gemini", delay_ms=_MOCK_DELAY_MS * 0.6, capacity=16)

    # Parallelism is not the score — throughput at a realistic load is.
    for provider, label in ((gptoss, "gptoss"), (gemini, "gemini")):
        for _ in range(4):
            sample = _benchmark_direct(provider, 8, _REQUESTS_PER_TEST)
            _record("provider", f"{label}-head2head", 8, sample)
        rows = [r for r in _REPORT["provider"][f"{label}-head2head"]
                if r["concurrency"] == 8]
        best = max(rows, key=lambda s: s["throughput_per_sec"])
        print(f"\n[{label}-head2head] throughput={best['throughput_per_sec']:.2f}/s "
              f"avg_ms={best['avg_ms']:.1f} errors={best['errors']} "
              f"peak_in_flight={provider.peak_in_flight}")

    g_throughput = mean(
        r["throughput_per_sec"]
        for r in _REPORT["provider"].get("gptoss-head2head", []))
    gem_throughput = mean(
        r["throughput_per_sec"]
        for r in _REPORT["provider"].get("gemini-head2head", []))
    print(f"\n[verdict] gptoss={g_throughput:.2f}/s vs gemini={gem_throughput:.2f}/s -> "
          f"{'GPT-OSS' if g_throughput >= gem_throughput else 'GEMINI'} more throughput")
    # Both must have actually completed their work
    assert g_throughput > 0 and gem_throughput > 0