# Design Document — Supabase Cloud Storage

## Overview

This feature integrates Supabase Storage and Supabase Database (PostgREST) into the existing Trilingua Laravel 12 application. After a successful document translation, the translated file is uploaded to a private Supabase Storage bucket, a 7-day signed download URL is generated and returned to the browser, and a record of the job is written to a `translation_history` table. A new History page lets users view and re-download past translations scoped to their current Laravel session.

No authentication changes are required. The Laravel session ID (`session()->getId()`) serves as the user identifier throughout.

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Raw Guzzle HTTP calls instead of a Supabase PHP SDK | No SDK is installed; Guzzle is already available via Laravel's default stack. Avoids adding a new dependency for a small, well-defined API surface. |
| Service Role Key for Storage uploads | Supabase Storage upload and signed-URL endpoints require the `service_role` key when the bucket is private. The anon key is used only for PostgREST DB calls where Row Level Security (RLS) policies apply. |
| DB failure does not block the download response | The signed URL is the primary user value. A logging failure should never prevent the user from downloading their file. |
| Session ID as user identifier | Authentication is out of scope. The session ID is already available in every request and provides adequate scoping for a single-session history feature. |
| 200-row cap on history queries | Prevents unbounded result sets from a single session accumulating over time. |

---

## Architecture

### Component Overview

```
Browser
  │
  ▼
routes/web.php
  │
  ├─► TranslationController  (modified)
  │       │
  │       ├─► TranslationService  (unchanged)
  │       ├─► StorageService      (new)
  │       └─► HistoryService      (new)
  │
  └─► HistoryController      (new)
          │
          ├─► HistoryService      (new)
          └─► StorageService      (new)

StorageService ──► Supabase Storage REST API  (via Guzzle)
HistoryService ──► Supabase PostgREST API     (via Guzzle)
```

### New Files

| Path | Purpose |
|---|---|
| `app/Services/StorageService.php` | Upload files, generate signed URLs |
| `app/Services/HistoryService.php` | Insert, query, and update `translation_history` |
| `app/Http/Controllers/HistoryController.php` | History page + re-download endpoint |
| `resources/views/history.blade.php` | History page Blade view |
| `app/Providers/SupabaseServiceProvider.php` | Boot-time env-var validation |

### Modified Files

| Path | Change |
|---|---|
| `app/Http/Controllers/TranslationController.php` | Document branch: call StorageService + HistoryService, return `download_url` |
| `resources/views/translation.blade.php` | JS: read `download_url` / `download_filename` instead of `download_token` |
| `config/services.php` | Add `supabase` key |
| `.env.example` | Add four Supabase placeholder variables |
| `routes/web.php` | Add GET /history and POST /history/redownload/{id} |
| `app/Providers/AppServiceProvider.php` | Register SupabaseServiceProvider (or inline boot validation) |

---

## Components and Interfaces

### StorageService

```php
namespace App\Services;

class StorageService
{
    public function __construct(private \GuzzleHttp\Client $guzzle) {}

    /**
     * Upload a local file to Supabase Storage.
     *
     * @param  string $localPath   Absolute path to the file on disk.
     * @param  string $storagePath Destination path inside the bucket, e.g. "{session_id}/{uuid}_translated.docx".
     * @return array{storage_path: string, signed_url: string, signed_url_expires_at: string}
     * @throws \RuntimeException on upload or signed-URL failure.
     */
    public function uploadFile(string $localPath, string $storagePath): array;

    /**
     * Generate a new signed URL for an existing object in Supabase Storage.
     *
     * @param  string $storagePath Path inside the bucket.
     * @return array{signed_url: string, signed_url_expires_at: string}
     * @throws \RuntimeException if the file does not exist (wraps 400/404 from Supabase).
     * @throws \RuntimeException on any other Supabase error.
     */
    public function generateSignedUrl(string $storagePath): array;
}
```

