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

# Ensure the Model directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shutil
import tempfile
import io
import uvicorn

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

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
from pipeline.translation_pipeline import TranslationPipeline
from pipeline.document_pipeline import DocumentPipeline

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------
TRANSLATION_PROVIDER = os.environ.get("TRANSLATION_PROVIDER", "gptoss").lower()

# Initialize all available providers
_mistral_provider = MistralProvider()
_gptoss_provider = GPTOSSProvider()

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
_document_pipeline = DocumentPipeline(_translation_pipeline)

print(f"  [OK] Active provider: {_active_provider.name} ({_active_provider.model_name})")
print(f"  [OK] Supported languages: {list(LANGUAGES.keys())}")
print(f"  [OK] Available providers: {list(AVAILABLE_PROVIDERS.keys())}")

app = FastAPI(title="TriLingua Translation Service v5")

MAX_REQUEST_BYTES = 100 * 1024 * 1024  # 100 MB

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            raise HTTPException(413, "Request body too large. Maximum size is 100 MB.")
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware)

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
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("TRANSLATION_PORT", 5000))
    is_production = os.environ.get("APP_ENV") == "production"
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=not is_production,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))] if not is_production else [],
    )