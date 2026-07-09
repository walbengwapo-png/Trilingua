"""
TriLingua Translation Microservice v4
======================================
Uses Mistral AI API for translation (no local model needed).
Supports: .docx .pdf .txt .md .rtf .odt .csv .pptx .xlsx

Usage:
    set MISTRAL_API_KEY=your_key_here
    python Model/server.py

The server listens on http://127.0.0.1:5000 by default.
Keep it running while the Laravel app is running.
"""

import sys
import os

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
# Load .env file for Python (Laravel's .env is NOT automatically read by Python)
# ---------------------------------------------------------------------------
def _load_env_file():
    """
    Read the Laravel .env file from the project root and load MISTRAL_API_KEY
    and MISTRAL_MODEL into os.environ so Python can see them.
    
    The .env file is located one directory above Model/ (i.e. trilingua-code/.env).
    """
    # Get the directory containing this script (Model/)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # The project root is one level up from Model/
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")
    
    if not os.path.exists(env_path):
        print(f"  [INFO] No .env file found at {env_path}")
        return
    
    print(f"  [INFO] Loading environment from: {env_path}")
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE pairs
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Only load Mistral-related variables (don't pollute with all Laravel vars)
                if key in ("MISTRAL_API_KEY", "MISTRAL_MODEL"):
                    if value and not os.environ.get(key):
                        os.environ[key] = value
                        print(f"  [INFO] Loaded {key} from .env file")

# Load .env before anything else
_load_env_file()

# ---------------------------------------------------------------------------
# Import the translation pipeline
# ---------------------------------------------------------------------------
print("Initializing TriLingua v4 (Mistral AI)...")

# Check for Mistral API key
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
if not MISTRAL_API_KEY:
    print("  WARNING: MISTRAL_API_KEY environment variable is not set.")
    print("   Translation will fail until you set it.")
    print("   Set it in your .env file or with: set MISTRAL_API_KEY=your_key_here")
else:
    print(f"  [OK] Mistral AI API key found (model: {os.environ.get('MISTRAL_MODEL', 'mistral-small-latest')})")

from document_translator_v3 import run_pipeline, _translate_single, LANGUAGES
print("Server ready.")

app = FastAPI(title="TriLingua Translation Service v4")

VALID_PDF_COLUMN_MODES = {"auto", "single", "left", "right"}

# Supported file extensions
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
    return {
        "status": "ok",
        "engine": "mistral-ai",
        "model": os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
        "languages": list(LANGUAGES.keys()),
        "formats": sorted(SUPPORTED_EXTENSIONS),
    }


# ---------------------------------------------------------------------------
# Text translation
# POST /translate/text
# Body: { "text": "...", "source_lang": "English", "target_lang": "Cebuano" }
# Returns: { "translated": "..." }
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
        src_code = LANGUAGES[req.source_lang]
        tgt_code = LANGUAGES[req.target_lang]
        result = _translate_single(req.text.strip(), src_code, tgt_code)
        return {"translated": result}
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

        run_pipeline(input_path, source_lang, target_lang, output_path,
                     pdf_column_mode=pdf_column_mode)

        if not os.path.exists(output_path):
            raise HTTPException(500, "Translation produced no output file.")

        original_stem = os.path.splitext(file.filename)[0]
        download_name = f"{original_stem}_translated{out_ext}"

        print(f"[SERVER] Translation complete. Output file ready at: {output_path}")

        # Read the file into memory and clean up immediately
        with open(output_path, "rb") as f:
            file_contents = f.read()

        # Clean up the temporary directory before returning
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
    # Use hot-reload so code changes to document_translator_v3.py
    # are picked up WITHOUT needing to restart the server manually.
    # To disable hot-reload: change reload=True to reload=False
    uvicorn.run(
        "server:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=True,
        reload_dirs=[os.path.dirname(os.path.abspath(__file__))],
    )
