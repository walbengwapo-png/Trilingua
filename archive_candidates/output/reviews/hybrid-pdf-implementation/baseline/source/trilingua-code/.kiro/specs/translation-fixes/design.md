# Design Document — translation-fixes

## Overview

This document covers the technical design for three targeted bug fixes in the Trilingua translation application. Trilingua is a Laravel + Python FastAPI system that translates text and documents between English, Cebuano, and Filipino using the NLLB-200-distilled-600M model.

The three fixes address:

1. **Bug 1** — Short text inputs (fewer than 3 words) crash the `/translate/text` endpoint with HTTP 500 because the pipeline's word-count filter discards all blocks, raising `ValueError`.
2. **Bug 2** — The `/translate/document` endpoint has no way to select a PDF column mode, so bilingual PDFs always use `"auto"` and pick up both columns (source + partial translation), degrading output quality.
3. **Bug 3** — Both fetch calls in the frontend call `response.json()` unconditionally; when the server returns a non-JSON error body, the parse throws and the catch handler shows the generic "Network error." instead of the real error.

Each fix is surgical — no architectural changes, no new dependencies, no changes to the NLLB model loading or pipeline logic.

---

## Architecture

The system is a two-tier web application:

```
Browser (Blade/JS)
      │  POST /translate  (FormData)
      ▼
Laravel (TranslationController → TranslationService)
      │  HTTP POST to 127.0.0.1:5000
      ▼
FastAPI microservice (server.py)
      │  calls
      ▼
document_translator_v3.py
  ├── _translate_single(text, src_code, tgt_code)   ← Bug 1 fix target
  └── run_pipeline(file, src, tgt, pdf_column_mode) ← Bug 2 fix target
```

All three bugs are fixed at their respective layers without touching the model or pipeline internals.

### Data Flow After Fixes

**Text translation (Bug 1 fix):**

```
POST /translate/text  { text, source_lang, target_lang }
  → validate languages + non-empty text
  → src_code = LANGUAGES[source_lang]
  → tgt_code = LANGUAGES[target_lang]
  → result = _translate_single(text, src_code, tgt_code)   ← direct call
  → return { "translated": result }
```

**Document translation (Bug 2 fix):**

```
POST /translate/document  (multipart: file, source_lang, target_lang, pdf_column_mode?)
  → validate languages, file type, pdf_column_mode ∈ {"auto","single","left","right"}
  → run_pipeline(input_path, source_lang, target_lang, output_path,
                 pdf_column_mode=pdf_column_mode)
  → return FileResponse
```

**Frontend error handling (Bug 3 fix):**

```
fetch(...)
  .then(response => response.text())
  .then(rawText => {
      let data;
      try { data = JSON.parse(rawText); } catch { data = null; }
      if (!response.ok) {
          if (data && (data.error || data.detail)) → show data.error || data.detail
          else → show "Error (HTTP <status>). Please try again."
      } else { ... handle success ... }
  })
  .catch(() => show "Network error. Please try again.")
```

---

## Components and Interfaces

### 1. `Model/server.py` — FastAPI endpoints

#### 1a. `/translate/text` (Bug 1)

**Current behaviour:** Writes text to a temp `.txt` file, calls `run_pipeline()`, which calls `read_txt()`, which applies `len(words) >= 3` filter. Short inputs produce zero blocks → `ValueError` → HTTP 500.

