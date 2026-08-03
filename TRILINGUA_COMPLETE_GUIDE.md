# Trilingua — Complete Guide

## What Is Trilingua?

Trilingua is a **3-way document translation system** for **Cebuano, Filipino (Tagalog), and English**. It has two sides:

- **Frontend/Backend** = Laravel 12 (PHP) web app — the UI, database, user auth, history
- **AI Engine** = Python FastAPI microservice — the brains, does all translation and document processing

They talk over HTTP. Laravel sends text/documents to Python, Python translates using an AI model, and sends results back.

---

## The Big Picture — Data Flow

```
YOUR BROWSER
      |
      | (HTTPS)
      v
LARAVEL (PHP) ─── trilingua-code/
  |  Routes (web.php)
  |  Controllers (app/Http/Controllers/)
  |  Services (app/Services/)
  |  Models (app/Models/)
  |  Views (resources/views/)
  |  Jobs (app/Jobs/)
  |
  |  Database (SQLite) — users, translation history
  |
  |  Supabase — file storage (optional cloud bucket)
  |
  |  (HTTP POST localhost:5000)
  v
PYTHON AI ENGINE ─── Model/
  |  server.py — FastAPI entry point
  |  pipeline/ — translation_pipeline.py, document_pipeline.py
  |  providers/ — gptoss.py, mistral.py (talk to AI APIs)
  |  ai/ — mistral_provider.py, ollama_provider.py (analysis, non-translation AI)
  |  document/ — extractor.py, reconstructor.py, ocr_extractor.py, chunker.py
  |  memory/ — context buffer, glossary, document memory
  |  cache/ — sqlite_cache.py (persistent translation cache)
  |  validators/ — hallucination_detector, quality reviewer
  |  prompts/ — system prompts, specialized document prompts
  |
  |  (HTTP requests to AI API)
  v
AI PROVIDER
  - GPT-OSS (Ollama Cloud) = default, runs locally on port 11434
  - Mistral AI = fallback, cloud API
  - Analysis (separate): Mistral cloud when key set, else local Ollama
```

---

## How a Translation Request Travels (Step by Step)

### TEXT TRANSLATION

1. **User types text** in `translation.blade.php` frontend, clicks Translate
2. **JavaScript** in that same file sends POST `/translate` with `{text, source_lang, target_lang}` via `fetch()`
3. **`routes/web.php:57`** routes it to `TranslationController::translate()`
4. **`TranslationController::translate()`** (`TranslationController.php:42`) validates and calls `$this->translationManager->translateText()`
5. **`TranslationManager::translateText()`** (`TranslationManager.php:46`) sends HTTP POST to Python at `http://127.0.0.1:5000/translate/text`
6. **`server.py`** (`server.py:269`) receives it, creates a `TranslationRequest` DTO, and calls `_translation_pipeline.translate(request)`
7. **`TranslationPipeline::translate()`** (`translation_pipeline.py:265`) builds context, then calls `self.provider.translate()` — goes to `GPTOSSProvider` or `MistralProvider`
8. **Provider** (`gptoss.py` or `mistral.py`) sends the text + system prompt + user prompt to the AI model API
9. **AI model** returns translated text
10. **Response flows back** the same way — Python returns JSON, Laravel returns JSON, browser shows it

### DOCUMENT TRANSLATION

1. **User attaches a file** (docx, pdf, txt, md, csv, rtf, odt, pptx, xlsx) in the UI
2. **JS sends POST `/translate`** with `FormData` containing the file
3. **Laravel controller** dispatches a **`TranslateDocumentJob`** to the queue (`TranslationController.php:103`)
4. **Job** (`TranslateDocumentJob.php:56`) stores initial "processing" status in Laravel cache and calls `$translationManager->translateDocument()` → POST to Python at `/translate/document`
5. **`server.py`** (`server.py:311`) receives file, creates `DocumentTranslationRequest`, calls `_document_pipeline.translate(request)`
6. **`DocumentPipeline::translate()`** (`document_pipeline.py:124`) orchestrates the whole pipeline:
   - **Extraction** — `document/extractor.py` reads the file format, extracts text blocks with metadata (style, position, font). For PDFs, per-line records with per-span runs and links are captured
   - **OCR Fallback** — for scanned/image-based PDFs where PyMuPDF extracts nothing, `document/ocr_extractor.py` runs Tesseract OCR at 300 DPI and feeds the blocks back into the pipeline
   - **AI Analysis** (Phase 1) — `document_analyzer.py` sends blocks to analysis AI to detect document type, structure, terminology
   - **Prepass** (Phase 7) — sends first 500 tokens to AI for summary + key terms as context injection
   - **Document Memory** (Phase 2) — builds a cross-document context store
   - **Translation** (Phase 3-6) — splits into chunks, translates each via `TranslationPipeline::batch_translate_blocks()`
   - **Reconstruction** — `document/reconstructor.py` writes translated text back into the original format (PDFs use a per-line redact-and-reinsert strategy)
   - **Result** — returns the translated file path
