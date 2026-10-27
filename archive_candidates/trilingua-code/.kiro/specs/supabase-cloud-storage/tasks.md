# Implementation Plan: Supabase Cloud Storage

## Overview

Integrate Supabase Storage and Supabase Database (PostgREST) into the Trilingua Laravel 12 application. The implementation proceeds in layers: configuration and service provider first, then the two new service classes, then the modified controller, then the new History controller and view, and finally wiring and frontend changes.

## Tasks

- [x] 1. Add Supabase configuration and boot-time validation
  - [x] 1.1 Add `supabase` key to `config/services.php` reading from `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_BUCKET`
    - Add the four env-backed keys under `'supabase'` in `config/services.php`
    - _Requirements: 6.1_
  - [x] 1.2 Create `app/Providers/SupabaseServiceProvider.php` with boot-time validation
    - Iterate over the four required env vars; throw `RuntimeException` naming any missing variable
    - Register the provider in `app/Providers/AppServiceProvider.php` (or `bootstrap/providers.php` for Laravel 12)
    - _Requirements: 6.2_
  - [x] 1.3 Add placeholder values for all four Supabase variables to `.env.example`
    - _Requirements: 6.3_
  - [ ]* 1.4 Write property test for missing env var throws RuntimeException
    - **Property 9: Missing Env Var Throws RuntimeException**
    - **Validates: Requirements 6.2**
    - Use `eris` `subset` generator over the four variable names; assert `RuntimeException` is thrown and message names the missing variable
    - Tag: `Feature: supabase-cloud-storage, Property 9: Missing env var throws RuntimeException`

- [x] 2. Implement `StorageService`
  - [x] 2.1 Create `app/Services/StorageService.php` with `uploadFile()` method
    - Inject `GuzzleHttp\Client`; define `SIGNED_URL_EXPIRY_SECONDS = 604800`
    - POST raw file bytes to `/storage/v1/object/{bucket}/{storagePath}` with `Authorization: Bearer {service_role_key}`
    - On non-2xx response throw `RuntimeException("Supabase Storage upload failed: {body}")`
    - After successful upload call the sign endpoint (see 2.2) and return `{ storage_path, signed_url, signed_url_expires_at }`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 2.2 Add `generateSignedUrl()` method to `StorageService`
    - POST `{ "expiresIn": 604800 }` to `/storage/v1/object/sign/{bucket}/{storagePath}`
    - Construct full URL as `{SUPABASE_URL}/storage/v1{signedURL}`
    - Set `signed_url_expires_at` to `now() + 604800` seconds (ISO 8601 UTC)
    - On non-2xx throw `RuntimeException("Supabase signed URL generation failed: {body}")`; distinguish file-not-found (400/404) with a "not found" marker in the message
    - _Requirements: 1.2, 1.3, 1.5, 5.1_
  - [ ]* 2.3 Write property test for storage path format
    - **Property 1: Storage Path Format**
    - **Validates: Requirements 1.1**
    - Use `eris` `string()` generators for session_id, uuid, and `elements(['.docx','.pdf','.txt','.md'])` for ext; assert path matches `{session_id}/{uuid}_translated.{ext}`
    - Tag: `Feature: supabase-cloud-storage, Property 1: Storage path format`
  - [ ]* 2.4 Write property test for signed URL expiry invariant
    - **Property 2: Signed URL Expiry Invariant**
    - **Validates: Requirements 1.2, 5.1**
    - Use `eris` `date()` / `integer()` generators for base timestamp; assert `signed_url_expires_at` equals base timestamp + 604800 seconds
    - Tag: `Feature: supabase-cloud-storage, Property 2: Signed URL expiry invariant`
  - [ ]* 2.5 Write property test for upload failure propagates as exception
    - **Property 3: Upload Failure Propagates as Exception**
    - **Validates: Requirements 1.4**
    - Use `eris` `elements([400,401,403,404,500,502,503])` generator for HTTP status; mock Guzzle to return that status; assert `RuntimeException` is thrown containing the response body
    - Tag: `Feature: supabase-cloud-storage, Property 3: Upload failure propagates as exception`
  - [ ]* 2.6 Write unit tests for `StorageService`
    - Test successful `uploadFile()` returns correct array shape (`storage_path`, `signed_url`, `signed_url_expires_at`)
    - Test `generateSignedUrl()` success path
    - Test Guzzle `ConnectException` is caught and re-thrown as `RuntimeException`
    - _Requirements: 1.3, 1.4, 1.5_

