# Implementation Plan: New Translation Page

## Overview

Implement the `/translate` route end-to-end: a `TranslationException` class, a `TranslationService` that shells out to the Python NLLB-200 backend via `proc_open`, a `TranslationController` that validates requests and returns JSON or streamed downloads, a two-panel Blade view with inline vanilla JS, per-view CSS, Vite config update, sidebar nav link, PHPUnit unit + feature tests, eris property-based tests, and Playwright frontend tests.

---

## Tasks

- [x] 1. Install eris and set up the `storage/app/temp` directory
  - Run `composer require --dev giorgiosironi/eris:^0.12` to add the eris property-based testing library
  - Create `storage/app/temp/.gitkeep` so the temp directory is tracked by git but its contents are ignored
  - Add `storage/app/temp/*` (excluding `.gitkeep`) to `.gitignore`
  - _Requirements: 7.9_

- [x] 2. Create `TranslationException` and `TranslationService` skeleton
  - [x] 2.1 Create `app/Exceptions/TranslationException.php`
    - Thin subclass of `RuntimeException` with no additional methods
    - _Requirements: 7.5_

  - [x] 2.2 Create `app/Services/TranslationService.php` with `LANGUAGE_MAP`, `EXTENSION_MAP`, `TIMEOUT_SECONDS` constants and method stubs for `translateText()` and `translateDocument()`
    - Define `LANGUAGE_MAP`: `['English' => 'eng_Latn', 'Cebuano' => 'ceb_Latn', 'Filipino' => 'tgl_Latn']`
    - Define `EXTENSION_MAP`: `['.docx'=>'.docx', '.pdf'=>'.pdf', '.txt'=>'.txt', '.md'=>'.md', '.csv'=>'.csv', '.rtf'=>'.docx', '.odt'=>'.docx']`
    - Define `TIMEOUT_SECONDS = 60`
    - Stubs throw `\LogicException('not implemented')` so the class is autoloadable
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 3. Implement `TranslationService::translateText()`
  - [x] 3.1 Implement the full `translateText(string $text, string $sourceLang, string $targetLang): string` method
    - Write `$text` to `storage/app/temp/{uuid}.txt` using `Storage::disk('local')`
    - Determine output path `storage/app/temp/{uuid}_out.txt`
    - Build the Python one-liner command using `LANGUAGE_MAP` codes (pass human-readable names to the script, which maps them internally)
    - Open the process with `proc_open`, set `stream_set_timeout` to `TIMEOUT_SECONDS` on all pipes
    - Read stdout/stderr; if `proc_get_status()['exitcode'] !== 0` throw `TranslationException($stderr)`
    - If stream timed out, kill the process and throw `TranslationException('Translation timed out after 60 seconds.')`
    - Read output file content and return as string
    - Register both temp file paths with `register_shutdown_function` for deletion
    - _Requirements: 7.3, 7.5, 5.9_

  - [ ]* 3.2 Write PHPUnit unit tests for `translateText` in `tests/Unit/TranslationServiceTest.php`
    - `test_translate_text_returns_translated_string` — mock subprocess (override command), verify return value
    - `test_translate_text_throws_on_nonzero_exit` — mock subprocess with exit code 1, verify `TranslationException` thrown
    - `test_language_map_returns_correct_nllb_codes` — verify all three `LANGUAGE_MAP` entries via reflection or a public accessor
    - _Requirements: 7.2, 7.3, 7.5_

- [x] 4. Implement `TranslationService::translateDocument()`
  - [x] 4.1 Implement the full `translateDocument(UploadedFile $file, string $sourceLang, string $targetLang): string` method
    - Store uploaded file to `storage/app/temp/{uuid}{ext}` using `$file->storeAs('temp', ...)`
    - Determine output extension via `EXTENSION_MAP` (`.rtf` → `.docx`, `.odt` → `.docx`, others unchanged)
    - Determine output path `storage/app/temp/{uuid}_translated{out_ext}`
    - Build and run the same Python one-liner command as `translateText`
    - Apply the same timeout and exit-code error handling
    - Register both temp file paths with `register_shutdown_function`
    - Return the absolute output file path
    - _Requirements: 7.4, 7.5, 7.9_

  - [ ]* 4.2 Write PHPUnit unit tests for `translateDocument` in `tests/Unit/TranslationServiceTest.php`
    - `test_translate_document_returns_output_path` — mock subprocess, verify returned path exists
    - `test_translate_document_maps_rtf_to_docx` — verify `.rtf` input produces `.docx` output path
    - `test_translate_document_maps_odt_to_docx` — verify `.odt` input produces `.docx` output path
    - _Requirements: 7.4_