7. **Job** receives the translated file, uploads it to Supabase Storage (or falls back to inline base64), stores the download URL in cache, creates history record in SQLite
8. **JS polls** `GET /translate/status/{jobId}` every 2 seconds until status is "completed", then shows download link

---

## Directory Structure: Every Folder Explained

### `trilingua-code/` — The Laravel Web App

#### `app/Http/Controllers/`
| File | What It Does |
|---|---|
| `TranslationController.php` | Handles POST `/translate` (text & document), GET `/translate` (page), GET `/translate/status/{jobId}` (polling) |
| `DashboardController.php` | GET `/dashboard` — loads stats (total docs, translations this month, words translated) |
| `DocumentsController.php` | GET `/documents` — shows My Documents page with originals + their translations |
| `HistoryController.php` | GET `/history`, GET `/history/{id}`, DELETE `/history/{id}`, POST redownload/redownload-original |
| `SettingsController.php` | GET/POST `/settings` — account info, password, theme, language preference |
| `Controller.php` | Base class (empty, just for type hierarchy) |
| `Auth/` | Login, Register, Password Reset (ForgotPassword, ResetPassword) |

#### `app/Models/`
| File | What It Does |
|---|---|
| `User.php` | Eloquent model for the `users` table. Supports theme, language, is_admin, password resets |
| `TranslationHistory.php` | Eloquent model for `translation_history` table. Has relationships: `user()`, `parentDocument()`, `translations()` |

#### `app/Services/`
| File | What It Does |
|---|---|
| `TranslationService.php` | **DEPRECATED** — old service using cURL/file_get_contents. Still works but all new code uses TranslationManager |
| `Translation/TranslationManager.php` | **MODERN** — Laravel's only translation entry point. Uses Laravel Http client, reads config from `config/translation.php`. Has `translateText()`, `translateDocument()`, `health()` |
| `HistoryService.php` | CRUD for translation_history table. `insertRecord()`, `getHistory()`, `getRecord()`, `deleteRecord()`, `getOriginalsWithTranslations()` |
| `StorageService.php` | Supabase Storage integration. `uploadFile()`, `deleteFile()`, `generateSignedUrl()` |

#### `app/Jobs/`
| File | What It Does |
|---|---|
| `TranslateDocumentJob.php` | Queued job for async document translation. Stores intermediate status in Laravel cache for frontend polling. Handles Supabase upload + inline download fallback |

#### `app/Exceptions/`
| File | What It Does |
|---|---|
| `TranslationException.php` | Custom exception for translation errors (extends RuntimeException) |

#### `config/`
| File | What It Does |
|---|---|
| `translation.php` | Python service URL, timeout, supported languages, supported formats, extension map |
| `app.php`, `auth.php`, `database.php`, etc. | Standard Laravel config |

#### `routes/`
| File | What It Does |
|---|---|
| `web.php` | All web routes. Auth routes with rate limiting (10 req/min), protected routes (60 req/min), translate status endpoint outside auth |

#### `resources/views/`
| File | What It Does |
|---|---|
| `layouts/app.blade.php` | Main app shell — sidebar nav, toast system, dark/light theme, mobile responsive |
| `translation.blade.php` | Translation page — language selectors, source textarea/file upload, output panel, text-to-speech, copy/save buttons, JS polling logic |
| `dashboard.blade.php` | Dashboard — greeting, stat cards (total docs, monthly translations, words), recent translations table |
| `history.blade.php` | History — searchable/filterable table, detail modal with metadata, delete with confirmation |
| `my-documents.blade.php` | Documents — grid of originals with their translations, tabs (all/recent/shared/archived) |
| `settings.blade.php` | Settings — sidebar with Account/General sections, name/email/password/theme/language |
| `auth/` | Login and Register forms |
| `errors/` | Error pages |

#### `resources/js/`
| File | What It Does |
|---|---|
| `app.js` | Main JS entry point (imports bootstrap.js) |
| `bootstrap.js` | Laravel Echo, Axios setup, CSRF token |

#### `resources/css/`
| File | What It Does |
|---|---|
| `app.css` | Main CSS entry point (imports Tailwind + base) |
| `base.css` | CSS variables, typography, colors, toast system, skeleton loading |
| `layouts/app.css` | App layout — sidebar, nav, mobile hamburger, brand |
| `views/` | Page-specific CSS (translation.css, dashboard.css, history.css, etc.) |
| `tailwind/` | Tailwind CSS source |

#### `database/`
| What | Details |
|---|---|
| `database.sqlite` | SQLite database file |
| `migrations/` | Laravel migration files for users and translation_history tables |
| `seeders/` | Database seeders |

---

### `Model/` — The Python AI Engine

This is the brain. All AI translation logic lives here.

#### `server.py` — Entry Point
FastAPI server on port `5000`. Endpoints:
- `GET /health` — health check
- `GET /providers` — list providers
- `POST /translate/text` — text translation
- `POST /translate/document` — document translation (returns file)
- `DELETE /cache/clear` — clear SQLite cache

