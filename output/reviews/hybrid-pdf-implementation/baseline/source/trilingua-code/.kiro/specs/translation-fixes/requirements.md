# Requirements Document

## Introduction

This spec covers three bug fixes for the Trilingua translation application — a Laravel + Python FastAPI system that translates text and documents between English, Cebuano, and Filipino using the NLLB-200 model.

**Bug 1 — Text translation fails for short inputs:** The `/translate/text` endpoint routes plain-text input through `run_pipeline()`, which applies a document-level word-count filter (`len(words) >= 3`). Short inputs such as "jeje bading" (2 words) are filtered to zero blocks, raising a `ValueError` that propagates as HTTP 500 and surfaces in the UI as "An unexpected error occurred."

**Bug 2 — Document translation quality degraded for bilingual PDFs:** The `read_pdf()` function with `column_mode="auto"` picks up both columns of a bilingual PDF (source language on the left, partial translation on the right) and translates all of it, including already-translated content. The `detect_columns()` fallback collapses everything to single-column when any column has fewer than 2 blocks, causing overlapping and repeated text in the PDF output.

**Bug 3 — Frontend error handling breaks on non-JSON error responses:** The document translation fetch call in the frontend calls `response.json()` unconditionally. When the Python server returns a plain-text or non-JSON error body (e.g., a FastAPI 500 with a string detail), the `.json()` parse throws and the `.catch()` handler shows "Network error." instead of the actual error message.

---

## Glossary

- **Translation_Service**: The Python FastAPI microservice (`Model/server.py`) that loads the NLLB-200 model and exposes HTTP endpoints for text and document translation.
- **Pipeline**: The `run_pipeline()` function in `document_translator_v3.py` that reads a document file, filters blocks, translates them, and writes the output file.
- **_translate_single**: The low-level function in `document_translator_v3.py` that translates a single string directly through the NLLB-200 model, bypassing all document-level filtering.
- **Word_Count_Filter**: The `len(p.split()) >= 3` guard applied inside `read_txt()`, `read_docx()`, `read_rtf()`, and `read_odt()` that discards blocks with fewer than 3 words.
- **PDF_Column_Mode**: A parameter accepted by `read_pdf()` and `run_pipeline()` controlling how columns are detected: `"auto"`, `"single"`, `"left"`, or `"right"`.
- **Laravel_Controller**: `TranslationController` in `app/Http/Controllers/TranslationController.php`, which handles `POST /translate` and `GET /translate/download/{token}`.
- **Laravel_Service**: `TranslationService` in `app/Services/TranslationService.php`, which calls the Translation_Service over HTTP.
- **Frontend**: The Blade view at `resources/views/translation.blade.php` containing the JavaScript translation UI.
- **Download_Token**: A UUID-based filename used as a session key to allow the user to download a translated document without exposing the real file path.

---

## Requirements

### Requirement 1: Text Translation Bypasses Document-Level Word-Count Filter

**User Story:** As a user, I want to translate short phrases and sentences, so that I can get translations for any amount of text regardless of word count.

#### Acceptance Criteria

1. WHEN the `/translate/text` endpoint receives a request with a non-empty text string, THE Translation_Service SHALL call `_translate_single()` directly instead of routing through `run_pipeline()`.
2. WHEN the text input contains fewer than 3 words, THE Translation_Service SHALL translate it and return a valid `{"translated": "..."}` JSON response with HTTP 200.
3. WHEN the text input is a single word, THE Translation_Service SHALL translate it and return a valid `{"translated": "..."}` JSON response with HTTP 200.
4. WHEN the text input is empty or whitespace-only, THE Translation_Service SHALL return HTTP 400 with a descriptive error message.
5. WHEN the text input contains 3 or more words, THE Translation_Service SHALL translate it and return a valid `{"translated": "..."}` JSON response with HTTP 200, preserving existing behavior.
6. IF `_translate_single()` raises an exception, THEN THE Translation_Service SHALL return HTTP 500 with the exception message as the error detail.

---

### Requirement 2: PDF Column Mode Selection for Document Translation

**User Story:** As a user translating a bilingual PDF, I want to choose which column to translate, so that I can avoid re-translating already-translated content and get clean output.

#### Acceptance Criteria

1. WHEN a document translation request is submitted, THE Translation_Service `/translate/document` endpoint SHALL accept an optional `pdf_column_mode` form field with a default value of `"auto"`.
2. WHEN `pdf_column_mode` is provided, THE Translation_Service SHALL pass it through to `run_pipeline()` as the `pdf_column_mode` argument.
3. IF `pdf_column_mode` is provided with a value other than `"auto"`, `"single"`, `"left"`, or `"right"`, THEN THE Translation_Service SHALL return HTTP 400 with a descriptive error message.
4. WHEN a PDF file is attached in the Frontend, THE Frontend SHALL display a PDF column mode selector control that is not visible when no file is attached or when a non-PDF file is attached.
5. WHEN the PDF column mode selector is displayed, THE Frontend SHALL offer the following options: Auto (default), Left column only, Right column only, Single column.
6. WHEN the user submits a document translation with a PDF file, THE Frontend SHALL include the selected `pdf_column_mode` value in the `FormData` sent to `POST /translate`.
7. WHEN a non-PDF document is submitted, THE Frontend SHALL NOT include the `pdf_column_mode` field in the `FormData`, and THE Translation_Service SHALL ignore it.
8. WHEN the Laravel_Service calls the Translation_Service for document translation, THE Laravel_Service SHALL forward the `pdf_column_mode` value received from the Frontend as a form field in the cURL request.

---

### Requirement 3: Robust Frontend Error Handling for Non-JSON Error Responses

**User Story:** As a user, I want to see a meaningful error message when translation fails, so that I understand what went wrong instead of seeing a generic "Network error."

#### Acceptance Criteria

1. WHEN the document translation fetch response has a non-2xx status code and the response body is valid JSON, THE Frontend SHALL display the `error` or `detail` field from the JSON body in the output panel error area.
2. WHEN the document translation fetch response has a non-2xx status code and the response body is not valid JSON, THE Frontend SHALL display a fallback error message that includes the HTTP status code in the output panel error area.
3. WHEN the text translation fetch response has a non-2xx status code and the response body is not valid JSON, THE Frontend SHALL display a fallback error message that includes the HTTP status code in the output panel error area.
4. WHEN the fetch call itself fails due to a network error (e.g., the server is unreachable), THE Frontend SHALL display "Network error. Please try again." in the output panel error area.
5. WHEN the Translation_Service returns an error response, THE Translation_Service SHALL always return a JSON body with an `error` or `detail` field so that the Frontend can parse it consistently.
6. IF the Translation_Service raises an unhandled exception in the `/translate/document` endpoint, THEN THE Translation_Service SHALL return HTTP 500 with a JSON body `{"detail": "<error message>"}` rather than a plain-text response.