- [x] 5. Checkpoint — Ensure all tests pass
  - Run `php artisan test --filter TranslationServiceTest` and confirm all unit tests pass. Ask the user if any questions arise.

- [x] 6. Create `TranslationController` and register routes
  - [x] 6.1 Add routes to `routes/web.php` inside the existing `auth` + `throttle:60,1` middleware group
    - `Route::get('/translate', [TranslationController::class, 'show'])->name('translate');`
    - `Route::post('/translate', [TranslationController::class, 'translate'])->name('translate.submit');`
    - Add `use App\Http\Controllers\TranslationController;` import
    - _Requirements: 8.1_

  - [x] 6.2 Create `app/Http/Controllers/TranslationController.php`
    - Constructor injects `TranslationService $service`
    - `show(): View` — returns `view('translation')`
    - `translate(Request $request): JsonResponse|StreamedResponse` — full implementation:
      - Validate `source_lang` and `target_lang` (required, in:English,Cebuano,Filipino, different from each other using a custom `Rule::notIn` or `after` validation)
      - Validate `text` (required_without:document, string, max:8000) OR `document` (required_without:text, file, mimes:docx,pdf,txt,md,rtf,odt,csv, max:10240)
      - For text mode: call `$this->service->translateText(...)`, return `response()->json(['translated' => $result])`
      - For document mode: call `$this->service->translateDocument(...)`, return `response()->streamDownload(...)` with `register_shutdown_function` to delete the output file
      - Catch `TranslationException`: return `response()->json(['error' => $e->getMessage()], 500)` or 504 for timeout
    - _Requirements: 1.1, 1.2, 5.1–5.9, 7.6, 7.7, 7.8, 7.9_

  - [ ]* 6.3 Write PHPUnit feature tests in `tests/Feature/TranslationControllerTest.php`
    - `test_show_requires_authentication` — GET /translate without auth → 302 to /login
    - `test_show_returns_translation_view` — GET /translate as auth user → 200, view is `translation`
    - `test_translate_rejects_same_language` — POST source_lang == target_lang → 422
    - `test_translate_rejects_empty_text` — POST with empty text → 422
    - `test_translate_rejects_text_over_8000_chars` — POST with 8001-char text → 422
    - `test_translate_rejects_unsupported_file_extension` — POST with `.xyz` file → 422
    - `test_translate_rejects_file_over_10mb` — POST with oversized file → 422
    - `test_translate_text_returns_json` — mock `TranslationService`, POST valid text → 200 JSON with `translated` key
    - `test_translate_document_returns_download` — mock `TranslationService`, POST valid file → streamed response
    - `test_translate_returns_error_on_translation_exception` — mock service throws `TranslationException` → 500 JSON with `error` key
    - _Requirements: 1.1, 1.2, 5.5, 7.6, 7.7, 7.8_