Starts up by:
1. Loading `.env` vars
2. Initializing providers (MistralProvider, GPTOSSProvider, OllamaAnalysisProvider)
3. Creating `TranslationPipeline` + `DocumentPipeline`
4. Running cold-start pre-warming (imports heavy libs, initializes SQLite cache, warms HTTP pool)

#### `dto/` — Data Transfer Objects
| File | What It Does |
|---|---|
| `requests.py` | `TranslationRequest`, `DocumentTranslationRequest` — input contracts. Defines `LANGUAGES` dict (`English→eng_Latn`, `Cebuano→ceb_Latn`, `Filipino→tgl_Latn`) |
| `responses.py` | `TranslationResponse`, `DocumentTranslationResponse`, `HealthResponse`, `ChunkResult` — normalized output contracts |

#### `providers/` — AI API Wrappers
| File | What It Does |
|---|---|
| `base.py` | `TranslationProvider` abstract base class — defines `translate()`, `health()`, `estimate_tokens()` interface |
| `gptoss.py` | `GPTOSSProvider` — talks to Ollama Cloud API at `localhost:11434`. Uses `requests.Session` with connection pooling. Retries 3x on failure. Validates for hallucinations. |
| `mistral.py` | `MistralProvider` — talks to `api.mistral.ai`. Handles rate limiting with exponential backoff. 3 retries. |
| `future_openai.py`, `future_gemini.py`, `future_deepseek.py` | Stubs — raise `NotImplementedError` |

**Key pattern**: Providers only communicate with AI APIs. They contain NO prompt engineering, NO document logic, NO validation. Prompts come from `prompts/` module.

#### `pipeline/` — Orchestration
| File | What It Does |
|---|---|
| `translation_pipeline.py` | **Core translation orchestrator**. `translate()` for single blocks, `translate_chunks()` for chunked text, `batch_translate_blocks()` for documents (concurrent, batched, cached). Key optimizations: ThreadPoolExecutor (16 workers), SQLite cache, short block batching (group <80 token blocks into batches of 5), passthrough filter (skip numbers/URLs/dates). |
| `document_pipeline.py` | **Full document pipeline**. `translate()` orchestrates: extract → analyze → prepass → memory → translate → validate → layout plan → reconstruct. Supports in-place translation for DOCX/PPTX/XLSX, LibreOffice round-trip for PDF, CSV row-by-row. Auto-selects processing mode (fast/balanced/thorough) based on document size. |
| `validation_pipeline.py` | Quality checks: layout validation, number preservation, length ratio, hallucination detection |
| `document_context.py` | `DocumentContext` dataclass — shared state flowing through all pipeline stages. Captures stats, warnings, timing, profiling data. Thread-safe. |
| `phase_profiler.py` | Context managers `phase_profile()` and `llm_call_profile()` for timing pipeline phases |

#### `document/` — File Processing
| File | What It Does |
|---|---|
| `extractor.py` | Reads files: DOCX (paragraphs, tables, headers, footers, text boxes with style metadata), PDF (via PyMuPDF — captures per-line records with bbox, baseline, alignment, per-span runs, font/color/bold/italic, and hyperlinks; normalizes subsetted font names), TXT, MD, RTF, ODT, CSV, PPTX, XLSX |
| `ocr_extractor.py` | OCR fallback for scanned/image-based PDFs. Renders each page at 300 DPI and runs Tesseract OCR (`pytesseract`), producing blocks compatible with the normal pipeline |
| `reconstructor.py` | Writes translated text back into original format. Key function: `_apply_translation_to_paragraph()` distributes translated text proportionally across runs to preserve per-run formatting. PDF path uses `write_pdf_preserved()` — per-line redact-and-reinsert with run-level formatting, system-font embedding, overflow handling, and hyperlink recreation |
| `chunker.py` | `ChunkSplitter` — splits text at sentence boundaries, respects max token limits |
| `semantic_chunker.py` | `SemanticChunker` — replaces naive chunking with structure-aware chunks (keeps headings with content, tables together, lists together). Uses DocumentProfile (NO extra AI calls). |
| `document_analyzer.py` | `DocumentAnalyzer` — sends document preview to AI, returns `DocumentProfile` with document_type, writing_style, sections, structure, terminology, abbreviations, entities |
| `layout_planner.py` | `LayoutPlanner` — predicts text expansion ratios, overflow risk, font scaling (PDF only, Phase 8) |
| `layout.py` | `FontMapper` — resolves PDF font names, maps to built-in PDF fonts. `BackgroundSampler` — samples page background for redaction fills |
| `metadata.py` | Metadata extraction utilities |

#### `memory/` — Context & Consistency
| File | What It Does |
|---|---|
| `document_memory.py` | `DocumentMemory` — full-document awareness. Stores document profile, terminology translations, abbreviations, named entities, recent chunks. Provides relevant context for each block. |
| `glossary.py` | `GlossaryStore` — source→target term pairs with regex substitution |
| `terminology.py` | `ContextBuffer` — sliding window (last 2 translated blocks), `TerminologyManager` |
| `translation_memory.py` | Placeholder for future fuzzy-match translation memory |
| `translation_cache.py` | `TranslationCache` — in-memory hash-based cache for dedup within a document |