- [x] 3. Implement `HistoryService`
  - [x] 3.1 Create `app/Services/HistoryService.php` with `insertRecord()` method
    - Inject `GuzzleHttp\Client`
    - POST to `/rest/v1/translation_history` with anon key headers and `Prefer: return=minimal`
    - Payload must include all eight columns: `session_id`, `original_filename`, `translated_filename`, `source_language`, `target_language`, `created_at`, `storage_path`, `signed_url_expires_at`
    - On non-2xx throw `RuntimeException("Supabase DB insert failed: {body}")`
    - _Requirements: 2.1, 2.2_
  - [x] 3.2 Add `getHistory()` method to `HistoryService`
    - GET `/rest/v1/translation_history?session_id=eq.{sessionId}&order=created_at.desc&limit=200&select=...`
    - Return decoded JSON array; on non-2xx throw `RuntimeException`
    - _Requirements: 4.1_
  - [x] 3.3 Add `getRecord()` and `updateExpiry()` methods to `HistoryService`
    - `getRecord(int $id)`: GET with `?id=eq.{id}&limit=1`; return first element or null
    - `updateExpiry(int $id, string $newExpiry)`: PATCH `?id=eq.{id}` with `{ "signed_url_expires_at": newExpiry }`; on non-2xx throw `RuntimeException`
    - _Requirements: 5.1, 5.6_
  - [ ]* 3.4 Write property test for history insert payload completeness
    - **Property 6: History Insert Payload Completeness**
    - **Validates: Requirements 2.1**
    - Use `eris` `string()` generators for session_id/filenames and `elements([...])` for languages; assert all eight columns are present and non-null in the payload sent to PostgREST
    - Tag: `Feature: supabase-cloud-storage, Property 6: History insert payload completeness`
  - [ ]* 3.5 Write property test for history ordering and cap
    - **Property 7: History Ordering and Cap**
    - **Validates: Requirements 4.1**
    - Use `eris` `vector(integer(0, 300), historyRecordGen())` generator; mock PostgREST to return the generated set; assert result is ordered by `created_at` descending and contains at most 200 records
    - Tag: `Feature: supabase-cloud-storage, Property 7: History ordering and cap`
  - [ ]* 3.6 Write unit tests for `HistoryService`
    - Test `getRecord()` returns null for a missing ID (empty array response)
    - Test `updateExpiry()` sends the correct PATCH payload and URL
    - _Requirements: 5.4, 5.6_

- [x] 4. Checkpoint — Ensure all service-layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Modify `TranslationController` for document branch
  - [x] 5.1 Inject `StorageService` and `HistoryService` into `TranslationController`
    - Add constructor parameters; update service container bindings if needed
    - _Requirements: 1.1, 2.1_
  - [x] 5.2 Replace local-file download logic with Supabase upload in the document branch
    - After `TranslationService::translateDocument()` returns `$localPath`, build `$storagePath = session()->getId() . '/' . basename($localPath)`
    - Call `StorageService::uploadFile($localPath, $storagePath)` → `$storageResult`
    - Delete `$localPath` with `@unlink($localPath)` (remove `register_shutdown_function` cleanup)
    - Wrap `HistoryService::insertRecord(...)` in try/catch; log failure via `Log::error()` but do not re-throw
    - Return JSON `{ download_url, download_filename, signed_url_expires_at }` on success
    - Return HTTP 500 `{ "error": "..." }` if `StorageService` throws
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 2.1, 2.3, 3.1, 3.3_
  - [ ]* 5.3 Write property test for translation response shape
    - **Property 4: Translation Response Shape**
    - **Validates: Requirements 3.1**
    - Use `eris` `string()` generators for filenames and `elements(['English','Cebuano','Filipino'])` for languages; mock `StorageService` to return valid data; assert response contains `download_url`, `download_filename`, and `signed_url_expires_at` with non-empty string values
    - Tag: `Feature: supabase-cloud-storage, Property 4: Translation response shape`
  - [ ]* 5.4 Write property test for storage failure returns HTTP 500
    - **Property 5: Storage Failure Returns HTTP 500**
    - **Validates: Requirements 3.3**
    - Use `eris` `string()` generator for exception messages; mock `StorageService::uploadFile()` to throw `RuntimeException`; assert controller returns HTTP 500 with JSON body containing `error` key
    - Tag: `Feature: supabase-cloud-storage, Property 5: Storage failure returns HTTP 500`
  - [ ]* 5.5 Write unit tests for `TranslationController` document branch
    - Test DB insert failure is logged but HTTP 200 with `download_url` is still returned
    - Test that `download_token` route returns 404 for tokens no longer populated by new translations
    - _Requirements: 2.3, 3.1_

