"""
TriLingua Translation Microservice v5
======================================
Modular AI Engine using provider pattern.
Supports: GPT-OSS (Ollama Cloud), Google Gemini
Document formats: .docx .pdf .txt .md .rtf .odt .csv .pptx .xlsx

Architecture:
  Laravel â†’ server.py â†’ pipeline/ â†’ providers/ â†’ AI API

Usage:
    set GEMINI_API_KEY=your_key_here     # For Gemini analysis and review
    set OLLAMA_CLOUD_URL=http://localhost:11434/api/chat  # For GPT-OSS
    python Model/server.py

The server listens on http://127.0.0.1:5000 by default.
"""

import sys
import os
import hmac
import logging
import time as _time

# Ensure the Model directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Must run before importing the pipeline: its progress logs include Unicode
# language arrows and source text.  On a legacy Windows console, an ordinary
# print would otherwise raise UnicodeEncodeError and abort the request.
from config.runtime import configure_process_output
configure_process_output()

import base64
import shutil
import tempfile
import io
import threading
import uvicorn

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Load .env file for Python
# ---------------------------------------------------------------------------
def _load_env_file():
    """Read the Laravel .env file and load relevant variables."""
    from config.environment import load_engine_environment
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")

    if not os.path.exists(env_path):
        print(f"  [INFO] No .env file found at {env_path}")
        return

    print(f"  [INFO] Loading environment from: {env_path}")
    load_engine_environment(env_path)

_load_env_file()

# ---------------------------------------------------------------------------
# Import the new modular pipeline
# ---------------------------------------------------------------------------
print("Initializing TriLingua v5 (Provider-based AI Engine)...")

from dto.requests import LANGUAGES
from dto.responses import TranslationResponse, HealthResponse
from providers.gemini import GeminiProvider
from providers.gptoss import GPTOSSProvider
from providers.nllb import NLLBProvider
from providers.fallback import FallbackTranslationProvider
from providers.future_openai import OpenAIProvider
from providers.future_deepseek import DeepSeekProvider
from ai.gemini_provider import GeminiAnalysisProvider
from ai.ollama_provider import OllamaAnalysisProvider
from ai.fallback_provider import FallbackAnalysisProvider
from pipeline.translation_pipeline import TranslationPipeline
from pipeline.document_pipeline import DocumentPipeline
from config.processing_modes import VALID_MODES, get_mode
from validators.ai_quality_reviewer import AIQualityReviewer
from validators.translation_validator import PDFValidationError

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
TRANSLATION_PROVIDER = os.environ.get("TRANSLATION_PROVIDER", "gptoss").lower()
TRANSLATION_FALLBACK_PROVIDER = os.environ.get(
    "TRANSLATION_FALLBACK_PROVIDER", "gemini"
).lower()
ANALYSIS_PROVIDER = os.environ.get("ANALYSIS_PROVIDER", "gemini").lower()
ANALYSIS_FALLBACK_PROVIDER = os.environ.get(
    "ANALYSIS_FALLBACK_PROVIDER", "ollama"
).lower()

# Initialize all available providers
_gemini_provider = GeminiProvider()
_gptoss_provider = GPTOSSProvider()
_nllb_provider = NLLBProvider()

# Analysis and quality review use a separate Gemini -> Ollama chain.
_ollama_analysis_provider = OllamaAnalysisProvider()
if ANALYSIS_PROVIDER == "gemini" and os.environ.get("GEMINI_API_KEY"):
    _gemini_analysis_provider = GeminiAnalysisProvider(
        max_attempts=max(1, int(os.environ.get("GEMINI_ANALYSIS_MAX_ATTEMPTS", "3")))
    )
    _analysis_provider = FallbackAnalysisProvider(
        _gemini_analysis_provider,
        _ollama_analysis_provider
        if ANALYSIS_FALLBACK_PROVIDER == "ollama" else None,
    )