**Signed URL expiry constant:** `SIGNED_URL_EXPIRY_SECONDS = 604800` (7 days). This constant is used in both `uploadFile` and `generateSignedUrl` to ensure consistency.

### HistoryService

```php
namespace App\Services;

class HistoryService
{
    public function __construct(private \GuzzleHttp\Client $guzzle) {}

    /**
     * Insert a new translation job record.
     *
     * @param  array $data  Keys: session_id, original_filename, translated_filename,
     *                      source_language, target_language, storage_path,
     *                      signed_url_expires_at (ISO 8601 UTC string).
     * @throws \RuntimeException on DB error.
     */
    public function insertRecord(array $data): void;

    /**
     * Fetch history records for a session, newest first, capped at 200.
     *
     * @return array<int, array>  Each element is a translation_history row.
     * @throws \RuntimeException on DB error.
     */
    public function getHistory(string $sessionId): array;

    /**
     * Fetch a single record by ID.
     *
     * @return array|null  Null if not found.
     * @throws \RuntimeException on DB error.
     */
    public function getRecord(int $id): ?array;

    /**
     * Update the signed_url_expires_at column for a record.
     *
     * @throws \RuntimeException on DB error.
     */
    public function updateExpiry(int $id, string $newExpiry): void;
}
```

### HistoryController

```php
namespace App\Http\Controllers;

class HistoryController extends Controller
{
    public function __construct(
        private HistoryService $history,
        private StorageService $storage,
    ) {}

    /** GET /history */
    public function index(Request $request): View|Response;

    /** POST /history/redownload/{id} */
    public function redownload(Request $request, int $id): JsonResponse;
}
```

### TranslationController (document branch — modified)

The existing `download()` method and session-token logic are **removed** from the document branch. The document branch now:

1. Calls `TranslationService::translateDocument()` → `$localPath`
2. Builds `$storagePath = session()->getId() . '/' . basename($localPath)`
3. Calls `StorageService::uploadFile($localPath, $storagePath)` → `$storageResult`
4. Deletes `$localPath` with `@unlink($localPath)` (removes the `register_shutdown_function` cleanup)
5. Calls `HistoryService::insertRecord(...)` — wrapped in try/catch; failure is logged but does not abort
6. Returns JSON: `{ download_url, download_filename, signed_url_expires_at }`

The `download()` method and its route (`GET /translate/download/{token}`) are **kept** for backward compatibility during the transition but will no longer be populated by new translations.

---

## Data Models

### `translation_history` Table — SQL DDL

```sql
CREATE TABLE translation_history (
    id                   BIGSERIAL PRIMARY KEY,
    session_id           TEXT        NOT NULL,
    original_filename    TEXT        NOT NULL,
    translated_filename  TEXT        NOT NULL,
    source_language      TEXT        NOT NULL,
    target_language      TEXT        NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    storage_path         TEXT        NOT NULL,
    signed_url_expires_at TIMESTAMPTZ NOT NULL
);

-- Index for the most common query pattern: fetch by session, newest first
CREATE INDEX idx_translation_history_session_created
    ON translation_history (session_id, created_at DESC);
```

All columns are `NOT NULL` — the schema enforces the constraint from Requirement 2.2.

### `config/services.php` Addition

```php
'supabase' => [
    'url'               => env('SUPABASE_URL'),
    'anon_key'          => env('SUPABASE_ANON_KEY'),
    'service_role_key'  => env('SUPABASE_SERVICE_ROLE_KEY'),
    'bucket'            => env('SUPABASE_BUCKET'),
],
```