#### `cache/`
| File | What It Does |
|---|---|
| `sqlite_cache.py` | `SQLiteTranslationCache` — persistent SQLite-backed cache. SHA-256 key (source + lang + provider). WAL mode + threading lock. TTL-based expiry. Two-layer: in-memory per doc + persistent SQLite. |

#### `prompts/` — AI Prompt Engineering
| File | What It Does |
|---|---|
| `system.py` | `build_system_prompt()` — generic system prompt with strict rules (output only translation, preserve names/numbers/dates, no explanations) |
| `translation.py` | `build_translation_prompt()` — user prompt with Cebuano/Filipino few-shot examples showing verb-focus preservation and proper noun handling |
| `specialized/__init__.py` | `get_system_prompt()` — selects specialized prompt based on DocumentProfile document_type |
| `specialized/legal.py`, `academic.py`, `medical.py`, `technical.py`, `business.py`, `resume.py`, `invoice.py`, `presentation.py` | Domain-specific system prompts with specialized terminology rules |
| `prepass.py` | `build_prepass_system_prompt()`, `build_prepass_user_prompt()`, `build_prepass_injection()` — two-pass context injection (Task 5) |
| `quality.py` | `build_batch_quality_review_prompt()` — batched quality review prompt |
| `context.py` | Context-related prompts |

#### `validators/` — Quality Assurance
| File | What It Does |
|---|---|
| `hallucination_detector.py` | `sanitize_translation()` — removes leaked delimiters, collapses repetitions. `detect_hallucination()` — checks for excessive length ratios, untranslated segments, repetitive patterns |
| `translation_validator.py` | `BLEUReporter` — computes BLEU scores against reference. `LayoutValidator` — checks block count match, missing text |
| `ai_quality_reviewer.py` | `AIQualityReviewer` — AI-powered quality review. Detects missing content, hallucinations, terminology errors, number/date errors. Returns `QualityReview` with score (0-100) and issues. Supports batched review (single AI call for all blocks). |

#### `ai/`
| File | What It Does |
|---|---|
| `base.py` | `AIAnalysisProvider` abstract base — defines `analyze(system_prompt, user_prompt) → dict` interface |
| `mistral_provider.py` | `MistralAnalysisProvider` — **default analysis provider when `MISTRAL_API_KEY` is set**. Uses the same key as the translation provider (`mistral-small-latest` by default, overridable via `MISTRAL_ANALYSIS_MODEL`). Handles document analysis, quality review, layout planning. Returns parsed JSON. |
| `ollama_provider.py` | `OllamaAnalysisProvider` — local fallback used when no Mistral key is set. Uses a separate smaller model (`OLLAMA_ANALYSIS_MODEL`, default `llama3.1:8b`) for non-translation AI tasks (document analysis, quality review, layout planning). Returns parsed JSON. |

#### `config/`
| File | What It Does |
|---|---|
| `processing_modes.py` | Three modes: **Fast** (no AI features), **Balanced** (document analyzer, memory, semantic chunking, specialized prompts, quality review, cache, prepass), **Thorough** (all of Balanced + layout planner) |

---

### `adapters/`, `intelligence/`, `pipeline/`, `translation/`, `workers/`, `reconstruction/`, `exceptions/`, `validation/`

`intelligence/` and `storage/` (with an empty `checkpoints/`) exist under `Model/` as placeholders for future expansion. The real code lives in `trilingua-code/`.

---

## Processing Modes — Fast vs Balanced vs Thorough

| Feature | Fast | Balanced | Thorough |
|---|---|---|---|
| AI Document Analyzer | No | Yes | Yes |
| Document Memory | No | Yes | Yes |
| Semantic Chunking | No | Yes | Yes |
| Specialized Prompts | No | Yes | Yes |
| AI Quality Review | No | Yes | Yes |
| Translation Cache | No | Yes | Yes |
| Prepass (Context Injection) | No | Yes | Yes |
| AI Layout Planner | No | No | Yes |

In "auto" mode, the pipeline picks based on file size and complexity.

---

## Key Optimizations Built In

1. **Concurrent translation** — `ThreadPoolExecutor` with 16 workers for parallel API calls
2. **SQLite cache** — persistent, SHA-256 keyed, TTL-based, two-layer (in-memory + disk)
3. **Short block batching** — groups blocks under ~80 tokens into batches of 5-8 for a single API call
4. **Passthrough filter** — skips translation for numbers, dates, URLs, emails, file paths, punctuation-only text (2-char text with letters like "Oh"/"Hi" is now translated)
5. **Batched quality review** — single AI call reviews all blocks instead of one per block (~58% faster)
6. **Cold start pre-warming** — imports heavy libs, initializes cache, warms HTTP pool at startup
7. **Hallucination detection** — regex + AI two-layer validation with automatic retranslation
8. **Automatic language-specific prompts** — few-shot examples for Cebuano/Filipino with verb-focus preservation
9. **PDF per-line redact-and-reinsert** — original text replaced line-by-line, preserving images, vector graphics, links, and run-level (bold/italic/size) formatting
10. **PDF OCR fallback** — scanned/image-based PDFs auto-retry via Tesseract OCR when text extraction yields nothing