- [x] 6. Create `HistoryController` and history routes
  - [x] 6.1 Create `app/Http/Controllers/HistoryController.php` with `index()` method
    - Inject `HistoryService` and `StorageService`
    - `index()`: call `HistoryService::getHistory(session()->getId())`; on exception log and render error view; otherwise render `history.blade.php` with `$records`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [x] 6.2 Add `redownload()` method to `HistoryController`
    - Fetch record via `HistoryService::getRecord($id)`; return 404 if null
    - Return 403 if `$record['session_id'] !== session()->getId()`
    - Call `StorageService::generateSignedUrl($record['storage_path'])`; map "not found" exception to 404, other exceptions to 500
    - Call `HistoryService::updateExpiry($id, $newExpiry)` on success
    - Return JSON `{ download_url }` on success
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_
  - [x] 6.3 Register history routes in `routes/web.php`
    - Add `GET /history` → `HistoryController@index` named `history`
    - Add `POST /history/redownload/{id}` → `HistoryController@redownload` named `history.redownload`
    - Place inside the existing middleware group
    - _Requirements: 4.1, 5.1_
  - [ ]* 6.4 Write property test for session ownership enforcement
    - **Property 8: Session Ownership Enforcement**
    - **Validates: Requirements 5.7**
    - Use `eris` `string()` generators for two distinct session IDs; mock `HistoryService::getRecord()` to return a record with one session ID while the request carries the other; assert HTTP 403 is returned without revealing record or file existence
    - Tag: `Feature: supabase-cloud-storage, Property 8: Session ownership enforcement`
  - [ ]* 6.5 Write unit tests for `HistoryController`
    - Test empty history renders empty-state message "You have no translation history yet."
    - Test DB error renders error view with "Unable to load history. Please try again later."
    - Test re-download returns 404 when file not found in storage
    - Test re-download returns 500 on generic storage error
    - _Requirements: 4.3, 4.4, 5.4, 5.5_

- [x] 7. Create `history.blade.php` view
  - [x] 7.1 Create `resources/views/history.blade.php`
    - Extend `layouts.app`; set title to "Translation History"
    - Render error paragraph when `$error` is set
    - Render empty-state paragraph "You have no translation history yet." when `$records` is empty
    - Render table with columns: Original File, Translated File, From, To, Date (UTC), Action
    - Format `created_at` as `YYYY-MM-DD HH:MM UTC` using `Carbon::parse()->utc()->format('Y-m-d H:i')`
    - Render Re-download button with `data-id` and `data-filename` attributes
    - _Requirements: 4.2, 4.3, 4.4_
  - [x] 7.2 Add Re-download JavaScript to `history.blade.php`
    - On button click, POST to `/history/redownload/{id}` via `fetch` with CSRF token
    - On success set `window.location.href = data.download_url`
    - On error display an inline error message
    - _Requirements: 5.2, 5.3_

- [x] 8. Update frontend and navigation
  - [x] 8.1 Update document translation success branch in `resources/views/translation.blade.php`
    - Change condition from `data.download_token` to `data.download_url`
    - Set `downloadLink.href = data.download_url` and `downloadLink.download = data.download_filename`
    - Optionally display `data.signed_url_expires_at` in the UI
    - _Requirements: 3.2, 3.3_
  - [x] 8.2 Update navigation link in `resources/views/layouts/app.blade.php`
    - Replace `<a href="#" class="nav-link">My Documents</a>` with `<a href="{{ route('history') }}" class="nav-link {{ request()->routeIs('history') ? 'active' : '' }}">History</a>`
    - _Requirements: 4.1_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use the `eris` library (`giorgiosironi/eris: 0.12`) already in `require-dev`; each must run a minimum of 100 iterations
- Unit tests focus on specific examples, edge cases, and controller ↔ service wiring
- Internal error details (stack traces, Supabase error bodies) must never be exposed to the browser — log only
- The `download()` method and `GET /translate/download/{token}` route are kept for backward compatibility but will no longer be populated by new translations

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "3.6"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1", "6.3"] },
    { "id": 6, "tasks": ["5.3", "5.4", "5.5", "6.2", "7.1"] },
    { "id": 7, "tasks": ["6.4", "6.5", "7.2"] },
    { "id": 8, "tasks": ["8.1", "8.2"] }
  ]
}
```
