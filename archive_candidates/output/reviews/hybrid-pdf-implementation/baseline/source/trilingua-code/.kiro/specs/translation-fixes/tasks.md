# Implementation Plan: translation-fixes

## Overview

Three surgical bug fixes across the FastAPI microservice, Laravel controller/service, and Blade frontend. No architectural changes, no new dependencies. Each fix is isolated to its layer and builds on the previous to ensure the full request path works end-to-end.

## Tasks

- [x] 1. Fix Bug 1 — Route `/translate/text` directly through `_translate_single()`
  - [x] 1.1 Update `Model/server.py` `/translate/text` endpoint
    - Import `_translate_single` from `document_translator_v3` alongside the existing `run_pipeline` import
    - Replace the temp-file creation, `run_pipeline()` call, and `shutil.rmtree` with a direct call to `_translate_single(req.text.strip(), src_code, tgt_code)`
    - Add empty/whitespace guard: return HTTP 400 `{"detail": "Text must not be empty."}` when `not req.text or not req.text.strip()`
    - Wrap the `_translate_single` call in try/except and re-raise as `HTTPException(500, str(e))`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property test for short text inputs always translate successfully
    - **Property 1: Short text inputs always translate successfully**
    - **Validates: Requirements 1.2, 1.3**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Use `@given` with `st.lists` of 1–2 word strings joined by space; assert result is a non-empty string

  - [ ]* 1.3 Write property test for whitespace-only inputs are always rejected
    - **Property 2: Whitespace-only inputs are always rejected**
    - **Validates: Requirements 1.4**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Use `@given(st.text(alphabet=" \t\n\r", min_size=1))`; assert `not text.strip()` (validates the guard condition)

  - [ ]* 1.4 Write property test for normal text inputs always translate successfully
    - **Property 3: Normal text inputs always translate successfully**
    - **Validates: Requirements 1.5**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Use `@given` with `st.lists` of 3–20 word strings; assert result is a non-empty string

  - [ ]* 1.5 Write unit tests for `/translate/text` endpoint
    - Mock `_translate_single` to return a fixed string; verify HTTP 200 + `{"translated": ...}` for 1-word and 2-word inputs
    - Verify HTTP 400 for empty string and whitespace-only strings
    - Mock `_translate_single` to raise `RuntimeError`; verify HTTP 500 with exception message in `detail`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 2. Checkpoint — Ensure all Bug 1 tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Fix Bug 2 — Add `pdf_column_mode` parameter to document translation
  - [x] 3.1 Update `Model/server.py` `/translate/document` endpoint
    - Add `VALID_PDF_COLUMN_MODES = {"auto", "single", "left", "right"}` constant
    - Add `pdf_column_mode: str = Form("auto")` parameter to the endpoint signature
    - Add validation: return HTTP 400 with descriptive message if `pdf_column_mode not in VALID_PDF_COLUMN_MODES`
    - Forward `pdf_column_mode=pdf_column_mode` to the `run_pipeline()` call
    - Wrap the entire handler body in try/except: re-raise `HTTPException` as-is, catch all other exceptions as `HTTPException(500, str(e))` with `shutil.rmtree` cleanup
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 3.2 Write property test for invalid `pdf_column_mode` values are always rejected
    - **Property 4: Invalid `pdf_column_mode` values are always rejected**
    - **Validates: Requirements 2.3**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Use `@given(st.text(min_size=1).filter(lambda s: s not in VALID_MODES))`; assert value is not in the valid set

  - [ ]* 3.3 Write unit tests for `/translate/document` `pdf_column_mode` handling
    - Verify HTTP 400 for each invalid `pdf_column_mode` value
    - Mock `run_pipeline`; verify it is called with the correct `pdf_column_mode` for each valid value
    - Verify default `pdf_column_mode="auto"` is used when the field is omitted
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Update `app/Services/TranslationService.php` `translateDocument()`
    - Add `string $pdfColumnMode = 'auto'` parameter to the method signature
    - Include `'pdf_column_mode' => $pdfColumnMode` in the `CURLOPT_POSTFIELDS` array passed to cURL
    - _Requirements: 2.8_

  - [x] 3.5 Update `app/Http/Controllers/TranslationController.php` `translate()`
    - Add `'pdf_column_mode' => ['nullable', Rule::in(['auto', 'single', 'left', 'right'])]` to the validation rules
    - Extract `$pdfColumnMode = $request->input('pdf_column_mode', 'auto')`
    - Pass `$pdfColumnMode` as the fourth argument to `$this->service->translateDocument()`
    - _Requirements: 2.2, 2.3, 2.8_

  - [ ]* 3.6 Write PHPUnit tests for `TranslationService` and `TranslationController`
    - Test `translateDocument()` with a mock cURL; verify `pdf_column_mode` appears in `CURLOPT_POSTFIELDS`
    - Test `translate()` with a mock service; verify `pdf_column_mode` is extracted from the request and forwarded
    - Test Laravel validation rejects invalid `pdf_column_mode` values with HTTP 422
    - _Requirements: 2.2, 2.3, 2.8_