- [ ] 7. Write eris property-based tests
  - [ ]* 7.1 Create `tests/Feature/TranslationControllerPropertyTest.php` — Property 3: same-language POST always rejected
    - Tag: `// Feature: new-translation-page, Property 3: Same-language POST is rejected by the controller`
    - Use `$this->forAll(Generator\elements('English', 'Cebuano', 'Filipino'))` to generate a random language L
    - POST `/translate` with `source_lang == target_lang == L` as an authenticated user
    - Assert 422 response every time (minimum 100 iterations)
    - _Requirements: 2.7, 7.6_

  - [ ]* 7.2 Create `tests/Unit/TranslationServicePropertyTest.php` — Property 9: language name maps to NLLB code
    - Tag: `// Feature: new-translation-page, Property 9: Language name maps to correct NLLB code`
    - Use `$this->forAll(Generator\elements('English', 'Cebuano', 'Filipino'))` to generate a language name
    - Assert the `LANGUAGE_MAP` constant returns `eng_Latn`, `ceb_Latn`, or `tgl_Latn` respectively
    - _Requirements: 7.2_

  - [ ]* 7.3 Add to `TranslationServicePropertyTest` — Property 10: non-zero exit throws `TranslationException` with stderr
    - Tag: `// Feature: new-translation-page, Property 10: Non-zero exit code throws TranslationException with stderr`
    - Use `$this->forAll(Generator\string(), Generator\choose(1, 255))` to generate random stderr and exit code
    - Mock the subprocess to return that exit code and stderr
    - Assert `TranslationException` is thrown and `$e->getMessage() === $stderr`
    - _Requirements: 7.5_

  - [ ]* 7.4 Add to `TranslationServicePropertyTest` — Property 11: output extension follows mapping
    - Tag: `// Feature: new-translation-page, Property 11: Output file extension follows the defined mapping`
    - Use `$this->forAll(Generator\elements('.docx','.pdf','.txt','.md','.csv','.rtf','.odt'))` to generate an input extension
    - Assert the output extension matches `EXTENSION_MAP` (`.rtf`→`.docx`, `.odt`→`.docx`, others unchanged)
    - _Requirements: 7.4_

  - [ ]* 7.5 Add to `TranslationControllerPropertyTest` — Property 12: text length validation
    - Tag: `// Feature: new-translation-page, Property 12: Controller rejects text outside valid length range`
    - Generate text of length 0 OR length > 8000 (use `Generator\bind` or two separate `forAll` calls)
    - POST to `/translate` as authenticated user; assert 422 every time
    - _Requirements: 7.7_

  - [ ]* 7.6 Add to `TranslationControllerPropertyTest` — Property 13: invalid file rejected
    - Tag: `// Feature: new-translation-page, Property 13: Controller rejects invalid file uploads`
    - Generate a random unsupported extension (e.g. `.xyz`, `.exe`, `.png`) using `Generator\elements`
    - Create a fake `UploadedFile` with that extension; POST to `/translate`; assert 422 every time
    - _Requirements: 7.8_

  - [ ]* 7.7 Add to `TranslationServicePropertyTest` — Property 14: temp files deleted after translation
    - Tag: `// Feature: new-translation-page, Property 14: Temp files are deleted after response`
    - Generate random text and a random valid language pair
    - Run `translateText` with a mocked subprocess that writes a dummy output file
    - Trigger the registered shutdown functions manually
    - Assert neither the input nor the output temp file exists in `storage/app/temp`
    - _Requirements: 7.9_

- [x] 8. Checkpoint — Ensure all tests pass
  - Run `php artisan test --filter "TranslationController|TranslationService"` and confirm all unit, feature, and property tests pass. Ask the user if any questions arise.

- [x] 9. Create the Blade view `resources/views/translation.blade.php`
  - [x] 9.1 Create the Blade view skeleton extending `layouts/app.blade.php`
    - `@section('title', 'New Translation')`
    - `@section('styles')` — `@vite('resources/css/views/translation.css')`
    - `@section('content')` — outer `.translation-layout` wrapper div
    - Add `<meta name="csrf-token">` is already in the layout; confirm it is accessible via `document.querySelector('meta[name="csrf-token"]').content`
    - _Requirements: 1.3, 1.5, 1.8_

  - [x] 9.2 Build the Source Panel HTML inside `.translation-layout`
    - `.translation-panel.translation-panel--source` containing:
      - `.translation-panel__header` with `<select id="source-lang">` (options: English, Cebuano, Filipino; default English), `.translation-swap` button with swap icon and `aria-label="Swap languages"`, `<select id="target-lang">` (default Cebuano)
      - `.translation-panel__body` with `<textarea id="source-text" maxlength="8000">`, `.translation-panel__file-info` (hidden) containing `<span id="file-name">` and `<button id="remove-file">`, `.translation-panel__footer` with `<button id="attach-btn">`, `<input id="file-input" type="file" hidden accept=".docx,.pdf,.txt,.md,.rtf,.odt,.csv">`, `<span id="char-counter">0/8000</span>`
      - `.translation-panel__error` (empty, hidden by default)
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 4.1, 4.2_

  - [x] 9.3 Build the Output Panel HTML and Translate button
    - `.translation-panel.translation-panel--output` containing:
      - `.translation-panel__header` with static label "Translation"
      - `.translation-panel__body` with `<div id="output-text">` and `<div id="output-download" hidden>` containing `<a id="download-link">`
      - `.translation-panel__footer` with `<button id="copy-btn" aria-disabled="true">Copy</button>` and `<button id="save-btn" aria-disabled="true">Save</button>`
      - `.translation-panel__error` (empty, hidden by default)
    - `.translation-actions` div with `<button id="translate-btn" class="btn primary">Translate</button>`
    - _Requirements: 5.1, 5.6, 5.7, 6.1, 6.4, 6.5_