### `.env.example` Additions

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_BUCKET=translations
```

### Boot-time Validation

A dedicated `SupabaseServiceProvider` (or inline in `AppServiceProvider::boot`) validates all four variables at startup:

```php
$required = ['SUPABASE_URL', 'SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_BUCKET'];
foreach ($required as $var) {
    if (empty(env($var))) {
        throw new \RuntimeException("Missing required environment variable: {$var}");
    }
}
```

---

## Supabase API Integration

### Storage REST API (via Guzzle)

Base URL: `{SUPABASE_URL}/storage/v1`  
Auth header: `Authorization: Bearer {SUPABASE_SERVICE_ROLE_KEY}`

#### Upload Object

```
POST /storage/v1/object/{bucket}/{storagePath}
Content-Type: <mime type of file>
Authorization: Bearer {service_role_key}

Body: raw file bytes
```

Success: HTTP 200 with `{ "Key": "bucket/path" }`.  
Failure: non-2xx → throw `RuntimeException("Supabase Storage upload failed: {response body}")`.

#### Generate Signed URL

```
POST /storage/v1/object/sign/{bucket}/{storagePath}
Content-Type: application/json
Authorization: Bearer {service_role_key}

Body: { "expiresIn": 604800 }
```

Success: HTTP 200 with `{ "signedURL": "https://..." }`.  
The full signed URL is: `{SUPABASE_URL}/storage/v1{signedURL}` (Supabase returns a relative path).  
Failure: non-2xx → throw `RuntimeException("Supabase signed URL generation failed: {response body}")`.

### PostgREST API (via Guzzle)

Base URL: `{SUPABASE_URL}/rest/v1`  
Auth headers:
```
Authorization: Bearer {SUPABASE_ANON_KEY}
apikey: {SUPABASE_ANON_KEY}
Content-Type: application/json
Prefer: return=minimal   (for INSERT/UPDATE)
```

#### Insert Record

```
POST /rest/v1/translation_history
Body: { session_id, original_filename, translated_filename, source_language,
        target_language, created_at, storage_path, signed_url_expires_at }
```

Success: HTTP 201.  
Failure: non-2xx → throw `RuntimeException("Supabase DB insert failed: {response body}")`.

#### Query History

```
GET /rest/v1/translation_history
    ?session_id=eq.{sessionId}
    &order=created_at.desc
    &limit=200
    &select=id,original_filename,translated_filename,source_language,target_language,created_at,storage_path,signed_url_expires_at
```

Success: HTTP 200 with JSON array.

#### Fetch Single Record

```
GET /rest/v1/translation_history?id=eq.{id}&limit=1
```

Success: HTTP 200 with JSON array (0 or 1 elements).

#### Update Expiry

```
PATCH /rest/v1/translation_history?id=eq.{id}
Body: { "signed_url_expires_at": "{newExpiry}" }
```

Success: HTTP 204.

---

## Routes

Added inside the existing `middleware(['auth', 'throttle:60,1'])` group in `routes/web.php`:

```php
use App\Http\Controllers\HistoryController;

Route::get('/history', [HistoryController::class, 'index'])->name('history');
Route::post('/history/redownload/{id}', [HistoryController::class, 'redownload'])->name('history.redownload');
```

---

## Views

### `resources/views/history.blade.php` — Structure

```
@extends('layouts.app')
@section('title', 'Translation History')
@section('content')
  @if ($error)
    <p class="error">Unable to load history. Please try again later.</p>
  @elseif ($records->isEmpty())
    <p class="empty-state">You have no translation history yet.</p>
  @else
    <table>
      <thead>
        <tr>
          <th>Original File</th>
          <th>Translated File</th>
          <th>From</th>
          <th>To</th>
          <th>Date (UTC)</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        @foreach ($records as $record)
          <tr>
            <td>{{ $record['original_filename'] }}</td>
            <td>{{ $record['translated_filename'] }}</td>
            <td>{{ $record['source_language'] }}</td>
            <td>{{ $record['target_language'] }}</td>
            <td>{{ \Carbon\Carbon::parse($record['created_at'])->utc()->format('Y-m-d H:i') }} UTC</td>
            <td>
              <button class="btn secondary redownload-btn"
                      data-id="{{ $record['id'] }}"
                      data-filename="{{ $record['translated_filename'] }}">
                Re-download
              </button>
            </td>
          </tr>
        @endforeach
      </tbody>
    </table>
  @endif