---

## The Translation History Table

`translation_history` in SQLite tracks everything:

| Column | Purpose |
|---|---|
| `user_id` | Who owns it |
| `translation_type` | `"text"` or `"document"` |
| `original_filename` | For documents |
| `translated_filename` | Output file name |
| `source_language` / `target_language` | Language pair |
| `storage_path` / `original_storage_path` | Supabase paths |
| `parent_document_id` | Links child translations to original |
| `file_size` | Size in bytes |
| `status` | Job status |
| `signed_url_expires_at` | When download link expires |
| `source_text` / `translated_text` | For text translations |

---

## How to Run

```bash
# Terminal 1: Python AI Engine
cd Model
python server.py
# → http://127.0.0.1:5000

# Terminal 2: Laravel Web App
php artisan serve
# → http://127.0.0.1:8000
```

---

---

## TEXT TRANSLATION — Exact Code Data Flow

Every line below shows how data moves from click to result.

### 1. Browser JS → Laravel

**`translation.blade.php:246-271`** — User clicks Translate

```js
var formData = new FormData();
formData.append('source_lang', sourceLang.value);  // "English"
formData.append('target_lang', targetLang.value);  // "Cebuano"
formData.append('text', sourceText.value);          // the actual text
formData.append('_token', csrfToken);               // CSRF protection

fetch('/translate', {
    method: 'POST',
    headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json' },
    body: formData
})
```

**`routes/web.php:57`** — Laravel catches the POST and routes it

```php
Route::post('/translate', [TranslationController::class, 'translate'])->name('translate.submit');
```

### 2. Laravel Controller → TranslationManager

**`TranslationController.php:42-155`** — Validates, creates DTO, calls service

```php
$validated = $request->validate([
    'source_lang' => ['required', Rule::in(['English', 'Cebuano', 'Filipino'])],
    'target_lang' => ['required', Rule::in(['English', 'Cebuano', 'Filipino']), Rule::notIn([$sourceLang])],
    'text'        => ['nullable', 'string', 'max:8000'],
]);

// CREATES DTO — wraps data into a typed object
$translationRequest = new TranslationRequest(
    text: $request->input('text'),         // string
    sourceLang: $sourceLang,                // "English"
    targetLang: $targetLang,                // "Cebuano"
);

// CALLS the service
$result = $this->translationManager->translateText($translationRequest);

// RETURNS JSON back to browser
return response()->json(['translated' => $result->translatedText]);
```

### 3. TranslationManager → Python Server

**`TranslationManager.php:46-90`** — HTTP POST to Python via Laravel Http client

```php
$response = Http::timeout($this->timeout)
    ->post("{$this->pythonUrl}/translate/text", $request->toArray());
// $this->pythonUrl = config('translation.python_service.url') = http://127.0.0.1:5000
// $request->toArray() = { text: "Hello", source_lang: "English", target_lang: "Cebuano" }

// HTTP POST to http://127.0.0.1:5000/translate/text
// Body: { "text": "Hello", "source_lang": "English", "target_lang": "Cebuano" }
```

**`config/translation.php:15-17`** — Where the URL lives

```php
'python_service' => [
    'url' => env('PYTHON_SERVICE_URL', 'http://127.0.0.1:5000'),
    'timeout' => env('PYTHON_SERVICE_TIMEOUT', 600),
],
```

### 4. Python server.py → TranslationPipeline

**`server.py:263-302`** — FastAPI endpoint receives it

```python
class TextRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str

@app.post("/translate/text")
def translate_text(req: TextRequest):
    # req.text = "Hello", req.source_lang = "English", req.target_lang = "Cebuano"

    # CREATES Python DTO
    request = TranslationRequest(
        text=req.text.strip(),
        source_lang=req.source_lang,
        target_lang=req.target_lang,
    )
    # CALLS the pipeline
    result = _translation_pipeline.translate(request)

    # RETURNS JSON
    return {
        "translated": result.translated_text,    # "Kumusta"
        "provider": result.provider,              # "gptoss"
        "model": result.model,                    # "gpt-oss:20b-cloud"
        "token_usage": result.token_usage,
        "execution_time_ms": result.execution_time_ms,
    }
```

### 5. TranslationPipeline → AI Provider

**`translation_pipeline.py:265-301`** — Orchestrates the call

```python
def translate(self, request: TranslationRequest) -> TranslationResponse:
    start_time = time.time()

    estimated_tokens = self.provider.estimate_tokens(request.text)  # word count

    # Build context hint from previous translations (sliding window)
    context_hint = request.context_hint
    if not context_hint:
        context_hint = self.context_buffer.get_hint()

    # CALL the provider
    response = self.provider.translate(
        text=request.text,            # "Hello"
        source_lang=request.source_lang,  # "English"
        target_lang=request.target_lang,  # "Cebuano"
        block_type=request.block_type,    # "paragraph"
        context_hint=context_hint,        # "" or previous chunk text
        document_type=request.document_type,  # "" or "legal_contract" etc
    )

    # Store in context buffer for next chunk
    if response.success and response.translated_text:
        self.context_buffer.push(response.translated_text)

    response.execution_time_ms = (time.time() - start_time) * 1000
    return response
```

