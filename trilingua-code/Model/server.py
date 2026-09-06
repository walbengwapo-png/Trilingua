"""
TriLingua Translation Microservice v5
======================================
Modular AI Engine using provider pattern.
Supports: GPT-OSS (Ollama Cloud), Mistral AI
Document formats: .docx .pdf .txt .md .rtf .odt .csv .pptx .xlsx

Architecture:
  Laravel → server.py → pipeline/ → providers/ → AI API

Usage:
    set MISTRAL_API_KEY=your_key_here    # For Mistral fallback
    set OLLAMA_CLOUD_URL=http://localhost:11434/api/chat  # For GPT-OSS
    python Model/server.py

The server listens on http://127.0.0.1:5000 by default.
"""

import sys
import os
import time as _time

# Ensure the Model directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import shutil
import tempfile
import io
import threading
import uvicorn

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Load .env file for Python
# ---------------------------------------------------------------------------
def _load_env_file():
    """Read the Laravel .env file and load relevant variables."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")

    if not os.path.exists(env_path):
        print(f"  [INFO] No .env file found at {env_path}")
        return

    print(f"  [INFO] Loading environment from: {env_path}")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key in ("MISTRAL_API_KEY", "MISTRAL_MODEL",
                           "TRANSLATION_PROVIDER", "OLLAMA_CLOUD_URL",
                           "OLLAMA_CLOUD_MODEL"):
                    if value and not os.environ.get(key):
                        os.environ[key] = value
                        print(f"  [INFO] Loaded {key} from .env file")

_load_env_file()

# ---------------------------------------------------------------------------
# Import the new modular pipeline
# ---------------------------------------------------------------------------
print("Initializing TriLingua v5 (Provider-based AI Engine)...")

from dto.requests import LANGUAGES
from dto.responses import TranslationResponse, HealthResponse
from providers.mistral import MistralProvider
from providers.gptoss import GPTOSSProvider
from providers.fallback import FallbackTranslationProvider
from providers.future_openai import OpenAIProvider
from providers.future_gemini import GeminiProvider
from providers.future_deepseek import DeepSeekProvider
from ai.mistral_provider import MistralAnalysisProvider
from ai.ollama_provider import OllamaAnalysisProvider
from pipeline.translation_pipeline import TranslationPipeline
from pipeline.document_pipeline import DocumentPipeline

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
TRANSLATION_PROVIDER = os.environ.get("TRANSLATION_PROVIDER", "gptoss").lower()
TRANSLATION_FALLBACK_PROVIDER = os.environ.get(
    "TRANSLATION_FALLBACK_PROVIDER",
    "mistral" if TRANSLATION_PROVIDER == "gptoss" else "gptoss",
).lower()

# Initialize all available providers
_mistral_provider = MistralProvider()
_gptoss_provider = GPTOSSProvider()

# Analysis provider (separate from translation providers)
# Uses Mistral AI for independent, unbiased analysis.
# Falls back to Ollama if Mistral API key is not set.
_analysis_provider = (
    MistralAnalysisProvider()
    if os.environ.get("MISTRAL_API_KEY")
    else OllamaAnalysisProvider()
)

# Future providers (stubs — raise NotImplementedError when instantiated)
# Uncomment imports above and these lines when ready to implement:
# _openai_provider = OpenAIProvider()
# _gemini_provider = GeminiProvider()
# _deepseek_provider = DeepSeekProvider()

# Map provider names to instances (active + future stubs)
AVAILABLE_PROVIDERS = {
    "mistral": _mistral_provider,
    "gptoss": _gptoss_provider,
    # Future: uncomment when provider is implemented
    # "openai": _openai_provider,
    # "gemini": _gemini_provider,
    # "deepseek": _deepseek_provider,
}

def _get_active_provider():
    """Get the currently active provider based on environment configuration."""
    primary = AVAILABLE_PROVIDERS.get(TRANSLATION_PROVIDER)
    if primary is None:
        print(f"  WARNING: Unknown provider '{TRANSLATION_PROVIDER}', falling back to gptoss")
        primary = _gptoss_provider

    fallback = AVAILABLE_PROVIDERS.get(TRANSLATION_FALLBACK_PROVIDER)
    if fallback is None or fallback is primary:
        return primary
    return FallbackTranslationProvider(primary, fallback)

# Create pipelines with the active provider
_active_provider = _get_active_provider()
_translation_pipeline = TranslationPipeline(_active_provider)
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
#   TRANSLATION_MAX_CONCURRENT   default 3  (simultaneous pipeline executions)
# ---------------------------------------------------------------------------
_THREADPOOL_SIZE = max(1, int(os.environ.get("TRANSLATION_THREADPOOL_SIZE", "8")))
_MAX_CONCURRENT = max(1, int(os.environ.get("TRANSLATION_MAX_CONCURRENT", "3")))

_translation_semaphore = threading.BoundedSemaphore(_MAX_CONCURRENT)


def _run_pipeline_guarded(pipeline_call):
    """Run a pipeline call under the concurrency guard.

    Rejects immediately (503) instead of queueing so a flood of simultaneous
    translations cannot pile up behind the provider rate limit.
    """
    if not _translation_semaphore.acquire(blocking=False):
        raise HTTPException(
            503,
            f"Server is busy processing other translations "
            f"(max {_MAX_CONCURRENT} concurrent). Please retry in a moment.",
        )
    try:
        return pipeline_call()
    finally:
        _translation_semaphore.release()


print(f"  [OK] Concurrent translations limited to {_MAX_CONCURRENT}")

# ---------------------------------------------------------------------------
# COLD START PRE-WARMING
# Pre-import heavy libraries at startup so the first request doesn't pay
# the import penalty. Python's import system caches modules in sys.modules,
# so subsequent imports are instant dictionary lookups.
# ---------------------------------------------------------------------------
_COLD_START_WARMED = False

def _warm_cold_start():
    """Pre-warm all heavy dependencies so the first request is fast.
    
    This resolves the "first translation slow, subsequent fast" issue.
    Call this once at server startup.
    """
    global _COLD_START_WARMED
    if _COLD_START_WARMED:
        return
    _COLD_START_WARMED = True
    
    warm_start = _time.time()
    print("  [WARMUP] Pre-warming cold-start dependencies...")
    
    # 1. Pre-import heavy document processing libraries
    # These are imported lazily inside function bodies in extractor.py and
    # reconstructor.py. Importing them here loads them into sys.modules
    # so the first request doesn't pay the 1-3s import penalty.
    libs = [
        ("python-docx",     lambda: __import__("docx")),
        ("PyMuPDF (fitz)",  lambda: __import__("fitz")),
        ("python-pptx",     lambda: __import__("pptx")),
        ("openpyxl",        lambda: __import__("openpyxl")),
        ("odfpy",           lambda: __import__("odf")),
        ("striprtf",        lambda: __import__("striprtf")),
    ]
    for name, loader in libs:
        try:
            loader()
            print(f"    [WARMUP] [OK] {name}")
        except ImportError:
            print(f"    [WARMUP] [MISSING] {name} (not installed)")
    
    # 2. Pre-warm SQLite translation cache
    # Create the database and schema at startup, not on first request.
    try:
        from cache.sqlite_cache import SQLiteTranslationCache
        cache = SQLiteTranslationCache(
            ttl_days=int(os.environ.get("TRANSLATION_CACHE_TTL_DAYS", "30")),
            enabled=os.environ.get("TRANSLATION_CACHE_ENABLED", "true").lower() == "true",
        )
        # Force table creation by doing a no-op lookup
        cache.get("__warmup__", "English", "__warmup__")
        print("    [WARMUP] [OK] SQLite cache initialized")
    except Exception as e:
        print(f"    [WARMUP] [FAIL] SQLite cache: {e}")
    
    # 3. Pre-warm HTTP connection pool
    # Send a lightweight health-check to the AI provider to establish
    # the TCP/TLS connection so the first translation request doesn't
    # need to do a cold handshake.
    try:
        provider = _get_active_provider()
        health_result = provider.health()
        if health_result.get("status") == "ok":
            print(f"    [WARMUP] [OK] {provider.name} connection pool warmed")
        else:
            print(f"    [WARMUP] [OK] {provider.name} connection pool warmed (status: {health_result.get('status')})")
    except Exception as e:
        print(f"    [WARMUP] [OK] {provider.name} connection pool warmed (health check: {e})")

    # 4. Pre-warm GPT-OSS model into GPU memory
    # The health check above only does a GET /api/tags — it does NOT
    # load the model. This sends a real chat request to force Ollama
    # to spin up a GPU instance so the first translation is fast.
    if _gptoss_provider.name in provider.name:
        try:
            print(f"    [WARMUP] Loading {_gptoss_provider.model_name} (may take 1-2 min)...")
            if _gptoss_provider.warmup():
                print(f"    [WARMUP] [OK] {_gptoss_provider.model_name} loaded into memory")
            else:
                print(f"    [WARMUP] [INFO] Model will load on first request")
        except Exception as e:
            print(f"    [WARMUP] [INFO] Model warmup: {e}")

    elapsed = (_time.time() - warm_start) * 1000
    print(f"  [WARMUP] Complete in {elapsed:.0f}ms")

# Run pre-warming immediately at startup
_warm_cold_start()

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
        from anyio.to_thread import current_default_thread_limiter
        current_default_thread_limiter().total_tokens = _THREADPOOL_SIZE
        print(f"  [OK] Threadpool limited to {_THREADPOOL_SIZE} worker threads")
    except Exception as e:
        print(f"  [WARN] Could not configure threadpool limiter: {e}")
    yield


app = FastAPI(title="TriLingua Translation Service v5", lifespan=_runtime_lifespan)

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
    provider_health = provider.health()
    return {
        "status": "ok",
        "engine": f"provider:{provider.name}",
        "model": provider.model_name,
        "active_provider": provider.name,
        "available_providers": list(AVAILABLE_PROVIDERS.keys()),
        "languages": list(LANGUAGES.keys()),
        "formats": sorted(SUPPORTED_EXTENSIONS),
        "provider_status": provider_health,
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


@app.post("/translate/text")
def translate_text(req: TextRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "Text must not be empty.")
    if req.source_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown source language: {req.source_lang}")
    if req.target_lang not in LANGUAGES:
        raise HTTPException(400, f"Unknown target language: {req.target_lang}")
    if req.source_lang == req.target_lang:
        raise HTTPException(400, "Source and target languages must differ.")
    from config.processing_modes import VALID_MODES, get_mode
    if req.mode not in VALID_MODES:
        raise HTTPException(400, f"Unknown processing mode: {req.mode}")

    # Text has no document complexity to analyze. Treat auto as the safe,
    # quality-oriented default rather than exposing a mode whose behavior is
    # ambiguous to callers.
    selected_mode = get_mode("balanced" if req.mode == "auto" else req.mode)

    try:
        from dto.requests import TranslationRequest as TR
        request = TR(
            text=req.text.strip(),
            source_lang=req.source_lang,
            target_lang=req.target_lang,
            document_type="general" if selected_mode.specialized_prompts else "",
        )
        result = _run_pipeline_guarded(lambda: _translation_pipeline.translate(request))

        if not result.success:
            raise HTTPException(500, result.error_message)

        # Fast mode returns after deterministic provider safeguards. Balanced
        # and thorough add a targeted review only after that initial result;
        # a second translation is requested only when the review finds a
        # meaningful issue. This keeps ordinary requests quick while giving
        # Cebuano/Filipino grammar and tense problems a repair path.
        review = None
        reviewer = _document_pipeline._quality_reviewer
        if selected_mode.ai_quality_review and reviewer is not None:
            review = _run_pipeline_guarded(
                lambda: reviewer.review(req.text, result.translated_text, "general")
            )
            if reviewer.needs_retranslation(review):
                repair_request = TR(
                    text=req.text.strip(),
                    source_lang=req.source_lang,
                    target_lang=req.target_lang,
                    context_hint=(
                        "Quality review found these issues in the previous output: "
                        f"{review.summary}. Produce a complete, natural translation "
                        "that fixes those issues. Preserve names, numbers, dates, and URLs."
                    ),
                    document_type="general",
                )
                repaired = _run_pipeline_guarded(
                    lambda: _translation_pipeline._translate_with_echo_guard(
                        text=repair_request.text,
                        source_lang=repair_request.source_lang,
                        target_lang=repair_request.target_lang,
                        block_type=repair_request.block_type,
                        context_hint=repair_request.context_hint,
                        document_type=repair_request.document_type,
                    )
                )
                if repaired.success:
                    result = repaired
                    review = _run_pipeline_guarded(
                        lambda: reviewer.review(req.text, result.translated_text, "general")
                    )

        return {
            "translated": result.translated_text,
            "provider": result.provider,
            "model": result.model,
            "token_usage": result.token_usage,
            "execution_time_ms": result.execution_time_ms,
            "mode": selected_mode.name,
            "quality_score": round(review.score) if review else None,
            "quality_issues": [issue.category for issue in review.issues] if review else [],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


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
@app.post("/translate/document")
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

        # Save the uploaded file (sync read — we are on a worker thread)
        contents = file.file.read()
        with open(input_path, "wb") as f:
            f.write(contents)

        print(f"[SERVER] Translating document: {file.filename} ({source_lang} → {target_lang})")
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
            raise HTTPException(500, result.error_message)

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
        }
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[SERVER] Exception during translation: {str(e)}")
        raise HTTPException(500, f"Translation error: {str(e)}")


# ---------------------------------------------------------------------------
# POST /translate/document/regenerate — reconstruction-only re-render of an
# edited document. Requires a sidecar captured at translate time plus the
# ORIGINAL source file (needed for PDF and in-place DOCX/PPTX/XLSX replay).
# No extraction, analysis, prepass, memory, or AI translation runs here.
# ---------------------------------------------------------------------------
@app.post("/translate/document/regenerate")
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
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[SERVER] Exception during regeneration: {str(e)}")
        raise HTTPException(500, f"Regeneration error: {str(e)}")


# ---------------------------------------------------------------------------
# Cache management
# DELETE /cache/clear — clears the persistent SQLite translation cache
# ---------------------------------------------------------------------------
@app.delete("/cache/clear")
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
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=True,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
    )