else:
    if ANALYSIS_PROVIDER == "gemini":
        print("  WARNING: GEMINI_API_KEY is absent; using Ollama for analysis/review")
    elif ANALYSIS_PROVIDER != "ollama":
        print(f"  WARNING: Unknown analysis provider '{ANALYSIS_PROVIDER}'; using Ollama")
    _analysis_provider = _ollama_analysis_provider

# Future providers (stubs â€” raise NotImplementedError when instantiated)
# Uncomment imports above and these lines when ready to implement:
# _openai_provider = OpenAIProvider()
# _deepseek_provider = DeepSeekProvider()

# Map provider names to instances (active + future stubs)
AVAILABLE_PROVIDERS = {
    "gemini": _gemini_provider,
    "gptoss": _gptoss_provider,
    "nllb": _nllb_provider,
    # Future: uncomment when provider is implemented
    # "openai": _openai_provider,
    # "deepseek": _deepseek_provider,
}

def _get_active_provider():
    """Get the currently active provider based on environment configuration."""
    provider = AVAILABLE_PROVIDERS.get(TRANSLATION_PROVIDER)
    if provider is None:
        print(f"  WARNING: Unknown provider '{TRANSLATION_PROVIDER}', falling back to gptoss")
        return _gptoss_provider
    return provider

def _get_pipeline_provider(primary):
    """Build the configured primary -> fallback translation route."""
    fallback = AVAILABLE_PROVIDERS.get(TRANSLATION_FALLBACK_PROVIDER)
    if fallback is None:
        print(f"  WARNING: Unknown translation fallback "
              f"'{TRANSLATION_FALLBACK_PROVIDER}'; fallback disabled")
        return primary
    if fallback.name == primary.name:
        return primary
    return FallbackTranslationProvider(primary, fallback)

# Create pipelines with the active provider
_active_provider = _get_active_provider()
_pipeline_provider = _get_pipeline_provider(_active_provider)
_translation_pipeline = TranslationPipeline(_pipeline_provider)
_text_quality_reviewer = AIQualityReviewer(_analysis_provider)
_document_pipeline = DocumentPipeline(
    _translation_pipeline,
    ai_analysis_provider=_analysis_provider,
)

print(f"  [OK] Active translation provider: {_active_provider.name} ({_active_provider.model_name})")
print(f"  [OK] Analysis provider: {_analysis_provider.name} ({_analysis_provider.model_name})")
print(f"  [OK] Supported languages: {list(LANGUAGES.keys())}")
print(f"  [OK] Available providers: {list(AVAILABLE_PROVIDERS.keys())}")

# ---------------------------------------------------------------------------
# Concurrency control
# ---------------------------------------------------------------------------
# Sync `def` endpoints run on FastAPI's default threadpool. We bound that
# pool explicitly so a burst of document jobs cannot spawn unbounded worker
# threads, and we cap concurrent pipeline executions so outbound AI calls are
# serialized enough to avoid tripping provider rate limits (429s). The
# providers themselves already retry 429s with exponential backoff + jitter;
# this guard stops the pile-up from happening in the first place.
#
#   TRANSLATION_THREADPOOL_SIZE  default 8  (matches provider HTTP pool sizes)
#   TRANSLATION_MAX_CONCURRENT   default 1 for Gemini, 3 otherwise
# ---------------------------------------------------------------------------
_THREADPOOL_SIZE = max(1, int(os.environ.get("TRANSLATION_THREADPOOL_SIZE", "8")))
_DEFAULT_MAX_CONCURRENT = str(_pipeline_provider.max_concurrency or 3)
_REQUESTED_MAX_CONCURRENT = max(
    1, int(os.environ.get("TRANSLATION_MAX_CONCURRENT", _DEFAULT_MAX_CONCURRENT))
)
_MAX_CONCURRENT = min(
    _REQUESTED_MAX_CONCURRENT,
    _pipeline_provider.max_concurrency or _REQUESTED_MAX_CONCURRENT,
)
_BUSY_WAIT_SECONDS = max(
    0, int(os.environ.get("TRANSLATION_BUSY_WAIT_SECONDS", "30"))
)