- [x] 10. Create `resources/css/views/translation.css`
  - Write all styles using only CSS custom properties from `base.css` (`--bg`, `--card-bg`, `--text`, `--muted`, `--primary`, `--accent`, `--border`, `--radius`)
  - `.translation-layout`: `display: flex; gap: 24px; align-items: flex-start`
  - `.translation-panel`: `flex: 1; min-width: 280px; background: var(--card-bg); border-radius: var(--radius); padding: 0`
  - `.translation-panel__header`: flex row, gap, padding, border-bottom
  - `.translation-panel__body textarea`: `width: 100%; resize: none; min-height: 240px; border: none; background: transparent; color: var(--text); padding: 16px; box-sizing: border-box`
  - `.translation-panel__footer`: flex row, padding, border-top, align-items center
  - `#char-counter`: `font-size: 0.8rem; color: var(--muted); margin-left: auto`
  - `.counter-warning`: `color: var(--accent)`
  - `select` inside `.translation-panel__header`: styled to match existing form inputs
  - `.translation-swap`: icon button, no background, cursor pointer
  - `.translation-actions`: `display: flex; justify-content: center; margin-top: 16px`
  - `button[aria-disabled="true"]`: `opacity: 0.5; pointer-events: none`
  - `@media (max-width: 768px)`: `.translation-layout { flex-direction: column }`
  - _Requirements: 1.4, 1.5, 1.6, 1.7, 6.5_

- [x] 11. Update Vite config and sidebar nav link
  - [x] 11.1 Add `'resources/css/views/translation.css'` to the `input` array in `vite.config.js`
    - Insert after `'resources/css/views/settings.css'`
    - _Requirements: 1.5_

  - [x] 11.2 Update the "New Translation" `<a>` in `resources/views/layouts/app.blade.php`
    - Change `href="#"` to `href="{{ route('translate') }}"`
    - Add `{{ request()->routeIs('translate') ? 'active' : '' }}` to the class attribute, consistent with the dashboard and settings links
    - _Requirements: 8.2, 8.3_