### 6. Provider → AI Model API

**`gptoss.py:40-128`** (or `mistral.py:56-226` for Mistral) — Builds prompts, calls model

```python
def translate(self, text, source_lang, target_lang, block_type, context_hint, document_type):
    # 1. BUILD SYSTEM PROMPT — picks specialized prompt based on document type
    from prompts.specialized import get_system_prompt
    system_msg = get_system_prompt(document_type, target_lang)
    # → prompts/specialized/__init__.py:53
    #   → if document_type = "legal", picks LEGAL_PROMPT from legal.py
    #   → else falls back to system.py:build_system_prompt()

    # 2. BUILD USER PROMPT — contains the text to translate + few-shot examples
    from prompts.translation import build_translation_prompt
    user_msg = build_translation_prompt(text, source_lang, target_lang, block_type)
    # → prompts/translation.py:16
    #   → includes Cebuano/Filipino few-shot examples like:
    #     "EN: I am going to the market. → CEB: Moadto ko sa merkado."

    # 3. ADD CONTEXT if available
    if context_hint:
        user_msg = f"Previous context: {context_hint}\n\n{user_msg}"

    # 4. CALL THE AI MODEL (Ollama Cloud API)
    resp = self._session.post(
        self._api_url,  # http://localhost:11434/api/chat
        json={
            "model": self._model,                    # "gpt-oss:20b-cloud"
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            "stream": False,
            "options": {"temperature": 0.3},
        },
        timeout=60,
    )

    # 5. EXTRACT result
    result = data.get("message", {}).get("content", "").strip()

    # 6. VALIDATE for hallucinations (only blocks >= 5 words)
    from validators.hallucination_detector import sanitize_translation, detect_hallucination
    result = sanitize_translation(result, text)  # removes delimiters, repetitions
    is_hallucinated, reason = detect_hallucination(result, text)  # checks length ratio, etc.

    # 7. RETURN
    return TranslationResponse(
        translated_text=result,   # "Kumusta"
        provider="gptoss",
        model="gpt-oss:20b-cloud",
        token_usage={ "input": N, "output": N },
        execution_time_ms=elapsed_ms,
    )
```

### 7. Response flows back the same way

```
gptoss.py returns TranslationResponse
  → translation_pipeline.py returns TranslationResponse
    → server.py returns JSON { translated: "Kumusta", ... }
       → Laravel TranslationManager reads JSON body
         → creates TranslationResponse DTO
           → TranslationController returns JSON { translated: "Kumusta" }
             → browser JS at translation.blade.php:293 reads data.translated
               → puts it in <div id="output-text">
```

---

## DOCUMENT TRANSLATION — Exact Code Data Flow

The document path splits into **sync** (Laravel dispatches job → returns job_id immediately) and **async** (the job runs, browser polls).

### 1. Browser → Laravel (Same as text, but with file)

**`translation.blade.php:257-260, 267-271`**

```js
formData.append('document', file);  // the actual file object

fetch('/translate', { method: 'POST', body: formData })
```

### 2. Laravel Controller → Dispatches Job

**`TranslationController.php:79-126`** — Detects file, creates job, returns job_id

```php
// DOCUMENT MODE
$uploadedFile = $request->file('document');

// Upload original to Supabase (best-effort)
$this->storage->uploadFile($uploadedFile->getRealPath(), $originalStoragePath);

// Create job
$job = new TranslateDocumentJob(
    $originalName,              // "report.docx"
    $originalExt,               // ".docx"
    $fileSize,                  // 102400
    $sourceLang,                // "English"
    $targetLang,                // "Cebuano"
    $pdfColumnMode,             // "auto"
    $uploadedFile->getRealPath(),  // temp path on disk
    Auth::id(),                 // user id
    $originalStoragePath        // Supabase path or null
);
$jobId = $job->uuid();

dispatch($job);  // queue it

// Return immediately with job ID for polling
return response()->json([
    'job_id' => $jobId,
    'status' => 'processing',
    'message' => 'Document queued for translation...',
    'original_filename' => $originalName,
]);
```

### 3. Browser polls while job runs

**`translation.blade.php:315-357`**

```js
function pollJobStatus(jobId) {
    var interval = setInterval(function () {
        fetch('/translate/status/' + jobId, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.status === 'completed') {
                clearInterval(interval);
                // Show download link
                downloadLink.href = data.download_url || data.download_data;
            } else if (data.status === 'failed') {
                clearInterval(interval);
                showError(outputError, data.error);
            }
        });
    }, 2000);  // every 2 seconds
}
```

### 4. TranslateDocumentJob → TranslationManager (Async)

**`TranslateDocumentJob.php:56-219`**