_translation_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT)


class UsageHTTPException(HTTPException):
    def __init__(self, status_code, detail, provider_usage):
        super().__init__(status_code, detail)
        self.provider_usage = provider_usage


def _run_pipeline_guarded(pipeline_call):
    """Run a pipeline call under the concurrency guard.

    Wait briefly for a slot instead of rejecting ordinary text requests while
    a document is between provider calls. Outbound GPT-OSS calls have their
    own global serialization and pacing guard.
    """
    if not _translation_semaphore.acquire(timeout=_BUSY_WAIT_SECONDS):
        raise HTTPException(
            503,
            f"Server busy: translation queue is still full after waiting "
            f"{_BUSY_WAIT_SECONDS} seconds (max {_MAX_CONCURRENT} active).",
        )
    try:
        from provider_usage import usage_scope, ProviderStopped
        usage = None
        try:
            with usage_scope() as usage:
                result = pipeline_call()
                usage.check()
                summary = usage.summary()
                response = result[0] if isinstance(result, tuple) else result
                if hasattr(response, 'token_usage'):
                    response.provider_usage = summary
                    response.token_usage = {'input': summary['input_tokens'], 'output': summary['output_tokens']}
                if hasattr(response, 'metrics'):
                    response.metrics.update(provider_usage=summary, llm_calls=summary['request_count'],
                                            input_tokens=summary['input_tokens'], output_tokens=summary['output_tokens'])
                return result
        except ProviderStopped as error:
            raise UsageHTTPException(429, str(error), usage.summary() if usage else None) from error
        except Exception as error:
            error.provider_usage = usage.summary() if usage else None
            raise
    finally:
        _translation_semaphore.release()


print(f"  [OK] Concurrent translations limited to {_MAX_CONCURRENT}")

# ---------------------------------------------------------------------------
# Dependencies and SQLite cache remain lazy; startup makes no provider requests.

from contextlib import asynccontextmanager


@asynccontextmanager
async def _runtime_lifespan(app: FastAPI):
    """Bound the anyio threadpool used for sync endpoints.

    Must run at startup (not import time): the default thread limiter only
    exists once an async event loop is running, which is exactly when uvicorn
    starts serving. Without this, FastAPI would default to 40 worker threads
    and a burst of document jobs could spawn unbounded concurrent executions.
    """
    try:
        _enforce_startup_token_policy()
    except RuntimeError as exc:
        print(f"  [FATAL] {exc}")
        raise
    try:
        from anyio.to_thread import current_default_thread_limiter
        current_default_thread_limiter().total_tokens = _THREADPOOL_SIZE
        print(f"  [OK] Threadpool limited to {_THREADPOOL_SIZE} worker threads")
    except Exception as e:
        print(f"  [WARN] Could not configure threadpool limiter: {e}")
    yield


app = FastAPI(title="TriLingua Translation Service v5", lifespan=_runtime_lifespan)


@app.exception_handler(UsageHTTPException)
async def usage_error_response(request, error):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=error.status_code,
                        content={'detail': error.detail, 'provider_usage': error.provider_usage})


@app.middleware("http")
async def log_translation_request(request, call_next):
    if not request.url.path.startswith("/translate/"):
        return await call_next(request)

    logger = logging.getLogger("uvicorn.error")
    started = _time.monotonic()
    logger.info("Translation request received: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Translation request failed: %s %s", request.method, request.url.path)
        raise
    logger.info(
        "Translation response: %s %s status=%s elapsed=%.1fs",
        request.method, request.url.path, response.status_code, _time.monotonic() - started,
    )
    return response


# ---------------------------------------------------------------------------
# Service-token enforcement
# The server binds to loopback, but any local process could otherwise call it.
# The mutation/translation endpoints require the X-Service-Token header to match
# PYTHON_SERVICE_TOKEN (compared in constant time). Laravel sends this header
# automatically from translation.python_service.token, which reads the same
# variable name. The /health endpoint stays open for monitoring.
# ---------------------------------------------------------------------------
# Deployments that terminate TLS and network-isolate this service still must not
# serve it unauthenticated, so a production process refuses to start without a
# token. Local and test runs keep the opt-in behaviour they have always had.
PRODUCTION_ENV_NAMES = {"production", "prod"}