@endsection
```

The Re-download button triggers a `fetch` POST to `/history/redownload/{id}`, receives `{ download_url }`, and sets `window.location.href` to initiate the download.

### `resources/views/translation.blade.php` — JS Changes

The document translation success branch changes from:

```js
// OLD
if (response.ok && data && data.download_token) {
    var downloadUrl = '/translate/download/' + encodeURIComponent(data.download_token);
    downloadLink.href = downloadUrl;
    downloadLink.download = data.download_filename || 'translated_document';
}
```

to:

```js
// NEW
if (response.ok && data && data.download_url) {
    downloadLink.href = data.download_url;
    downloadLink.download = data.download_filename || 'translated_document';
    // Optionally display expiry: data.signed_url_expires_at
}
```

### Navigation — `layouts/app.blade.php`

The placeholder `<a href="#" class="nav-link">My Documents</a>` is updated to:

```html
<a href="{{ route('history') }}" class="nav-link {{ request()->routeIs('history') ? 'active' : '' }}">
    History
</a>
```

---

## Data Flow Diagrams

### 1. Document Translation Flow (POST /translate)

```
Browser
  │  POST /translate (multipart: document, source_lang, target_lang)
  ▼
TranslationController::translate()
  │
  ├─► TranslationService::translateDocument()
  │       └─► Python microservice (cURL)
  │           └─► returns $localPath (storage/app/temp/{uuid}_translated.{ext})
  │
  ├─► StorageService::uploadFile($localPath, "{sessionId}/{uuid}_translated.{ext}")
  │       ├─► Guzzle POST /storage/v1/object/{bucket}/{path}   [upload]
  │       ├─► Guzzle POST /storage/v1/object/sign/{bucket}/{path}  [sign]
  │       └─► returns { storage_path, signed_url, signed_url_expires_at }
  │
  ├─► @unlink($localPath)   [delete temp file]
  │
  ├─► HistoryService::insertRecord(...)   [try/catch — failure logged, not re-thrown]
  │       └─► Guzzle POST /rest/v1/translation_history
  │
  └─► return JSON { download_url, download_filename, signed_url_expires_at }
          │
          ▼
        Browser renders <a href="{download_url}" download="{filename}">
```

### 2. History Page Load (GET /history)

```
Browser
  │  GET /history
  ▼
HistoryController::index()
  │
  ├─► HistoryService::getHistory(session()->getId())
  │       └─► Guzzle GET /rest/v1/translation_history?session_id=eq.{id}&order=created_at.desc&limit=200
  │           └─► returns array of rows (or throws on DB error)
  │
  ├─► [on DB error] log exception → render error view
  │
  └─► render history.blade.php with $records
          │
          ▼
        Browser displays table (or empty state)
```

### 3. Re-download Flow (POST /history/redownload/{id})

```
Browser
  │  POST /history/redownload/{id}  (AJAX fetch)
  ▼
HistoryController::redownload()
  │
  ├─► HistoryService::getRecord($id)
  │       └─► Guzzle GET /rest/v1/translation_history?id=eq.{id}&limit=1
  │
  ├─► [record not found] → 404
  ├─► [session_id mismatch] → 403
  │
  ├─► StorageService::generateSignedUrl($record['storage_path'])
  │       └─► Guzzle POST /storage/v1/object/sign/{bucket}/{path}
  │           ├─► [file not found in storage] → throw with "not found" marker → 404
  │           └─► [other error] → throw → 500
  │
  ├─► HistoryService::updateExpiry($id, $newExpiry)
  │       └─► Guzzle PATCH /rest/v1/translation_history?id=eq.{id}
  │
  └─► return JSON { download_url }
          │
          ▼
        Browser: window.location.href = download_url