```php
public function handle(
    TranslationManager $translationManager,
    StorageService $storageService,
    HistoryService $historyService
): void {
    // Store "processing" state
    $this->storeResult(['status' => 'processing']);

    // Recreate UploadedFile from temp path
    $uploadedFile = new UploadedFile($this->tempPath, $this->originalName, ...);

    // CALL TranslationManager
    $translationResult = $translationManager->translateDocument(
        $uploadedFile,          // file object
        $this->sourceLang,      // "English"
        $this->targetLang,      // "Cebuano"
        $this->pdfColumnMode    // "auto"
    );

    // Save the returned binary to disk
    file_put_contents($outputPath, $translationResult['body']);

    // Upload to Supabase Storage
    $storageResult = $storageService->uploadFile($outputPath, $translatedStoragePath);

    // Store result in Laravel cache for browser polling
    $this->storeResult([
        'status' => 'completed',
        'download_url' => $storageResult['signed_url'],
        'download_filename' => $downloadFilename,
    ]);

    // Save to translation_history table
    $historyService->insertRecord([...]);
}
```

### 5. TranslationManager → Python Server (Same pattern as text)

**`TranslationManager.php:97-160`**

```php
$response = Http::timeout($this->timeout)
    ->attach(
        'file',
        file_get_contents($file->getRealPath()),  // file binary
        $file->getClientOriginalName()             // "report.docx"
    )
    ->post("{$this->pythonUrl}/translate/document", [
        'source_lang'     => $sourceLang,      // "English"
        'target_lang'     => $targetLang,      // "Cebuano"
        'pdf_column_mode' => $pdfColumnMode,   // "auto"
    ]);

$body = $response->body();  // ← this is the translated FILE (binary)

return [
    'body'              => $body,
    'download_filename' => $stem . '_translated' . $outExt,
    'mime_type'         => $response->header('Content-Type'),
];
```

### 6. Python server.py → DocumentPipeline

**`server.py:311-397`**

```python
@app.post("/translate/document")
async def translate_document(
    file: UploadFile = File(...),
    source_lang: str = Form(...),    # "English"
    target_lang: str = Form(...),    # "Cebuano"
    pdf_column_mode: str = Form("auto"),
    mode: str = Form("balanced"),
):
    # Save uploaded file to temp directory
    contents = await file.read()
    with open(input_path, "wb") as f:
        f.write(contents)

    # CREATES document DTO
    request = DocumentTranslationRequest(
        file_path=input_path,       # temp file path
        source_lang=source_lang,    # "English"
        target_lang=target_lang,    # "Cebuano"
        pdf_column_mode=pdf_column_mode,
        mode=mode,
    )

    # CALL DocumentPipeline
    result = _document_pipeline.translate(request)

    # Read the translated file
    with open(actual_output, "rb") as f:
        file_contents = f.read()

    # Return as streaming binary download
    return StreamingResponse(
        io.BytesIO(file_contents),
        headers={"Content-Disposition": f"attachment; filename={download_name}"}
    )
```

### 7. DocumentPipeline — The Full Engine

**`document_pipeline.py:124-432`**

```python
def translate(self, request: DocumentTranslationRequest) -> DocumentTranslationResponse:
    # ── STEP 0: SETUP ──────────────────────────────────────
    ctx = DocumentContext()
    ctx.mode = self._determine_mode(request)  # fast/balanced/thorough/auto
    ext = os.path.splitext(request.file_path)[1].lower()

    # ── STEP 1: EXTRACT ───────────────────────────────────
    # document/extractor.py:18 analyze_document()
    #   → for .docx: read_docx() → python-docx reads paragraphs, tables, headers, footers
    #   → for .pdf:  read_pdf() → PyMuPDF reads text blocks with position
    #   → for .txt:  read_txt() → plaintext lines
    # Returns list of { type, text, style, position, page, ... }
    data, detected_ext = analyze_document(request.file_path)
    blocks = data  # e.g. [{"type":"paragraph","text":"Hello world","style":{...}}, ...]

    # ── STEP 2: AI ANALYSIS (Phase 1) ─────────────────────
    # document/document_analyzer.py
    # Sends block texts to analysis AI → returns DocumentProfile
    # Fields: document_type, writing_style, sections, terminology, abbreviations, entities
    profile = self._document_analyzer.analyze(blocks)

    # ── STEP 3: PREPASS (Phase 7) ─────────────────────────
    # prompts/prepass.py
    # Sends first 500 tokens → returns { summary, domain, terms }
    # Injected as context into every translation block
    prepass_result = self._ai_provider.analyze(sys_prompt, user_prompt)
    ctx.prepass_summary = prepass_result.get("summary", "")
    ctx.prepass_domain = prepass_result.get("domain", "")
    ctx.prepass_terms = prepass_result.get("terms", [])

    # ── STEP 4: DOCUMENT MEMORY (Phase 2) ─────────────────
    # memory/document_memory.py
    # Full-document context: terminology, abbreviations, named entities
    memory = DocumentMemory()
    memory.store_profile(profile)
    ctx.document_memory = memory

    # ── STEP 5: TRANSLATE (Phase 3-6) ─────────────────────
    # translation_pipeline.py:447 batch_translate_blocks()
    # Uses ThreadPoolExecutor (16 workers) for concurrent API calls
    translated_blocks = self.translation_pipeline.batch_translate_blocks(
        blocks,
        source_lang, target_lang,
        document_memory=memory,
        mode=ctx.mode,
        translation_cache=sqlite_cache,
        quality_reviewer=ai_reviewer,
        semantic_chunker=semantic_chunker,
        document_profile=profile,
    )

    # ── STEP 6: LAYOUT PLANNING (Phase 8, PDF only) ───────
    # document/layout_planner.py
    # Predicts text expansion ratios, overflow risk
    ctx.layout_plan = self._layout_planner.plan(blocks, translated_blocks, ...)

    # ── STEP 7: RECONSTRUCT ───────────────────────────────
    # document/reconstructor.py
    # Writes translated text BACK into original format
    # For DOCX: _translate_docx_inplace_with_translator()
    #   → iterates paragraphs, calls translate_fn for each
    #   → _apply_translation_to_paragraph() distributes text proportionally across runs
    # For PDF: reconstruct_document() → writes new PDF with PyMuPDF
    reconstruct_document(translated_blocks, output_file, request.file_path, detected_ext)

    return DocumentTranslationResponse(output_path=output_file, ...)
```