def _app_env() -> str:
    return os.environ.get("APP_ENV", "").strip().lower()


def _is_production() -> bool:
    return _app_env() in PRODUCTION_ENV_NAMES


def _model_service_token() -> str:
    """The shared secret Laravel presents as X-Service-Token.

    PYTHON_SERVICE_TOKEN is the canonical name. MODEL_SERVICE_TOKEN is read
    only as a fallback so existing local .env files keep working; it must never
    be the name used to configure a deployment.
    """
    canonical = os.environ.get("PYTHON_SERVICE_TOKEN", "").strip()
    if canonical or _is_production():
        return canonical
    return os.environ.get("MODEL_SERVICE_TOKEN", "").strip()


def _enforce_startup_token_policy() -> None:
    """Refuse to serve production traffic without a shared secret."""
    if not _is_production():
        return
    if not _model_service_token():
        raise RuntimeError(
            "PYTHON_SERVICE_TOKEN must be set to a non-empty value when "
            "APP_ENV=production. Refusing to start the translation service "
            "without service-token enforcement."
        )


async def require_service_token(
    x_service_token: str = Header(default=None),
):
    configured = _model_service_token()
    if not configured:
        # Production cannot reach this branch: startup already refused to boot.
        # Reaching it anyway means the process lost its configuration, and
        # serving unauthenticated would silently expose every endpoint.
        if _is_production():
            raise HTTPException(503, "Service token is not configured.")
        return
    if not x_service_token or not hmac.compare_digest(x_service_token, configured):
        raise HTTPException(401, "Invalid or missing service token.")

VALID_PDF_COLUMN_MODES = {"auto", "single", "left", "right"}

SUPPORTED_EXTENSIONS = {
    ".docx", ".pdf", ".txt", ".md", ".csv", ".rtf", ".odt", ".pptx", ".xlsx"
}

EXTENSION_MAP = {
    ".docx": ".docx", ".pdf": ".pdf", ".txt": ".txt",
    ".md": ".md",     ".csv": ".csv", ".rtf": ".docx",
    ".odt": ".docx",  ".pptx": ".pptx", ".xlsx": ".xlsx",
}


def _content_type_for_ext(ext: str) -> str:
    """Best-effort MIME type for a given output extension."""
    return {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf":  "application/pdf",
        ".txt":  "text/plain",
        ".md":   "text/markdown",
        ".csv":  "text/csv",
    }.get(ext or "", "application/octet-stream")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    provider = _get_active_provider()
    # Report the operational provider chain, not only Gemini's model-metadata
    # endpoint. After a translation opens the fallback circuit this exposes
    # the degraded state and cooldown while still confirming GPT-OSS health.
    provider_health = _pipeline_provider.health()
    return {
        "status": "ok",
        "engine": f"provider:{_pipeline_provider.name}",
        "model": _pipeline_provider.model_name,
        "active_provider": provider.name,
        "fallback_provider": (
            TRANSLATION_FALLBACK_PROVIDER
            if TRANSLATION_FALLBACK_PROVIDER != provider.name else None
        ),
        "available_providers": list(AVAILABLE_PROVIDERS.keys()),
        "languages": list(LANGUAGES.keys()),
        "formats": sorted(SUPPORTED_EXTENSIONS),
        "provider_status": provider_health,
        "analysis_status": _analysis_provider.health(),
    }


# ---------------------------------------------------------------------------
# Provider info endpoint
# ---------------------------------------------------------------------------
@app.get("/providers")
def list_providers():
    """List all available translation providers and their status."""
    result = {}
    for name, provider in AVAILABLE_PROVIDERS.items():
        result[name] = provider.health()
    return {
        "active_provider": _get_active_provider().name,
        "providers": result,
    }


