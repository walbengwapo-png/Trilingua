# -*- coding: utf-8 -*-
"""
Instrumentation tests for the profiling wrappers.

Verifies that:
1. DocumentContext.record_llm_call() correctly increments counters.
2. phase_profile context manager records phase times.
3. llm_call_profile context manager records call duration and count.
4. The phase/LLM attribution works correctly (LLM calls are attributed
   to the active phase).
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pipeline.document_context import DocumentContext
from pipeline.phase_profiler import phase_profile, llm_call_profile


# ===========================================================================
# DocumentContext profiling field tests
# ===========================================================================

class TestDocumentContextProfiling:

    def test_default_profiling_fields(self):
        """All profiling fields should start at zero."""
        ctx = DocumentContext()
        assert ctx.llm_calls == 0
        assert ctx.llm_total_time_ms == 0.0
        assert ctx.phase_times == {}
        assert ctx.phase_llm_calls == {}
        assert ctx._current_phase == ""

    def test_record_llm_call_increments_count(self):
        """record_llm_call should increment llm_calls."""
        ctx = DocumentContext()
        ctx.record_llm_call(100.0)
        assert ctx.llm_calls == 1
        assert ctx.llm_total_time_ms == 100.0

    def test_record_llm_call_accumulates(self):
        """Multiple LLM calls should accumulate."""
        ctx = DocumentContext()
        ctx.record_llm_call(50.0)
        ctx.record_llm_call(150.0)
        assert ctx.llm_calls == 2
        assert ctx.llm_total_time_ms == 200.0

    def test_record_llm_call_uncategorized(self):
        """LLM calls without an active phase should go to 'uncategorized'."""
        ctx = DocumentContext()
        ctx.record_llm_call(75.0)
        assert ctx.phase_llm_calls.get("uncategorized") == 1

    def test_record_llm_call_attributed_to_phase(self):
        """LLM calls should be attributed to the active phase."""
        ctx = DocumentContext()
        ctx.enter_phase("test_phase")
        ctx.record_llm_call(100.0)
        assert ctx.phase_llm_calls.get("test_phase") == 1
        assert ctx.llm_calls == 1
        assert ctx.llm_total_time_ms == 100.0


# ===========================================================================
# PhaseProfiler context manager tests
# ===========================================================================

class TestPhaseProfile:

    def test_phase_profile_records_time(self):
        """phase_profile should record elapsed time."""
        ctx = DocumentContext()
        with phase_profile("my_phase", ctx):
            time.sleep(0.01)  # 10ms
        assert "my_phase" in ctx.phase_times
        assert ctx.phase_times["my_phase"] >= 8.0  # allow margin

    def test_phase_profile_accumulates(self):
        """Multiple entries in the same phase should accumulate."""
        ctx = DocumentContext()
        with phase_profile("accum", ctx):
            time.sleep(0.005)
        with phase_profile("accum", ctx):
            time.sleep(0.005)
        assert ctx.phase_times["accum"] >= 8.0

    def test_phase_profile_sets_current_phase(self):
        """The phase name should be set as _current_phase during execution."""
        ctx = DocumentContext()
        with phase_profile("active_phase", ctx):
            assert ctx._current_phase == "active_phase"
        # Phase should be cleared after exit
        assert ctx._current_phase == "active_phase"


# ===========================================================================
# LLM call profiling context manager tests
# ===========================================================================

class TestLlmCallProfile:

    def test_llm_call_profile_records_call(self):
        """llm_call_profile should increment llm_calls."""
        ctx = DocumentContext()
        with llm_call_profile(ctx):
            time.sleep(0.005)
        assert ctx.llm_calls == 1
        assert ctx.llm_total_time_ms >= 3.0

    def test_llm_call_profile_attributed_to_phase(self):
        """LLM calls inside a phase_profile should be attributed."""
        ctx = DocumentContext()
        with phase_profile("my_phase", ctx):
            with llm_call_profile(ctx):
                time.sleep(0.005)
        assert ctx.phase_llm_calls.get("my_phase") == 1
        assert ctx.llm_calls == 1


# ===========================================================================
# Thread safety tests
# ===========================================================================

class TestThreadSafety:

    def test_concurrent_llm_calls(self):
        """Multiple threads recording LLM calls should not corrupt counters."""
        import threading

        ctx = DocumentContext()
        ctx.enter_phase("concurrent")

        n_calls = 50
        barrier = threading.Barrier(n_calls)
        results = []

        def worker():
            barrier.wait()
            for _ in range(10):
                ctx.record_llm_call(1.0)
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(n_calls)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert ctx.llm_calls == n_calls * 10
        assert ctx.llm_total_time_ms == n_calls * 10
        assert ctx.phase_llm_calls.get("concurrent") == n_calls * 10