- [x] 4. Checkpoint — Ensure all Bug 2 backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Fix Bug 2 (frontend) — Add PDF column mode selector to Blade view
  - [x] 5.1 Add `<select id="pdf-column-mode">` element to `resources/views/translation.blade.php`
    - Insert the select element with options: Auto (value `"auto"`, default), Single column (`"single"`), Left column only (`"left"`), Right column only (`"right"`)
    - Set `style="display:none"` as the initial state
    - _Requirements: 2.4, 2.5_

  - [x] 5.2 Wire file input change and remove events to show/hide the selector
    - In the `fileInput` `change` event handler, detect if the selected file has a `.pdf` extension; show the selector if true, hide and reset to `"auto"` if false
    - In the `removeFile` click handler, hide the selector and reset its value to `"auto"`
    - _Requirements: 2.4_

  - [x] 5.3 Include `pdf_column_mode` in `FormData` for document translation fetch
    - When building `FormData` for the document translation request, check if the file extension is `.pdf`; if so, append `formData.append('pdf_column_mode', pdfColumnMode.value)`
    - Do not append the field for non-PDF files
    - _Requirements: 2.6, 2.7_

- [x] 6. Fix Bug 3 — Robust frontend error handling for non-JSON responses
  - [x] 6.1 Refactor document translation fetch chain in `resources/views/translation.blade.php`
    - Replace `response.json()` with `response.text()` in the first `.then()`
    - In the chained `.then(rawText => ...)`, attempt `JSON.parse(rawText)` inside a try/catch; set `data = null` on parse failure
    - Handle non-2xx: if `data && (data.error || data.detail)` → show that message; else show `'Error (' + response.status + '). Please try again.'`
    - Keep the `.catch()` handler showing `'Network error. Please try again.'`
    - _Requirements: 3.1, 3.2, 3.4_

  - [x] 6.2 Refactor text translation fetch chain in `resources/views/translation.blade.php`
    - Apply the same `response.text()` → `JSON.parse` → fallback pattern to the text translation fetch
    - Ensure non-2xx + non-JSON responses show `'Error (' + response.status + '). Please try again.'`
    - _Requirements: 3.3, 3.4_

  - [ ]* 6.3 Write property test for non-JSON error bodies produce status-code-bearing fallback
    - **Property 6: Non-JSON error bodies always produce a status-code-bearing fallback message**
    - **Validates: Requirements 3.2, 3.3**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Extract the fallback-message-building logic into a pure helper function `build_fallback_error_message(status_code, raw_text)`
    - Use `@given(st.integers(min_value=400, max_value=599), st.text().filter(lambda s: _is_not_json(s)))`; assert `str(status_code) in message`

  - [ ]* 6.4 Write property test for all error responses from Translation_Service are valid JSON
    - **Property 5: All error responses from the Translation_Service are valid JSON**
    - **Validates: Requirements 3.5, 3.6**
    - Add to `Model/tests/test_translation_fixes_properties.py`
    - Use `TestClient`; generate bad inputs (empty text, unknown language names) via `@given`; assert response body is valid JSON with `detail` or `error` field

  - [ ]* 6.5 Write unit tests for error response JSON consistency
    - Verify all error paths in `/translate/text` and `/translate/document` return JSON bodies with a `detail` field
    - _Requirements: 3.5, 3.6_

- [x] 7. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Properties 1 and 3 involve actual NLLB model inference and are slow; run with `@settings(max_examples=10)` in CI and full 100 iterations locally
- Properties 2, 4, 5, and 6 are fast (no model calls) and can run at full 100 iterations in CI
- All property tests go in `Model/tests/test_translation_fixes_properties.py`
- PHP unit tests go in the existing Laravel test suite under `tests/Unit/`
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between the three bug fixes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["3.5", "5.1"] },
    { "id": 4, "tasks": ["3.6", "5.2"] },
    { "id": 5, "tasks": ["5.3", "6.1"] },
    { "id": 6, "tasks": ["6.2"] },
    { "id": 7, "tasks": ["6.3", "6.4", "6.5"] }
  ]
}
```