```

---

## Error Handling Strategy

| Scenario | Behaviour |
|---|---|
| Upload to Supabase Storage fails | `StorageService` throws `RuntimeException`. `TranslationController` catches it and returns HTTP 500 `{ "error": "..." }`. Frontend shows error in output panel. |
| Signed URL generation fails | Same as above. |
| DB insert fails | `HistoryService` throws. `TranslationController` catches, logs via `Log::error()`, and continues — returns HTTP 200 with `download_url`. |
| History page DB query fails | `HistoryController` catches, logs, renders error view with generic message. |
| Re-download: record not found | HTTP 404 `{ "error": "This file is no longer available." }` |
| Re-download: session mismatch | HTTP 403 `{ "error": "Forbidden." }` — no information about record existence. |
| Re-download: file not in storage | HTTP 404 `{ "error": "This file is no longer available." }` |
| Re-download: other storage error | HTTP 500 `{ "error": "Unable to generate download link. Please try again later." }` |
| Missing env var at boot | `RuntimeException` thrown in service provider — application fails to start with a clear message. |
| Guzzle connection error | Guzzle throws `ConnectException` — caught by the service and re-thrown as `RuntimeException` with a descriptive message. |

Internal error details (stack traces, Supabase error bodies) are **never** exposed to the browser. They are written to the Laravel log only.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property Reflection

Before listing properties, redundancy is eliminated:

- 1.2 (signed URL expiry = created_at + 604800) and 5.1 (re-download expiry = 604800) are the same invariant applied in two places. They are merged into **Property 2: Signed URL expiry invariant**.
- 1.1 (storage path format) and 2.1 (insert payload completeness) are distinct — both kept.
- 3.1 (response shape) and 3.3 (error → HTTP 500) are distinct — both kept.
- 4.1 (ordering + 200-row cap) and 4.2 (required fields in view data) are distinct — both kept.
- 5.7 (session mismatch → 403) is a security invariant — kept as its own property.
- 6.2 (missing env var → RuntimeException) is a property over all subsets of missing vars — kept.

### Property 1: Storage Path Format

*For any* session ID and translated file UUID + extension, the storage path constructed by `StorageService` must match the pattern `{session_id}/{uuid}_translated.{ext}`, where `{ext}` is a non-empty lowercase file extension.

**Validates: Requirements 1.1**

### Property 2: Signed URL Expiry Invariant

*For any* timestamp at which a signed URL is generated (whether during initial upload or re-download), the `signed_url_expires_at` value returned by `StorageService` must equal that timestamp plus exactly 604 800 seconds.

**Validates: Requirements 1.2, 5.1**

### Property 3: Upload Failure Propagates as Exception

*For any* non-2xx HTTP status code returned by the Supabase Storage upload endpoint (mocked), `StorageService::uploadFile()` must throw a `RuntimeException` whose message contains the Supabase error body.

**Validates: Requirements 1.4**

### Property 4: Translation Response Shape

*For any* successful document translation and upload, the JSON response from `TranslationController::translate()` must contain all three keys — `download_url`, `download_filename`, and `signed_url_expires_at` — with non-empty string values.

**Validates: Requirements 3.1**

### Property 5: Storage Failure Returns HTTP 500

*For any* exception thrown by `StorageService` during a document translation request, `TranslationController::translate()` must return HTTP 500 with a JSON body containing an `error` key.

**Validates: Requirements 3.3**

### Property 6: History Insert Payload Completeness

*For any* valid translation job (any session ID, any filenames, any language pair, any timestamps), the payload passed by `HistoryService::insertRecord()` to the PostgREST API must contain all eight required columns — `session_id`, `original_filename`, `translated_filename`, `source_language`, `target_language`, `created_at`, `storage_path`, `signed_url_expires_at` — with non-null values.

**Validates: Requirements 2.1**

### Property 7: History Ordering and Cap

*For any* set of translation history records stored for a session, `HistoryService::getHistory()` must return them ordered by `created_at` descending and must return at most 200 records regardless of how many exist.

**Validates: Requirements 4.1**

### Property 8: Session Ownership Enforcement

*For any* re-download request where the `session_id` stored in the `translation_history` record differs from the current Laravel session ID, `HistoryController::redownload()` must return HTTP 403 without revealing whether the record or file exists.

**Validates: Requirements 5.7**

### Property 9: Missing Env Var Throws RuntimeException

*For any* non-empty subset of the four required Supabase environment variables (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`) being absent or empty, the application boot sequence must throw a `RuntimeException` whose message names at least one of the missing variables.

