# TriLingua Python Engine — Setup Guide

## Prerequisites

- **Python 3.11+** — [python.org](https://python.org)
- **Ollama** — [ollama.com](https://ollama.com) (for GPT-OSS provider or analysis)

## 1. Install Python Dependencies

```bash
cd trilingua-code
pip install fastapi uvicorn python-multipart requests pydantic
pip install python-docx PyMuPDF python-pptx openpyxl odfpy striprtf
pip install pytest hypothesis sacrebleu   # dev/testing only
```

## 2. Pull Ollama Models

**Cloud models** (require Ollama Cloud running at localhost:11434):

Will be pulled automatically on first request:
- `minimax-m3:cloud`
- `qwen3.5:397b-cloud`
- `gemma4:31b-cloud`
- `gpt-oss:20b-cloud`

**Local analysis model** (runs on CPU, ~700MB, fast):

```bash
ollama pull llama3.2:1b
```

## 3. Configure .env

The file `trilingua-code/.env` controls all provider and pipeline settings.

### Translation Provider

```
TRANSLATION_PROVIDER=mistral        # "mistral" or "gptoss"
```

| Provider | Key | Model |
|----------|-----|-------|
| Mistral | `MISTRAL_API_KEY` | `MISTRAL_MODEL=mistral-small-latest` |
| GPT-OSS (Ollama Cloud) | — | `OLLAMA_CLOUD_MODEL=gpt-oss:20b-cloud` |

**Switching providers:** Change `TRANSLATION_PROVIDER`, restart server. That's it.

### Analysis Provider

```
OLLAMA_ANALYSIS_MODEL=llama3.2:1b
```

Used for document analysis and quality review. Falls back gracefully if unavailable.

### Concurrency

```
TRANSLATION_CONCURRENCY=16
```

How many parallel API calls the pipeline sends. Auto-capped at 4 when using Mistral (to avoid rate limits). Default 16 for GPT-OSS.

| Provider | Recommended |
|----------|------------|
| Mistral | `4` (auto-capped, override not needed) |
| GPT-OSS (Ollama Cloud) | `16` (default if line is deleted) |

### All .env Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TRANSLATION_PROVIDER` | Yes | `gptoss` | `mistral` or `gptoss` |
| `MISTRAL_API_KEY` | If Mistral | — | Mistral API key |
| `MISTRAL_MODEL` | No | `mistral-small-latest` | Mistral model name |
| `OLLAMA_CLOUD_URL` | No | `http://localhost:11434/api/chat` | Ollama Cloud endpoint |
| `OLLAMA_CLOUD_MODEL` | No | `gpt-oss:20b-cloud` | Ollama Cloud model |
| `OLLAMA_ANALYSIS_MODEL` | No | `llama3.2:1b` | Analysis model (local Ollama) |
| `TRANSLATION_CONCURRENCY` | No | `16` | Parallel API call count |
| `SUPABASE_URL` | For storage | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | For storage | — | Supabase service key |

## 4. Start the Server

```bash
cd trilingua-code
python Model/server.py
```

Expected startup log:

```
[OK] Active translation provider: mistral (mistral-small-latest)
[OK] Analysis provider: ollama_analysis (llama3.2:1b)
[OK] Available providers: ['mistral', 'gptoss']
[WARMUP] Pre-warming cold-start dependencies...
  [WARMUP] [OK] python-docx
  [WARMUP] [OK] PyMuPDF (fitz)
  ...
  [WARMUP] [OK] mistral connection pool warmed
  [WARMUP] Complete in 6ms
INFO:     Started server process [12345]
INFO:     Application startup complete.
```

GPT-OSS warmup includes a model loading step (may take 1-2 min):

```
[WARMUP] Loading gpt-oss:20b-cloud (may take 1-2 min)...
[WARMUP] [OK] gpt-oss:20b-cloud loaded into memory
```

The server listens on `http://127.0.0.1:5000`.

## 5. PDF Handling

PDFs are processed via **PyMuPDF** — text is extracted from pages, translated, then overlaid onto the original PDF. Layout quality depends on font matching and overflow handling.

### PDF Glyph Complement (Cebuano/Filipino Accented Characters)

Cebuano and Filipino translations use accented Latin-1 characters (``ñ``, ``á``, ``é``, ``í``, ``ó``, ``ú``, ``ü`` and uppercase variants). Many PDFs use subsetted embedded fonts that contain **only the glyphs used in the original English text**, which typically lack these accented characters.

The pipeline now handles this via **glyph-aware font resolution**:

1. At extraction time, font programs embedded in the document are collected
2. During reconstruction, required Unicode codepoints are derived from the translated block text
3. ``FontMapper.resolve_to_pdf_name()`` checks each embedded font for glyph coverage
4. If the original subsetted font lacks the needed codepoints, the mapper falls back to a Base-14 built-in font (Helvetica / Times / Courier) that has full Latin-1 support
5. Non-Base-14 font buffers are re-embedded into the output page via ``page.insert_font()``

This applies to both the overlay-based write path (``reconstructor.py``) and the legacy redaction-based path (``document_translator_v3.py``).

### PDF Column Modes

For bilingual PDFs (text in two columns), the API/pipeline supports:
- `auto` — detect columns automatically (default)
- `single` — read top-to-bottom as one column
- `left` — only translate left column
- `right` — only translate right column

## 6. Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Cannot connect to Ollama Cloud` | Ollama not running | Start Ollama, verify at http://localhost:11434 |
| `Timeout` | GPU spin-up longer than 60s | Timeout is now 300s, wait or check Ollama status |
| `404 Client Error ... /api/chat` | Analysis model doesn't exist | Run `ollama pull <model>` or change `OLLAMA_ANALYSIS_MODEL` |
| `Rate limited, retrying...` | Too many concurrent requests | Mistral caps at 4 automatically; or lower `TRANSLATION_CONCURRENCY` |
| `Unknown provider '...'` | Wrong `TRANSLATION_PROVIDER` value | Use `mistral` or `gptoss`, NOT model name |
| `No translatable text extracted` | Scanned PDF (no text layer) | OCR required (not supported) |

### Running PDF Font Regression Tests

```bash
cd trilingua-code/Model
pytest tests/test_regression.py -v -k font_regression
```

Automatically generates test PDFs with accented text, runs a full ``write_pdf_preserved`` round-trip, and verifies all accented glyphs survive. Also validates font fallback logic when embedded fonts lack required codepoints.

## 7. Quick Reference

```bash
# Start server (Mistral)
python Model/server.py

# Or with GPT-OSS
TRANSLATION_PROVIDER=gptoss python Model/server.py

# Test analysis provider is working
ollama list          # verify local analysis model is pulled
ollama ps            # check if model is loaded in memory
```

For Laravel frontend setup, see `README.md` in the repo root.
