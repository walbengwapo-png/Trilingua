"""
A/B benchmark for Tier 2a: Analyzer + Prepass merge/concurrency.

Compares three modes (TRANSLATION_ANALYZER_MODE):
  - sequential: analyzer then prepass (original baseline)
  - merged:     single AI call for both
  - concurrent: run analyzer and prepass in parallel

Measures wall-clock time and LLM call counts for each.
Runs against real Ollama API when available, or mocks for structural checks.
"""
import os
import sys
import time
import json

# Add Model root to path so we can import without running as module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document.document_analyzer import DocumentAnalyzer


# ── Small test document (simulates extracted blocks) ─────────────────
SAMPLE_BLOCKS = [
    {"text": "Introduction to Machine Learning", "type": "heading"},
    {"text": "Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.", "type": "paragraph"},
    {"text": "There are three main types of machine learning: supervised learning, unsupervised learning, and reinforcement learning.", "type": "paragraph"},
    {"text": "Supervised learning uses labeled training data to learn a mapping function from input to output.", "type": "paragraph"},
    {"text": "Common algorithms include linear regression, decision trees, and support vector machines.", "type": "paragraph"},
    {"text": "Machine learning applications include image recognition, natural language processing, and recommendation systems.", "type": "paragraph"},
]


def format_result(label, elapsed_ms, llm_calls, success=True):
    """Format a benchmark result line."""
    status = "OK" if success else "FAIL"
    return f"  {label:20s}  {elapsed_ms:8.1f}ms  {llm_calls:3d} calls  [{status}]"


class BenchmarkProvider:
    """Mock AI analysis provider that simulates a real API call with delay."""
    def __init__(self, delay_ms=500, fail=False):
        self.delay_ms = delay_ms
        self.fail = fail
        self.call_count = 0

    @property
    def model_name(self):
        return "benchmark-mock"

    def analyze(self, system_prompt, user_prompt):
        """Simulate an AI call with configurable delay."""
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Simulated failure")
        time.sleep(self.delay_ms / 1000)
        return {
            "document_type": "technical_manual",
            "writing_style": "technical",
            "language": "English",
            "confidence": 0.85,
            "sections": [{"level": 1, "title": "Introduction", "start_block": 0}],
            "structure": [{"element_type": "heading", "block_index": 0, "text": "Introduction"}],
            "terminology": ["machine learning", "supervised learning"],
            "abbreviations": [{"abbreviation": "ML", "full_form": "Machine Learning"}],
            "entities": [],
            "repeated_phrases": [],
            # Prepass fields (used by merged mode)
            "summary": "This document introduces machine learning concepts and algorithms.",
            "domain": "technical",
            "translation_terms": [
                {"source": "Machine Learning", "target": "Pagkat-on sa Makina"},
                {"source": "Supervised Learning", "target": "Pagkat-on nga Gibantayan"},
            ],
        }


def test_mode_sequential(provider):
    """Run analyzer then prepass sequentially (original behavior)."""
    analyzer = DocumentAnalyzer(provider)
    call_count_before = provider.call_count

    t0 = time.perf_counter()
    profile = analyzer.analyze(SAMPLE_BLOCKS)
    t1 = time.perf_counter()

    # Simulate prepass (separate call)
    prepass_text = " ".join(b.get("text", "") for b in SAMPLE_BLOCKS[:3])
    result = provider.analyze(
        "Prepass system prompt",
        f"Analyze this text: {prepass_text}",
    )
    t2 = time.perf_counter()

    calls = provider.call_count - call_count_before
    elapsed_ms = (t2 - t0) * 1000
    return elapsed_ms, calls, True


def test_mode_merged(provider):
    """Run merged analyzer+prepass (single call)."""
    analyzer = DocumentAnalyzer(provider)
    call_count_before = provider.call_count

    t0 = time.perf_counter()
    profile, prepass_data = analyzer.analyze_with_prepass(
        SAMPLE_BLOCKS,
        source_lang="English",
        target_lang="Cebuano",
    )
    t1 = time.perf_counter()

    calls = provider.call_count - call_count_before
    elapsed_ms = (t1 - t0) * 1000

    has_prepass = bool(prepass_data.get("summary")) and bool(prepass_data.get("domain"))
    return elapsed_ms, calls, has_prepass


def test_mode_concurrent(provider):
    """Run analyzer and prepass concurrently."""
    analyzer = DocumentAnalyzer(provider)
    call_count_before = provider.call_count

    from concurrent.futures import ThreadPoolExecutor

    t0 = time.perf_counter()

    def run_analyzer():
        return analyzer.analyze(SAMPLE_BLOCKS)

    def run_prepass():
        prepass_text = " ".join(b.get("text", "") for b in SAMPLE_BLOCKS[:3])
        return provider.analyze(
            "Prepass system prompt",
            f"Analyze this text: {prepass_text}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        analyzer_future = pool.submit(run_analyzer)
        prepass_future = pool.submit(run_prepass)
        profile = analyzer_future.result()
        prepass_result = prepass_future.result()

    t1 = time.perf_counter()
    calls = provider.call_count - call_count_before
    elapsed_ms = (t1 - t0) * 1000
    return elapsed_ms, calls, True


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Tier 2a A/B Benchmark: Analyzer + Prepass Modes")
    print("=" * 60)

    # -- Test with mock provider (for structural correctness) --
    print("\n[1/2] Mock provider (500ms simulated delay per call)\n")
    provider = BenchmarkProvider(delay_ms=500)

    modes = [
        ("sequential", test_mode_sequential),
        ("merged",     test_mode_merged),
        ("concurrent", test_mode_concurrent),
    ]

    results = []
    for label, test_fn in modes:
        p = BenchmarkProvider(delay_ms=500)  # Fresh provider for each mode
        elapsed_ms, calls, ok = test_fn(p)
        print(format_result(label, elapsed_ms, calls, ok))
        results.append((label, elapsed_ms, calls, ok))

    print("\n  Summary:")
    baseline = results[0][1]  # sequential as baseline
    for label, elapsed, calls, ok in results:
        speedup = (baseline - elapsed) / baseline * 100 if baseline > 0 else 0
        print(f"    {label:20s}  {elapsed:8.1f}ms  ({speedup:+.1f}%)  {calls} calls  {'OK' if ok else 'FAIL'}")

    # -- Test with real provider if available --
    print("\n[2/2] Real Ollama provider (if available)\n")
    real_available = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        real_available = resp.status_code == 200
    except Exception:
        pass

    if not real_available:
        print("  Ollama not available — skipping real provider test.\n")
    else:
        from ai.ollama_provider import OllamaAnalysisProvider
        real_provider = OllamaAnalysisProvider(
            api_url="http://localhost:11434/api/chat",
            model=os.environ.get("OLLAMA_CLOUD_MODEL", "gpt-oss:20b-cloud"),
        )

        results_real = []
        for label, test_fn in modes:
            # Use a shared provider but reset call state
            real_provider.call_count = 0
            t0 = time.perf_counter()
            elapsed_ms, calls, ok = test_fn(real_provider)
            print(format_result(label, elapsed_ms, calls, ok))
            results_real.append((label, elapsed_ms, calls, ok))

        if results_real:
            print("\n  Summary (real Ollama):")
            baseline = results_real[0][1]
            for label, elapsed, calls, ok in results_real:
                speedup = (baseline - elapsed) / baseline * 100 if baseline > 0 else 0
                print(f"    {label:20s}  {elapsed:8.1f}ms  ({speedup:+.1f}%)  {calls} calls  {'OK' if ok else 'FAIL'}")

    print("\nDone.")