**Validates: Requirements 6.2**

---

## Testing Strategy

### Dual Testing Approach

Unit tests cover specific examples, edge cases, and error conditions. Property-based tests verify universal invariants across many generated inputs. Both are needed for comprehensive coverage.

### Property-Based Testing Library

**[eris](https://github.com/giorgiosironi/eris)** (already in `require-dev` as `giorgiosironi/eris: 0.12`) is the property-based testing library for PHP in this project. It integrates with PHPUnit and provides generators for strings, integers, dates, and custom types.

Each property test must run a minimum of **100 iterations**.

Tag format for each property test:
```
Feature: supabase-cloud-storage, Property {N}: {property_text}
```

### Property Tests (eris + PHPUnit)

| Property | Test class | Generator inputs |
|---|---|---|
| P1: Storage path format | `StorageServicePathTest` | `string()` for session_id, `string()` for uuid, `elements(['.docx','.pdf','.txt','.md'])` for ext |
| P2: Signed URL expiry invariant | `StorageServiceExpiryTest` | `date()` / `integer()` for base timestamp |
| P3: Upload failure propagates | `StorageServiceUploadFailureTest` | `elements([400,401,403,404,500,502,503])` for HTTP status |
| P4: Translation response shape | `TranslationControllerResponseTest` | `string()` for filenames, `elements(['English','Cebuano','Filipino'])` for languages |
| P5: Storage failure → HTTP 500 | `TranslationControllerStorageFailureTest` | `string()` for exception messages |
| P6: Insert payload completeness | `HistoryServiceInsertTest` | `string()` for session_id/filenames, `elements([...])` for languages |
| P7: History ordering and cap | `HistoryServiceQueryTest` | `vector(integer(0, 300), historyRecordGen())` for record sets |
| P8: Session ownership enforcement | `HistoryControllerOwnershipTest` | `string()` for session IDs (ensure they differ) |
| P9: Missing env var throws | `SupabaseConfigTest` | `subset(['SUPABASE_URL','SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_BUCKET'])` |

### Unit / Example Tests (PHPUnit)

- `StorageService`: successful upload returns correct array shape; signed URL generation success; Guzzle `ConnectException` is re-thrown as `RuntimeException`.
- `HistoryService`: `getRecord()` returns null for missing ID; `updateExpiry()` sends correct PATCH payload.
- `TranslationController`: DB insert failure is logged but does not block HTTP 200 response; `download_token` route still returns 404 for expired tokens.
- `HistoryController`: empty history renders empty-state message; DB error renders error view; re-download 404 on missing file; re-download 500 on generic storage error.
- `SupabaseServiceProvider`: all four vars present → no exception.

### Integration Tests

- End-to-end document translation with a real (or Supabase-local) bucket: upload succeeds, signed URL is accessible, DB row is created.
- History page: row appears after translation, Re-download returns a valid URL.

### Unit Testing Balance

Property tests handle broad input coverage. Unit tests focus on:
- Specific success/failure examples
- Integration points (controller ↔ service wiring)
- Edge cases (empty session ID, filename with spaces, very long filenames)

Avoid duplicating coverage between unit and property tests.
