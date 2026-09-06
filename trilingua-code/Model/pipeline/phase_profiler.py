import time as _time_module
from contextlib import contextmanager
from typing import Generator

from .document_context import DocumentContext


@contextmanager
def phase_profile(name: str, ctx: DocumentContext) -> Generator[None, None, None]:
    """Context manager that profiles a pipeline phase.

    Records wall-clock time and sets the current phase name on *ctx*
    so that any LLM calls made inside the phase are attributed to it.

    Usage:
        with phase_profile("document_analyzer", ctx):
            profile = analyzer.analyze(blocks)
    """
    ctx.enter_phase(name)
    start = _time_module.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (_time_module.perf_counter() - start) * 1000
        ctx.phase_times[name] = ctx.phase_times.get(name, 0) + elapsed_ms


@contextmanager
def llm_call_profile(ctx: DocumentContext) -> Generator[None, None, None]:
    """Context manager that profiles a single LLM API call.

    Records the call duration and increments the LLM call counter on *ctx*.

    Usage:
        with llm_call_profile(ctx):
            response = provider.translate(...)
    """
    start = _time_module.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (_time_module.perf_counter() - start) * 1000
        ctx.record_llm_call(elapsed_ms)