- [x] 12. Implement inline JavaScript in `translation.blade.php`
  - [x] 12.1 Implement the character counter and paste-truncation logic
    - On `input` event of `#source-text`: update `#char-counter` text to `${len}/8000`; toggle `.counter-warning` class when `len > 7500`
    - On `paste` event: truncate pasted content so total length ≤ 8000 using `e.preventDefault()` + manual insertion
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 12.2 Implement the swap button logic
    - On click of `.translation-swap`: read both select values; if equal, show inline error in `.translation-panel__error` and return; otherwise swap values, clear `#output-text`, clear output error
    - In text mode: keep textarea content as-is (language swapped, text stays)
    - In file mode: swap only the selectors, do not remove the attached file
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x] 12.3 Implement file attachment, validation, and removal
    - `#attach-btn` click → trigger `#file-input` click
    - `#file-input` change: validate extension against `['.docx','.pdf','.txt','.md','.rtf','.odt','.csv']` and size ≤ 10485760; on failure show inline error and reset input; on success show `#file-name`, hide `#source-text` and `#char-counter`, show `.translation-panel__file-info`
    - `#remove-file` click: clear `#file-input`, hide `.translation-panel__file-info`, show `#source-text` and `#char-counter`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 12.4 Implement the AJAX text translation submit flow
    - `#translate-btn` click (text mode): disable button, show loading indicator
    - Build `FormData` with `source_lang`, `target_lang`, `text`, and CSRF token
    - `fetch('/translate', { method: 'POST', headers: { 'X-CSRF-TOKEN': ..., 'Accept': 'application/json' }, body: formData })`
    - On 200: populate `#output-text`, enable `#copy-btn` and `#save-btn` (remove `aria-disabled`)
    - On 422: read `response.errors`, display first error message in source panel's `.translation-panel__error`
    - On 500/504: display `response.error` in output panel's `.translation-panel__error`
    - Always: re-enable `#translate-btn`, remove loading indicator
    - _Requirements: 5.2, 5.4, 5.6, 5.8, 5.9_

  - [x] 12.5 Implement the document translation submit flow
    - When a file is attached, `#translate-btn` click: disable button, show loading indicator
    - Submit a standard `<form>` POST (not AJAX) with `multipart/form-data` containing `source_lang`, `target_lang`, `document`, and `_token`
    - On success the browser receives a streamed download; show `#output-download` with `#download-link` pointing to the response
    - On error (422/500): display error in the appropriate panel's `.translation-panel__error`
    - _Requirements: 5.3, 5.4, 5.7, 5.8_

  - [x] 12.6 Implement copy and save button actions
    - `#copy-btn` click: call `navigator.clipboard.writeText(outputText)`; on success change label to "Copied!" and revert after 2000 ms; on failure show inline error in output panel's `.translation-panel__error`
    - `#save-btn` click: build UTC timestamp string `YYYYMMDD_HHMMSS`; create a `Blob` from `#output-text` content; trigger download as `translation_{timestamp}.txt` via a temporary `<a>` element
    - Both buttons must have `aria-disabled="true"` and `pointer-events: none` when `#output-text` is empty
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 13. Checkpoint — Ensure all tests pass
  - Run `php artisan test` and confirm the full test suite passes. Ask the user if any questions arise.

- [ ] 14. Write Playwright frontend tests
  - [ ]* 14.1 Create `tests/e2e/translation.spec.js` (or `.ts`) with Playwright tests
    - Install Playwright if not present: `npm install --save-dev @playwright/test` and `npx playwright install`
    - Test: swap button exchanges select values and clears output
    - Test: character counter updates on input and shows `counter-warning` class above 7500 chars
    - Test: paste truncation caps textarea at 8000 characters
    - Test: unsupported file extension shows inline error without submitting
    - Test: oversized file shows inline error without submitting
    - Test: copy button label changes to "Copied!" then reverts
    - Test: save button downloads a file matching `translation_YYYYMMDD_HHMMSS.txt`
    - _Requirements: 2.3, 2.4, 3.2, 3.4, 3.6, 4.5, 4.6, 6.2, 6.4_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Run `php artisan test` (PHPUnit + eris) and `npx playwright test` (Playwright). Confirm all suites pass. Ask the user if any questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical boundaries
- Property tests (eris) validate universal correctness properties across random inputs (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- The Python backend is invoked via a one-liner `python -c "..."` wrapper because `document_translator_v3.py` is a Colab notebook without a CLI entry point
- Temp files in `storage/app/temp` are cleaned up via `register_shutdown_function` — this runs even on fatal PHP errors
- Document translation uses a full-page form POST (not AJAX) because browsers cannot trigger a file download from a `fetch` response without extra complexity
- eris requires PHP 8.x and PHPUnit 10+; confirm compatibility with `phpunit/phpunit ^11.5` already in `composer.json`

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2"] },
    { "id": 1, "tasks": ["3.1", "4.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "6.1", "6.2"] },
    { "id": 3, "tasks": ["6.3", "7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7"] },
    { "id": 4, "tasks": ["9.1", "11.1", "11.2"] },
    { "id": 5, "tasks": ["9.2", "9.3", "10"] },
    { "id": 6, "tasks": ["12.1", "12.2", "12.3"] },
    { "id": 7, "tasks": ["12.4", "12.5"] },
    { "id": 8, "tasks": ["12.6"] },
    { "id": 9, "tasks": ["14.1"] }
  ]
}
```