# ---------------------------------------------------------------------------
# Text translation
# POST /translate/text
# Body: { "text": "...", "source_lang": "English", "target_lang": "Cebuano" }
# Returns: { "translated": "...", "provider": "...", ... }
# ---------------------------------------------------------------------------
class TextRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str
    mode: str = "balanced"


@app.post("/translate/text", dependencies=[Depends(require_service_token)])
def translate_text(req: TextRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "Text must not be empty.")
    if req.source_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown source language: {req.source_lang}")
    if req.target_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown target language: {req.target_lang}")
    if req.source_lang == req.target_lang:
        raise HTTPException(400, "Source and target languages must differ.")
    requested_mode = req.mode.lower().strip()
    if requested_mode not in VALID_MODES:
        raise HTTPException(400, f"Unknown processing mode: {req.mode}")
    resolved_mode = "balanced" if requested_mode == "auto" else requested_mode
    processing_mode = get_mode(resolved_mode)

    try:
        from dto.requests import TranslationRequest as TR
        source_text = req.text

        def _translate_and_review():
            request = TR(
                text=source_text,
                source_lang=req.source_lang,
                target_lang=req.target_lang,
            )
            initial = _translation_pipeline.translate(request)
            if not initial.success:
                return initial, None, []

            warnings = list(initial.warnings)
            if not processing_mode.ai_quality_review:
                return initial, None, warnings

            try:
                review = _text_quality_reviewer.review(
                    source=source_text,
                    translation=initial.translated_text,
                )
            except Exception as error:
                warnings.append(
                    f"Quality review was unavailable; returning the valid "
                    f"translation ({type(error).__name__})."
                )
                return initial, None, warnings
            if "unavailable" in review.summary.lower():
                warnings.append("Quality review was unavailable; returning the valid translation.")
                return initial, None, warnings

            if not _text_quality_reviewer.needs_retranslation(review):
                return initial, review, warnings

            from provider_usage import call_with_purpose
            repaired = call_with_purpose("repair", _translation_pipeline._translate_with_echo_guard,
                text=source_text,
                source_lang=req.source_lang,
                target_lang=req.target_lang,
                block_type="paragraph",
                context_hint=f"Previous quality issues: {review.summary}",
                document_type="",
            )
            if not repaired.success or not repaired.translated_text:
                warnings.append(
                    "Quality repair failed; retained the initial translation."
                )
                return initial, review, warnings

            try:
                final_review = _text_quality_reviewer.review(
                    source=source_text,
                    translation=repaired.translated_text,
                )
            except Exception as error:
                final_review = None
                warnings.append(
                    f"Final quality review was unavailable after repair "
                    f"({type(error).__name__})."
                )
            _translation_pipeline.store_translation(
                source_text, req.source_lang, req.target_lang,
                repaired.translated_text,
            )
            warnings.extend(repaired.warnings)
            return repaired, final_review, warnings

        result, review, warnings = _run_pipeline_guarded(_translate_and_review)

        if not result.success:
            raise UsageHTTPException(500, result.error_message, getattr(result, "provider_usage", None))

        if review is not None and not review.available:
            warnings.append("AI quality review unavailable; translation was retained without a review score.")

        return {
            "translated": result.translated_text,
            "provider": result.provider,
            "model": result.model,
            "mode": resolved_mode,
            "quality_score": round(review.score, 1) if review and review.score is not None else None,
            "quality_review_available": bool(review and review.available),
            "quality_issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "description": issue.description,
                }
                for issue in (review.issues if review else [])
            ],
            "warnings": warnings,
            "token_usage": result.token_usage,
            "provider_usage": getattr(result, "provider_usage", None),
            "execution_time_ms": result.execution_time_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger("uvicorn.error").exception("Text translation failed")
        raise UsageHTTPException(500, str(e), getattr(e, "provider_usage", None))


