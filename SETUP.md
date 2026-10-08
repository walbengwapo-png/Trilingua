# TriLingua Python Engine — Setup Guide

## Prerequisites

- **Python 3.11+** — [python.org](https://python.org)
- **Ollama** — [ollama.com](https://ollama.com) (for GPT-OSS provider or local analysis fallback)
- **Tesseract OCR** — [github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract) (optional, only for scanned/image-based PDFs)

## 1. Install Python Dependencies

```bash
cd trilingua-code
pip install fastapi uvicorn python-multipart requests pydantic
pip install python-docx PyMuPDF python-pptx openpyxl odfpy striprtf
pip install pytesseract Pillow   # optional: OCR fallback for scanned PDFs
pip install pytest hypothesis sacrebleu   # dev/testing only
```

## 2. Pull Ollama Models

**Cloud models** (require Ollama Cloud running at localhost:11434):

Will be pulled automatically on first request:
- `minimax-m3:cloud`
- `qwen3.5:397b-cloud`
- `gemma4:31b-cloud`
- `gpt-oss:20b-cloud`

**Local analysis model** (only needed as the analysis fallback when no Gemini API key is set):

```bash
ollama pull llama3.2:1b
```

Set `OLLAMA_ANALYSIS_MODEL` in `.env` to whatever model you pull (code default is `llama3.1:8b`).

## 3. Configure .env

The file `trilingua-code/.env` controls all provider and pipeline settings.

### Translation Provider

```
TRANSLATION_PROVIDER=gemini        # "gemini" or "gptoss"
```

| Provider | Key | Model |
|----------|-----|-------|
| Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL=gemini-2.5-flash` |
| GPT-OSS (Ollama Cloud) | — | `OLLAMA_CLOUD_MODEL=gpt-oss:20b-cloud` |

**Switching providers:** Change `TRANSLATION_PROVIDER`, restart server. That's it.

### Analysis Provider

Analysis (document analysis, quality review, layout planning) uses a separate provider from translation:

```
GEMINI_ANALYSIS_MODEL=gemini-2.5-flash
```

- **Gemini (default when `GEMINI_API_KEY` is set)** — the server picks `GeminiAnalysisProvider` whenever a Gemini API key is present. Uses the same key as the translation provider, model controlled by `GEMINI_ANALYSIS_MODEL`.
- **Ollama (fallback)** — if no `GEMINI_API_KEY` is set, the server falls back to the local `OllamaAnalysisProvider` using `OLLAMA_ANALYSIS_MODEL`.

Falls back gracefully if unavailable.

### Concurrency

```
TRANSLATION_CONCURRENCY=16
```

How many parallel API calls the pipeline sends. Auto-capped at 4 when using Gemini (to avoid rate limits). Default 16 for GPT-OSS.

| Provider | Recommended |
|----------|------------|
| Gemini | `4` (auto-capped, override not needed) |
| GPT-OSS (Ollama Cloud) | `16` (default if line is deleted) |

### All .env Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TRANSLATION_PROVIDER` | Yes | `gemini` | `gemini` or `gptoss` |
| `GEMINI_API_KEY` | If Gemini | — | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model name (translation) |
| `OLLAMA_CLOUD_URL` | No | `http://localhost:11434/api/chat` | Ollama Cloud endpoint |
| `OLLAMA_CLOUD_MODEL` | No | `gpt-oss:20b-cloud` | Ollama Cloud model |
| `GEMINI_ANALYSIS_MODEL` | No | `gemini-2.5-flash` | Analysis model (Gemini cloud) |
| `OLLAMA_ANALYSIS_MODEL` | No | `llama3.1:8b` | Analysis model (local Ollama fallback) |
| `TRANSLATION_CONCURRENCY` | No | `8` | Maximum per-document GPT-OSS batch submissions; shared slots are scheduled fairly |
| `GPTOSS_TRANSLATION_SLOTS` | No | `8` | Shared GPT-OSS document-batch capacity across all active documents |
| `TRANSLATION_MAX_CONCURRENT` | No | `2` | Active document pipelines accepted by the Python service |
| `DOCUMENT_QUEUE_WORKERS` | No | `2` | Laravel queue workers launched for document jobs |
| `GEMINI_FALLBACK_CONCURRENCY` | No | `1` | Serialized Gemini translation-fallback capacity |
| `GPTOSS_MAX_OUTPUT_TOKENS` | No | `0` | Use Ollama's normal output budget; empty GPT-OSS replies retry at 8192 then 16384 |
| `TRANSLATION_CACHE_ENABLED` | No | `true` | Enable the persistent SQLite cache |
| `TRANSLATION_CACHE_TTL_DAYS` | No | `30` | SQLite cache entry lifetime |
| `TRANSLATION_PORT` | No | `5000` | Port the FastAPI server listens on |
| `TRI_SHRINK_FLOOR` | No | `0.70` | PDF shrink-to-fit floor (× base font size) |
| `SUPABASE_URL` | For storage | — | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | For storage | — | Supabase service key |

## 4. Start the Server

```bash
cd trilingua-code
python Model/server.py
```

Expected startup log (with `GEMINI_API_KEY` set, analysis uses Gemini):

```
[OK] Active translation provider: gemini (gemini-2.5-flash)
[OK] Analysis provider: gemini_analysis (gemini-2.5-flash)
[OK] Available providers: ['gemini', 'gptoss']
[WARMUP] Pre-warming cold-start dependencies...
  [WARMUP] [OK] python-docx
  [WARMUP] [OK] PyMuPDF (fitz)
  ...
  [WARMUP] [OK] gemini connection pool warmed
  [WARMUP] Complete in 6ms
INFO:     Started server process [12345]
INFO:     Application startup complete.
```

Without a `GEMINI_API_KEY`, the analysis provider falls back to local Ollama (`ollama_analysis`).

GPT-OSS warmup includes a model loading step (may take 1-2 min):

```
[WARMUP] Loading gpt-oss:20b-cloud (may take 1-2 min)...
[WARMUP] [OK] gpt-oss:20b-cloud loaded into memory
```

The server listens on `http://127.0.0.1:5000`.

## 5. PDF Handling

PDFs are processed via **PyMuPDF** — text is extracted per line (with per-span font/size/color/run metadata), translated, then written back with a **per-line redact-and-reinsert** strategy that preserves images, vector graphics, links, and as much original formatting as possible.

### PDF Reconstruction Strategy (write path)

`write_pdf_preserved()` in ``reconstructor.py`` replaces original text line-by-line:

1. **Per-line extraction** — ``read_pdf()`` in ``extractor.py`` records each source line's bbox, baseline, x0, alignment, hyperlinks, and per-span runs (font family, size, color, bold/italic).
2. **Per-line redaction** — original lines are covered with background-sampled redaction rects via ``apply_redactions(images=0, graphics=0, text=0)`` so images and vector graphics survive untouched.
3. **Re-insertion** — translated text is re-flowed into the original line boxes at their exact baseline/x0 with per-line font/size/colour and block alignment.
4. **Run-level formatting** — lines that mixed bold/italic/size in the source reproduce that split in the output: whole translated words are assigned to the source run whose style they keep (unchanged tokens like numbers/proper nouns are matched verbatim to preserve style bit-for-bit). No mid-word style splits are introduced.
5. **Overflow rules** — text is never merged into the next block. Excess words first expand into collision-checked whitespace, then shrink down to a 70% font-size floor, then wrap to continuation lines inside the block's own box.
6. **Hyperlink recreation** — link annotations are re-created at the translated line positions; any source links lost to redaction are restored afterward.
7. **Page-copy fallback** — if a post-redaction invariant fails (I1 image bytes changed, I2 leftover original glyphs, I3 bbox collision, I4 exception), the page is rebuilt from a pristine copy and processed again.

### PDF Glyph Complement (Cebuano/Filipino Accented Characters)

Cebuano and Filipino translations use accented Latin-1 characters (``ñ``, ``á``, ``é``, ``í``, ``ó``, ``ú``, ``ü`` and uppercase variants). Many PDFs use subsetted embedded fonts that contain **only the glyphs used in the original English text**, which typically lack these accented characters.

Font resolution during reconstruction guarantees glyph coverage in this order:

1. Required Unicode codepoints are derived from the translated line text
2. A matching **system TrueType font** is used first when one is available — Tahoma, Verdana, Calibri, Segoe UI, Georgia, Cambria, etc. are mapped from `C:\Windows\Fonts` (bold/italic variants included) and embedded via ``page.insert_font()``
3. Otherwise a **Base-14 built-in variant** (Helvetica / Times / Courier, bold/italic variants) with full Latin-1 support is used
4. CID/Type0 subset fonts are **never** re-embedded — PyMuPDF's ``insert_text`` corrupts spaces/letters with them, so the mapper prefers clean Base-14/system paths instead

`FontMapper` in ``layout.py`` still handles the embedded-font resolution used elsewhere, but the PDF write path now prefers system fonts for guaranteed accented coverage.

### OCR Fallback (Scanned / Image-Based PDFs)

If PyMuPDF extracts **no text** from a PDF, the pipeline automatically retries with OCR via ``document/ocr_extractor.py``. Each page is rendered at 300 DPI and run through **Tesseract** (low-confidence results dropped), producing blocks compatible with the normal pipeline.

Requires `pip install pytesseract Pillow` plus the Tesseract OCR binary on `PATH`. If the OCR path isn't available the request fails with a clear message telling you to install it.

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
| `Rate limited, retrying...` | Too many concurrent requests | Gemini caps at 4 automatically; or lower `TRANSLATION_CONCURRENCY` |
| `Unknown provider '...'` | Wrong `TRANSLATION_PROVIDER` value | Use `gemini` or `gptoss`, NOT model name |
| `OCR fallback is not available (pytesseract not installed)` | Scanned PDF with no text layer, no OCR deps | `pip install pytesseract Pillow` + install Tesseract OCR |
| `No translatable text extracted` | Scanned PDF AND OCR yielded no text | OCR deps missing, or truly image-only page; try `pdf_column_mode='left'/'right'` for bilingual |

### Running PDF Font Regression Tests

```bash
cd trilingua-code/Model
pytest tests/test_regression.py -v -k font_regression
```

Runs full ``write_pdf_preserved`` round-trips against generated accented PDFs plus a real mixed-run document (``tests/testPDFs/M1_Q1_ENGLISH 8.pdf``). Verifies:

- Accented glyphs survive and font fallback triggers when embedded fonts lack codepoints
- Original font is kept when no accented characters are needed
- Overflow words are rescued into free continuation rows (and stop at occupied rows)
- Mixed bold/italic/size runs are preserved with no mid-word style splits

## 7. Quick Reference

```bash
# Start server (Gemini)
python Model/server.py

# Or with GPT-OSS
TRANSLATION_PROVIDER=gptoss python Model/server.py

# Test analysis provider is working
# (Gemini if GEMINI_API_KEY is set, else local Ollama)
curl http://127.0.0.1:5000/health        # shows active provider + model
ollama list                               # verify local analysis model is pulled
ollama ps                                 # check if model is loaded in memory
```

For Laravel frontend setup, see `README.md` in the repo root.
