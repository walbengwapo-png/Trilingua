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

import shutil
import tempfile
import io
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
    provider = AVAILABLE_PROVIDERS.get(TRANSLATION_PROVIDER)
    if provider is None:
        print(f"  WARNING: Unknown provider '{TRANSLATION_PROVIDER}', falling back to gptoss")
        return _gptoss_provider
    return provider

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
    if _gptoss_provider.name == provider.name:
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

app = FastAPI(title="TriLingua Translation Service v5")

VALID_PDF_COLUMN_MODES = {"auto", "single", "left", "right"}

SUPPORTED_EXTENSIONS = {
    ".docx", ".pdf", ".txt", ".md", ".csv", ".rtf", ".odt", ".pptx", ".xlsx"
}

EXTENSION_MAP = {
    ".docx": ".docx", ".pdf": ".pdf", ".txt": ".txt",
    ".md": ".md",     ".csv": ".csv", ".rtf": ".docx",
    ".odt": ".docx",  ".pptx": ".pptx", ".xlsx": ".xlsx",
}


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

    try:
        from dto.requests import TranslationRequest as TR
        request = TR(
            text=req.text.strip(),
            source_lang=req.source_lang,
            target_lang=req.target_lang,
        )
        result = _translation_pipeline.translate(request)

        if not result.success:
            raise HTTPException(500, result.error_message)

        return {
            "translated": result.translated_text,
            "provider": result.provider,
            "model": result.model,
            "token_usage": result.token_usage,
            "execution_time_ms": result.execution_time_ms,
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
# ---------------------------------------------------------------------------
@app.post("/translate/document")
async def translate_document(
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

        # Save the uploaded file
        contents = await file.read()
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
        result = _document_pipeline.translate(request)

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

        # Return the file
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
        print(f"[SERVER] Exception during translation: {str(e)}")
        raise HTTPException(500, f"Translation error: {str(e)}")


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