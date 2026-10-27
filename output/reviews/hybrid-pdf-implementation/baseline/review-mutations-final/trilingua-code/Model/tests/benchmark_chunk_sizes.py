"""
Phase D Tier 3b: Incremental chunk size benchmark.

Runs the golden regression suite at each chunk size and reports:
  - Pass rate (structural correctness)
  - Wall-clock time
  - LLM call count (from profiling)
  - Recommended optimal size

Usage:
    python tests/benchmark_chunk_sizes.py
"""
import os
import sys
import time
import subprocess
import re
import json

MODEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHUNK_SIZES = [400, 550, 700, 850, 1000]


def run_tests(chunk_size):
    """Run golden tests with a specific TRANSLATION_MAX_TOKENS.

    Returns dict with pass/fail counts and timing.
    """
    env = os.environ.copy()
    env["TRANSLATION_MAX_TOKENS"] = str(chunk_size)
    env["TRANSLATION_ANALYZER_MODE"] = "merged"
    env["TRANSLATION_BATCHED_REVIEW"] = "false"
    env["PYTHONIOENCODING"] = "utf-8"

    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_regression.py",
         "-v", "--tb=line", "--no-header"],
        capture_output=True, text=True, timeout=300,
        cwd=MODEL_DIR, env=env,
    )
    elapsed = time.perf_counter() - t0

    stdout = result.stdout

    passed = len(re.findall(r'\bPASSED\b', stdout))
    failed = len(re.findall(r'\bFAILED\b', stdout))
    total = passed + failed

    # Extract timing from summary
    timing_match = re.search(r'in\s+([\d.]+)\s*s', stdout)
    test_time_s = float(timing_match.group(1)) if timing_match else 0.0

    # Extract LLM call count from test output (profiling)
    llm_match = re.search(r'LLM Calls:\s+(\d+)', stdout)
    llm_calls = int(llm_match.group(1)) if llm_match else None

    return {
        "chunk_size": chunk_size,
        "passed": passed,
        "failed": failed,
        "total": total,
        "pass_rate": (passed / total * 100) if total > 0 else 0,
        "test_time_s": round(test_time_s, 2),
        "wall_time_s": round(elapsed, 2),
        "llm_calls": llm_calls,
        "returncode": result.returncode,
    }


def print_row(r):
    """Print a single result row."""
    status = "PASS" if r["failed"] == 0 else "FAIL"
    llm = f"{r['llm_calls']}" if r["llm_calls"] is not None else "N/A"
    print(f"{r['chunk_size']:>5}  {r['passed']:>3}/{r['total']:<3}  "
          f"{r['failed']:>3}  {r['pass_rate']:>6.1f}%  "
          f"{r['test_time_s']:>7.2f}s  {llm:>5}  {status:>4}")


if __name__ == "__main__":
    print("=" * 75)
    print("Phase D Tier 3b: Chunk Size Benchmark")
    print("=" * 75)
    print(f"{'Tokens':>5}  {'Passed':>7}  {'Failed':>5}  {'Rate':>7}  "
          f"{'TestTime':>8}  {'LLM':>5}  {'Status':>5}")
    print("-" * 75)

    results = []
    for size in CHUNK_SIZES:
        print(f"\n--- Chunk size: {size} tokens ---")
        r = run_tests(size)
        print_row(r)
        results.append(r)

    print("\n" + "=" * 75)
    print("Summary")
    print("=" * 75)
    print(f"{'Tokens':>5}  {'Passed':>7}  {'Failed':>5}  {'Rate':>7}  "
          f"{'TestTime':>8}  {'LLM':>5}  {'Status':>5}")
    print("-" * 75)
    for r in results:
        print_row(r)

    all_pass = [r for r in results if r["failed"] == 0]
    if all_pass:
        fastest = min(all_pass, key=lambda r: r["test_time_s"])
        print(f"\nRecommendation: {fastest['chunk_size']} tokens "
              f"(fastest at {fastest['pass_rate']:.0f}% pass rate)")
    else:
        print("\nNo chunk size achieved 100% pass rate")