# ---------------------------------------------------------------------------
# Document translation
# POST /translate/document  (multipart/form-data)
# Fields: file (UploadFile), source_lang, target_lang
# Returns: the translated file as a download
#
# NOTE: These endpoints are declared as plain `def` (NOT `async def`) on
# purpose. The pipeline performs blocking file I/O and synchronous AI HTTP
# calls; running it on the event loop would freeze every other request
# (including /health) while a translation is in flight. FastAPI executes
# sync endpoints on the bounded threadpool configured above.
# ---------------------------------------------------------------------------
@app.post("/translate/document", dependencies=[Depends(require_service_token)])
def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    pdf_column_mode: str = Form("auto"),
    mode: str = Form("balanced"),
):
    if pdf_column_mode not in VALID_PDF_COLUMN_MODES:
        raise HTTPException(
            400,
            f"Invalid pdf_column_mode '{pdf_column_mode}'. "
            f"Must be one of: {sorted(VALID_PDF_COLUMN_MODES)}"
        )
    if source_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown source language: {source_lang}")
    if target_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown target language: {target_lang}")
    if source_lang == target_lang:
        raise HTTPException(400, "Source and target languages must differ.")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in EXTENSION_MAP:
        raise HTTPException(400, f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")

    out_ext = EXTENSION_MAP[ext]
    tmp_dir = tempfile.mkdtemp()
    output_path = None

    try:
        input_path = os.path.join(tmp_dir, f"input{ext}")
        output_path = os.path.join(tmp_dir, f"translated{out_ext}")

        # Save the uploaded file (sync read â€” we are on a worker thread)
        contents = file.file.read()
        with open(input_path, "wb") as f:
            f.write(contents)

        print(f"[SERVER] Translating document: {file.filename} ({source_lang} â†’ {target_lang})")
        print(f"[SERVER] Format: {ext}, Size: {len(contents)} bytes")

        # Use the new DocumentPipeline
        from dto.requests import DocumentTranslationRequest as DTR
        request = DTR(
            file_path=input_path,
            source_lang=source_lang,
            target_lang=target_lang,
            pdf_column_mode=pdf_column_mode,
            mode=mode,
        )
        result = _run_pipeline_guarded(lambda: _document_pipeline.translate(request))

        if not result.success:
            raise UsageHTTPException(500, result.error_message, getattr(result, "provider_usage", None))

        actual_output = result.output_path
        if not os.path.exists(actual_output):
            raise HTTPException(500, "Translation produced no output file.")

        original_stem = os.path.splitext(file.filename)[0]
        download_name = f"{original_stem}_translated{out_ext}"

        print(f"[SERVER] Translation complete. Output file ready at: {actual_output}")
        print(f"[SERVER] Provider: {result.provider}, Model: {result.model}")
        print(f"[SERVER] Execution time: {result.total_execution_time_ms:.0f}ms")

        # Read the file into memory and clean up immediately
        with open(actual_output, "rb") as f:
            file_contents = f.read()

        # Clean up the temporary directory
        shutil.rmtree(tmp_dir, ignore_errors=True)

        # Return the JSON envelope: base64 file bytes + per-block review data.
        # Laravel decodes file_base64 and persists `blocks` for admin review.
        return {
            "file_base64": base64.b64encode(file_contents).decode("ascii"),
            "blocks": getattr(result, "blocks", None) or [],
            "sidecar": getattr(result, "sidecar", None),
            "download_filename": download_name,
            "mime_type": _content_type_for_ext(out_ext),
            "metrics": result.metrics or {},
            "validation": getattr(result, "output_validation", {}) or {},
        }
    except PDFValidationError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(422, {"message": str(e), "validation": e.report})
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[SERVER] Exception during translation: {str(e)}")
        raise UsageHTTPException(500, f"Translation error: {str(e)}", getattr(e, "provider_usage", None))


# ---------------------------------------------------------------------------
# POST /translate/document/regenerate â€” reconstruction-only re-render of an
# edited document. Requires a sidecar captured at translate time plus the
# ORIGINAL source file (needed for PDF and in-place DOCX/PPTX/XLSX replay).
# No extraction, analysis, prepass, memory, or AI translation runs here.
# ---------------------------------------------------------------------------
@app.post("/translate/document/regenerate", dependencies=[Depends(require_service_token)])
def translate_document_regenerate(
    file: UploadFile = File(...),
    sidecar: str = Form(...),
    blocks: str = Form(""),
    overrides: str = Form("{}"),
    source_lang: str = Form(""),
    target_lang: str = Form(""),
    pdf_column_mode: str = Form("auto"),
):
    import json as _json
    tmp_dir = tempfile.mkdtemp()
    try:
        input_path = os.path.join(tmp_dir, f"original{os.path.splitext(file.filename)[1].lower()}")
        contents = file.file.read()
        with open(input_path, "wb") as f:
            f.write(contents)

        try:
            decoded = _json.loads(sidecar)
        except Exception:
            raise HTTPException(400, "Invalid 'sidecar' JSON.")

        # Allow an explicit blocks payload to override/replace the sidecar blocks.
        if blocks:
            try:
                decoded["blocks"] = _json.loads(blocks)
            except Exception:
                raise HTTPException(400, "Invalid 'blocks' JSON.")

        try:
            overrides_dict = _json.loads(overrides) or {}
        except Exception:
            raise HTTPException(400, "Invalid 'overrides' JSON.")

        fmt = (decoded.get("format") or "").lower()
        out_ext = fmt if fmt in EXTENSION_MAP.values() else ".pdf"
        output_path = os.path.join(tmp_dir, f"regenerated{out_ext}")

        from document.regenerator import reconstruct_from_sidecar
        _run_pipeline_guarded(lambda: reconstruct_from_sidecar(
            decoded,
            overrides=overrides_dict,
            original_file=input_path,
            output_file=output_path,
            source_lang=source_lang or decoded.get("source_lang", ""),
            target_lang=target_lang or decoded.get("target_lang", ""),
            pdf_column_mode=pdf_column_mode or decoded.get("pdf_column_mode", "auto"),
        ))

        if not os.path.exists(output_path):
            raise HTTPException(500, "Regeneration produced no output file.")

        with open(output_path, "rb") as f:
            file_contents = f.read()

        original_stem = os.path.splitext(file.filename)[0]
        download_name = f"{original_stem}_regenerated{out_ext}"
        shutil.rmtree(tmp_dir, ignore_errors=True)

        return StreamingResponse(
            io.BytesIO(file_contents),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={download_name}"}
        )
    except PDFValidationError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(422, {"message": str(e), "validation": e.report})
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[SERVER] Exception during regeneration: {str(e)}")
        raise HTTPException(500, f"Regeneration error: {str(e)}")


# ---------------------------------------------------------------------------
# Cache management
# DELETE /cache/clear â€” clears the persistent SQLite translation cache
# ---------------------------------------------------------------------------
@app.delete("/cache/clear", dependencies=[Depends(require_service_token)])
def clear_cache():
    """Clear all cached translations from the persistent SQLite cache.

    This endpoint clears both the in-memory document cache and the
    persistent SQLite database. After calling this, all translations
    will be re-generated on the next request.

    Returns:
        JSON with status and number of entries deleted.
    """
    try:
        from cache.sqlite_cache import SQLiteTranslationCache
        cache = SQLiteTranslationCache(
            ttl_days=int(os.environ.get("TRANSLATION_CACHE_TTL_DAYS", "30")),
            enabled=os.environ.get("TRANSLATION_CACHE_ENABLED", "true").lower() == "true",
        )
        result = cache.clear_all()
        return {
            "status": "ok",
            "message": "Translation cache cleared",
            "entries_deleted": result.get("entries_deleted", 0),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to clear cache: {str(e)}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("TRANSLATION_PORT", 5000))

    # A file watcher can terminate an in-flight document whenever a test file
    # or source file changes. Translation is a long-running service, so reload
    # is opt-in even in local development.
    _reload = os.environ.get("MODEL_SERVICE_RELOAD", "false").lower() == "true"

    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=_reload,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
    )