### 8. How blocks flow through translation

**`translation_pipeline.py:447-739`** — The concurrent engine

```python
def batch_translate_blocks(self, blocks, source_lang, target_lang, ...):
    # PHASE 1: Identify passthrough blocks (numbers, URLs, dates — skip translation)
    # _is_passthrough_block() → regex checks
    passthrough_indices = {i for i, b in enumerate(blocks) if _is_passthrough_block(b["text"])}

    # PHASE 2: Check SQLite cache for all blocks
    cached_results = {}
    for i, block in enumerate(blocks):
        if i not in passthrough_indices:
            cached = translation_cache.get(block["text"], target_lang, provider.name)
            if cached:
                cached_results[i] = cached

    # PHASE 3: Short block batching (group <80 token blocks into batches of 5-8)
    # → sends multiple blocks in ONE API call for efficiency
    batches = []
    for item in work_items:
        if token_count < 80 and batch_size < max_batch_items:
            current_batch.append(item)  # group small blocks together
        else:
            batches.append(current_batch)

    # PHASE 4: Translate concurrently with ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=16) as executor:
        for batch in batches:
            future = executor.submit(self._translate_batch_worker, batch, ...)

    # PHASE 5: Reassemble in document order
    for i, block in enumerate(blocks):
        if i in passthrough_indices:     # copy source text as-is
        elif i in cached_results:        # use cached translation
        elif i in results:               # use fresh translation
            translated_blocks.append(new_block)
```

### 9. How the reconstructor writes it back

**`document/reconstructor.py:20-71`** — The key formatting function

```python
def _apply_translation_to_paragraph(para, translated_text, glossary_store):
    """Distribute translated text across runs preserving per-run formatting."""

    runs = para.runs
    if len(runs) == 1:
        runs[0].text = translated_text  # fast path
        return

    # Multi-run: distribute proportionally by character count
    original_text = "".join(r.text for r in runs)
    orig_len = len(original_text)
    tgt_len = len(translated_text)

    for i, run in enumerate(runs):
        if i == len(runs) - 1:
            run.text = translated_text[char_pos:]  # last run gets remainder
        else:
            run_orig_len = len(run.text)
            run_tgt_len = max(0, int(tgt_len * run_orig_len / orig_len))
            run.text = translated_text[char_pos:char_pos + run_tgt_len]
            char_pos += run_tgt_len
```

---

## KEY: Text vs Document Flow Differences

| Aspect | Text Translation | Document Translation |
|---|---|---|
| **Speed** | Synchronous (instant) | Async (polled, can take minutes) |
| **Laravel path** | Controller → TranslationManager directly | Controller → Job → TranslationManager |
| **Python path** | TranslationPipeline.translate() | DocumentPipeline.translate() → extract → analyze → prepass → memory → batch translate → reconstruct |
| **Output** | JSON `{ translated: "..." }` | Binary file (via Supabase URL or inline base64) |
| **History** | Written in Controller | Written in Job |
| **Concurrency** | Single API call | ThreadPoolExecutor with 16 workers + batching |
| **AI features** | None (just translate) | Up to 8 phases depending on mode |

## The Mental Model

Think of Trilingua as a **translation factory assembly line**:

1. **Receiving Dock** (`server.py`) — accepts jobs
2. **Material Handler** (`extractor.py`) — unwraps documents, extracts raw text blocks
3. **Inspector** (`document_analyzer.py`) — looks at the text, identifies document type and structure
4. **Prepper** (`prepass.py`) — reads the first bit to understand the domain and key terms
5. **Memory Keeper** (`document_memory.py`) — remembers what was translated before to stay consistent
6. **Translators** (`TranslationPipeline` + providers) — the workers who do the actual translation
7. **Quality Control** (`hallucination_detector.py` + `ai_quality_reviewer.py`) — checks for mistakes
8. **Packager** (`reconstructor.py`) — puts everything back into original document format
9. **Shipping** (Laravel controller + job) — hands the result to the user