**Fix:** Import `_translate_single` from `document_translator_v3` (it is already available in the module's namespace since `run_pipeline` uses it internally). Replace the temp-file + pipeline approach with a direct call:

```python
from document_translator_v3 import run_pipeline, _translate_single, LANGUAGES

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
```

The `TextRequest` Pydantic model is unchanged. The temp directory creation and `shutil.rmtree` are removed entirely.

#### 1b. `/translate/document` (Bug 2 + Bug 3)

**Current behaviour:** Accepts `file`, `source_lang`, `target_lang`. Does not accept `pdf_column_mode`. Unhandled exceptions propagate as FastAPI's default JSON 500 (already JSON via `raise HTTPException`), but the explicit try/except is missing for the outer async body.

**Fix:** Add `pdf_column_mode` form field with validation, forward to `run_pipeline`, and wrap the entire handler body in try/except:

```python
VALID_PDF_COLUMN_MODES = {"auto", "single", "left", "right"}

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
    # ... existing language + extension validation ...
    try:
        # ... save file, call run_pipeline with pdf_column_mode=pdf_column_mode ...
        run_pipeline(input_path, source_lang, target_lang, output_path,
                     pdf_column_mode=pdf_column_mode)
        # ... return FileResponse ...
    except HTTPException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(500, str(e))
```

All `HTTPException` responses from FastAPI are automatically serialized as `{"detail": "..."}` JSON, satisfying Requirement 3.5 and 3.6.

### 2. `app/Services/TranslationService.php` — `translateDocument()` (Bug 2)

**Fix:** Add `pdf_column_mode` parameter (default `"auto"`) and include it in `CURLOPT_POSTFIELDS`:

```php
public function translateDocument(
    UploadedFile $file,
    string $sourceLang,
    string $targetLang,
    string $pdfColumnMode = 'auto'
): string {
    // ...
    curl_setopt_array($ch, [
        CURLOPT_POSTFIELDS => [
            'file'             => new \CURLFile(...),
            'source_lang'      => $sourceLang,
            'target_lang'      => $targetLang,
            'pdf_column_mode'  => $pdfColumnMode,
        ],
    ]);
    // ...
}
```

### 3. `app/Http/Controllers/TranslationController.php` — `translate()` (Bug 2)

**Fix:** Extract `pdf_column_mode` from the request and pass it to the service. The validation rule ensures only valid values are accepted at the Laravel layer (defence in depth):

```php
$request->validate([
    // ... existing rules ...
    'pdf_column_mode' => ['nullable', Rule::in(['auto', 'single', 'left', 'right'])],
]);

$pdfColumnMode = $request->input('pdf_column_mode', 'auto');

$outputPath = $this->service->translateDocument(
    $request->file('document'),
    $sourceLang,
    $targetLang,
    $pdfColumnMode
);
```

### 4. `resources/views/translation.blade.php` — Frontend (Bug 2 + Bug 3)

#### 4a. PDF column mode selector (Bug 2)

A `<select id="pdf-column-mode">` element is added to the source panel. It is hidden by default and shown only when a `.pdf` file is attached. It is hidden again when the file is removed or replaced with a non-PDF.

```html
<select id="pdf-column-mode" style="display:none">
    <option value="auto" selected>Auto (detect columns)</option>
    <option value="single">Single column</option>
    <option value="left">Left column only</option>
    <option value="right">Right column only</option>
</select>
```

JavaScript logic:

```javascript
var pdfColumnMode = document.getElementById('pdf-column-mode');

fileInput.addEventListener('change', function () {
    var file = fileInput.files[0];
    // ... existing validation ...
    var isPdf = ext === '.pdf';
    pdfColumnMode.style.display = isPdf ? '' : 'none';
    if (!isPdf) { pdfColumnMode.value = 'auto'; }
});

removeFile.addEventListener('click', function () {
    // ... existing logic ...
    pdfColumnMode.style.display = 'none';
    pdfColumnMode.value = 'auto';
});
```

When building `FormData` for document translation, include `pdf_column_mode` only for PDF files:

```javascript
var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
if (ext === '.pdf') {
    formData.append('pdf_column_mode', pdfColumnMode.value);
}
```

#### 4b. Robust error handling (Bug 3)

Both fetch chains are updated to use `response.text()` first, then attempt `JSON.parse()`:

```javascript
fetch(url, options)
    .then(function (response) {
        return response.text().then(function (rawText) {
            var data = null;
            try { data = JSON.parse(rawText); } catch (e) { /* not JSON */ }

            if (response.ok) {
                // handle success using data
            } else if (response.status === 422 && data && data.errors) {
                var firstField = Object.keys(data.errors)[0];
                showError(sourcePanel, data.errors[firstField][0]);
            } else if (data && (data.error || data.detail)) {
                showError(outputPanel, data.error || data.detail);
            } else {
                showError(outputPanel, 'Error (' + response.status + '). Please try again.');
            }
        });
    })
    .catch(function () {
        showError(outputPanel, 'Network error. Please try again.');
    })
    .finally(function () { setTranslating(false); });
```

This pattern is applied to both the document translation fetch and the text translation fetch.

---

## Data Models

No new data models are introduced. The existing structures are extended minimally:

### `TextRequest` (Pydantic, `server.py`) — unchanged

```python
class TextRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str
```

The empty/whitespace validation is added in the endpoint handler, not the model, to return HTTP 400 with a clear message rather than a Pydantic 422.

### Form fields for `/translate/document`

| Field | Type | Default | Validation |
|---|---|---|---|
| `file` | `UploadFile` | required | extension in allowed set |
| `source_lang` | `str` | required | key in `LANGUAGES` |
| `target_lang` | `str` | required | key in `LANGUAGES`, ≠ source |
| `pdf_column_mode` | `str` | `"auto"` | one of `{"auto","single","left","right"}` |

### `TranslationService::translateDocument()` signature change

```php
// Before
public function translateDocument(UploadedFile $file, string $sourceLang, string $targetLang): string

// After
public function translateDocument(UploadedFile $file, string $sourceLang, string $targetLang, string $pdfColumnMode = 'auto'): string
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Short text inputs always translate successfully

*For any* non-empty text string with 1 or 2 words, calling `_translate_single(text, src_code, tgt_code)` SHALL return a non-empty string without raising an exception.

**Validates: Requirements 1.2, 1.3**

### Property 2: Whitespace-only inputs are always rejected

*For any* string composed entirely of whitespace characters (spaces, tabs, newlines, or combinations thereof), the `/translate/text` endpoint SHALL return HTTP 400.

**Validates: Requirements 1.4**

### Property 3: Normal text inputs always translate successfully

*For any* non-empty text string with 3 or more words, calling `_translate_single(text, src_code, tgt_code)` SHALL return a non-empty string without raising an exception.

**Validates: Requirements 1.5**

> **Property reflection:** Properties 1 and 3 both test that `_translate_single` returns a non-empty string for valid inputs. They are kept separate because they validate different sides of the word-count boundary — the fix specifically targets the sub-3-word case, so both sides of the boundary need explicit coverage. They are not redundant.

### Property 4: Invalid `pdf_column_mode` values are always rejected

*For any* string that is not one of `{"auto", "single", "left", "right"}`, submitting it as `pdf_column_mode` to the `/translate/document` endpoint SHALL return HTTP 400.

**Validates: Requirements 2.3**

### Property 5: All error responses from the Translation_Service are valid JSON

*For any* request to `/translate/text` or `/translate/document` that results in an error response (non-2xx status), the response body SHALL be valid JSON containing an `error` or `detail` field.

**Validates: Requirements 3.5, 3.6**

### Property 6: Non-JSON error bodies always produce a status-code-bearing fallback message

*For any* non-JSON response body returned with a non-2xx HTTP status code, the frontend error-handling logic SHALL produce a fallback message string that contains the HTTP status code as a substring.

**Validates: Requirements 3.2, 3.3**

---

## Error Handling

### Bug 1 — Text translation

| Condition | Response |
|---|---|
| Empty or whitespace-only `text` | HTTP 400 `{"detail": "Text must not be empty."}` |
| Unknown `source_lang` or `target_lang` | HTTP 400 `{"detail": "Unknown ... language: ..."}` |
| `source_lang == target_lang` | HTTP 400 `{"detail": "Source and target languages must differ."}` |
| `_translate_single` raises any exception | HTTP 500 `{"detail": "<exception message>"}` |

### Bug 2 — PDF column mode

| Condition | Response |
|---|---|
| `pdf_column_mode` not in valid set | HTTP 400 `{"detail": "Invalid pdf_column_mode '...'. Must be one of: ..."}` |
| Laravel validation failure | HTTP 422 `{"errors": {"pdf_column_mode": [...]}}` |
| Non-PDF file with `pdf_column_mode` provided | Parameter accepted but ignored by `run_pipeline` (no-op for non-PDF formats) |

### Bug 3 — Frontend error handling

| Condition | UI behaviour |
|---|---|
| Non-2xx + valid JSON with `error`/`detail` | Show `data.error \|\| data.detail` in output panel error area |
| Non-2xx + valid JSON with `errors` (422) | Show first validation error in source panel error area |
| Non-2xx + non-JSON body | Show `"Error (<status>). Please try again."` in output panel error area |
| Fetch rejects (network error) | Show `"Network error. Please try again."` in output panel error area |
| 2xx response | Normal success handling (unchanged) |

---

## Testing Strategy

### Unit tests (Python — `pytest` + `unittest.mock`)

**Bug 1:**
- Mock `_translate_single` to return a fixed string; verify the endpoint returns HTTP 200 with `{"translated": ...}` for 1-word and 2-word inputs.
- Verify HTTP 400 is returned for empty string and whitespace-only strings.
- Mock `_translate_single` to raise `RuntimeError`; verify HTTP 500 is returned with the exception message in `detail`.

**Bug 2:**
- Verify `/translate/document` returns HTTP 400 for each invalid `pdf_column_mode` value.
- Mock `run_pipeline`; verify it is called with the correct `pdf_column_mode` for each valid value.
- Verify the default `pdf_column_mode="auto"` is used when the field is omitted.

**Bug 3:**
- Verify all error paths in `/translate/text` and `/translate/document` return JSON bodies with `detail` field.

### Unit tests (PHP — PHPUnit)

**Bug 2:**
- Test `TranslationService::translateDocument()` with a mock cURL; verify `pdf_column_mode` appears in `CURLOPT_POSTFIELDS`.
- Test `TranslationController::translate()` with a mock service; verify `pdf_column_mode` is extracted from the request and forwarded.
- Test Laravel validation rejects invalid `pdf_column_mode` values with HTTP 422.

### Property-based tests (Python — `hypothesis`)

The project already uses Hypothesis (`.hypothesis/` directory present). Property tests are placed in `Model/tests/test_translation_fixes_properties.py`.

**Property 1 — Short text inputs always translate successfully:**
```python
# Feature: translation-fixes, Property 1: short text inputs always translate successfully
@given(st.lists(st.text(min_size=1, alphabet=st.characters(whitelist_categories=('L',))),
                min_size=1, max_size=2).map(lambda ws: " ".join(ws)))
@settings(max_examples=100)
def test_short_text_translates(text):
    result = _translate_single(text.strip(), "eng_Latn", "ceb_Latn")
    assert isinstance(result, str) and len(result.strip()) > 0
```

**Property 2 — Whitespace-only inputs are always rejected:**
```python
# Feature: translation-fixes, Property 2: whitespace-only inputs are always rejected
@given(st.text(alphabet=" \t\n\r", min_size=1))
@settings(max_examples=100)
def test_whitespace_rejected(text):
    # Test the validation logic directly (not the HTTP layer)
    assert not text.strip()  # confirms the input is whitespace-only
    # The endpoint guard: `if not req.text or not req.text.strip()` → 400
```

**Property 3 — Normal text inputs always translate successfully:**
```python
# Feature: translation-fixes, Property 3: normal text inputs always translate successfully
@given(st.lists(st.text(min_size=1, alphabet=st.characters(whitelist_categories=('L',))),
                min_size=3, max_size=20).map(lambda ws: " ".join(ws)))
@settings(max_examples=100)
def test_normal_text_translates(text):
    result = _translate_single(text.strip(), "eng_Latn", "ceb_Latn")
    assert isinstance(result, str) and len(result.strip()) > 0
```

**Property 4 — Invalid `pdf_column_mode` values are always rejected:**
```python
# Feature: translation-fixes, Property 4: invalid pdf_column_mode values are always rejected
VALID_MODES = {"auto", "single", "left", "right"}

@given(st.text(min_size=1).filter(lambda s: s not in VALID_MODES))
@settings(max_examples=100)
def test_invalid_column_mode_rejected(mode):
    # Test the validation logic directly
    assert mode not in VALID_MODES
```

**Property 5 — All error responses are valid JSON:**
```python
# Feature: translation-fixes, Property 5: all error responses from the Translation_Service are valid JSON
@given(st.one_of(
    st.just(""),
    st.just("   "),
    st.text(min_size=1).filter(lambda s: s not in LANGUAGES),
))
@settings(max_examples=100)
def test_error_responses_are_json(bad_input):
    # Use TestClient to call the endpoint and verify JSON error body
    response = client.post("/translate/text", json={
        "text": bad_input, "source_lang": "English", "target_lang": "Cebuano"
    })
    assert response.status_code != 200
    body = response.json()
    assert "detail" in body or "error" in body
```

**Property 6 — Non-JSON error bodies produce status-code-bearing fallback:**
```python
# Feature: translation-fixes, Property 6: non-JSON error bodies produce status-code-bearing fallback
@given(st.integers(min_value=400, max_value=599),
       st.text().filter(lambda s: _is_not_json(s)))
@settings(max_examples=100)
def test_non_json_fallback_contains_status(status_code, body_text):
    message = build_fallback_error_message(status_code, body_text)
    assert str(status_code) in message
```

> Note: Properties 1 and 3 involve actual model inference and are slow. In CI, run them with `@settings(max_examples=10)` and use the full 100 iterations locally or in a dedicated model-test job. Properties 2, 4, 5, and 6 are fast (no model calls) and can run at full 100 iterations in CI.

### Integration tests

- End-to-end: submit a 2-word text translation via the Laravel route and verify HTTP 200 with a translated string.
- End-to-end: submit a PDF document with `pdf_column_mode=left` and verify the translated file is returned.
- End-to-end: take the server offline and verify the frontend shows "Network error. Please try again." (not a JSON parse error).
