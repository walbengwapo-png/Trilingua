# User ID History Fix — Bugfix Design

## Overview

Translation history records and translated documents are currently tied to a PHP session ID rather than the authenticated user's ID. Because a new session is generated on every login, users lose access to all their previous translations and documents after logging out and back in.

The fix replaces `session_id` with `user_id` (a foreign key to the `users` table) as the ownership identifier in the `translation_history` Supabase table and updates every layer that reads or writes that column: `HistoryService`, `TranslationController`, `HistoryController`, and `DocumentsController`. The storage path prefix in `TranslationController` is also changed from `session()->getId()` to `Auth::id()` so that uploaded files are grouped by user rather than by session.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — a user logs out and back in, receiving a new session ID, which causes all history records (stored under the old session ID) to become invisible.
- **Property (P)**: The desired behavior — history records are stored and retrieved by `user_id`, so they persist across sessions.
- **Preservation**: All existing behaviors unrelated to the `session_id` → `user_id` swap must remain unchanged (403/404 ownership checks, ordering, error handling, translation flow, etc.).
- **`HistoryService`**: `app/Services/HistoryService.php` — the service that communicates with the Supabase REST API to insert and query `translation_history` rows.
- **`TranslationController`**: `app/Http/Controllers/TranslationController.php` — handles text and document translation requests; inserts history records and builds the Supabase Storage path.
- **`HistoryController`**: `app/Http/Controllers/HistoryController.php` — renders the history page and handles redownload requests; enforces ownership.
- **`DocumentsController`**: `app/Http/Controllers/DocumentsController.php` — renders the My Documents page by fetching history filtered to document-type records.
- **`Auth::id()`**: Laravel helper that returns the integer primary key of the currently authenticated user.
- **`session()->getId()`**: PHP/Laravel helper that returns the current session string — changes on every login.
- **`user_id`**: The integer foreign key referencing `users.id` that will replace `session_id` as the ownership column.
- **`storage_path`**: The Supabase Storage object path, currently prefixed with `session()->getId()`. After the fix it will be prefixed with `Auth::id()`.

## Bug Details

### Bug Condition

The bug manifests when an authenticated user logs out and logs back in. The new session ID no longer matches the `session_id` stored in `translation_history`, so `HistoryService::getHistory` returns an empty result set and `HistoryController::redownload` rejects ownership checks with a 403.

**Formal Specification:**
```
FUNCTION isBugCondition(context)
  INPUT: context = { userId: int, currentSessionId: string, storedSessionId: string }
  OUTPUT: boolean

  RETURN context.currentSessionId != context.storedSessionId
         AND context.userId IS NOT NULL
         AND recordsExistForUser(context.userId)
END FUNCTION
```

### Examples

- **History page shows empty after re-login**: User creates 5 translations, logs out, logs back in. `getHistory(session()->getId())` returns `[]` because the new session ID matches no rows. Expected: all 5 records are shown.
- **Redownload returns 403 after re-login**: User tries to redownload a document from a previous session. `$record['session_id'] !== session()->getId()` evaluates to `true`, returning 403. Expected: ownership check passes because `$record['user_id'] === Auth::id()`.
- **My Documents page shows empty after re-login**: `DocumentsController` calls `getHistory(session()->getId())`, which returns `[]` for the new session. Expected: all document records for the user are shown.
- **Storage path is session-scoped**: Uploaded files are stored at `{sessionId}/{filename}`. After re-login the path prefix changes, making old files unreachable via the stored `storage_path`. Expected: files are stored at `{userId}/{filename}`, which is stable across sessions.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- A redownload request for a record belonging to a different user MUST continue to return 403 Forbidden.
- A redownload request for a non-existent record MUST continue to return 404 Not Found.
- A failed database insert during translation MUST continue to be logged without blocking the translation response.
- `HistoryService::getHistory` MUST continue to return records ordered by `created_at` descending, capped at 200 results.
- `HistoryService::updateExpiry` MUST continue to update `signed_url_expires_at` for the specified record ID.
- Document translation MUST continue to upload the translated file to Supabase Storage and return a signed download URL.
- Text translation MUST continue to return the translated text to the user.

**Scope:**
All inputs that do NOT involve the `session_id` → `user_id` ownership lookup are completely unaffected by this fix. This includes:
- Mouse/keyboard interactions with the UI
- Translation logic (text extraction, AI calls, file conversion)
- Supabase Storage upload and signed URL generation
- Authentication and session management themselves

## Hypothesized Root Cause

Based on the bug description and code review, the root causes are:

1. **`HistoryService::insertRecord` stores `session_id`**: The payload builder includes `'session_id' => $data['session_id'] ?? null` and the callers pass `session()->getId()`. There is no `user_id` field in the payload.

2. **`HistoryService::getHistory` filters by `session_id`**: The Supabase query uses `'session_id' => "eq.{$sessionId}"`. A new session ID after re-login matches zero rows.

3. **`TranslationController` passes `session()->getId()` as `session_id`**: Both the document and text translation branches call `$this->history->insertRecord(['session_id' => session()->getId(), ...])`.

4. **`TranslationController` uses `session()->getId()` as the storage path prefix**: `$storagePath = session()->getId() . '/' . basename($outputPath)` — the stored path becomes stale after re-login.

5. **`HistoryController::redownload` compares `$record['session_id']` to `session()->getId()`**: After re-login the comparison always fails, returning 403 for legitimate owners.

6. **`DocumentsController` passes `session()->getId()` to `getHistory`**: Inherits the same empty-result problem as `HistoryController::index`.

7. **`translation_history` table has no `user_id` column**: The Supabase schema only has `session_id`; there is no foreign key to `users`.

## Correctness Properties

Property 1: Bug Condition — History Persists Across Sessions

_For any_ authenticated user who has previously created translation records, after logging out and back in (receiving a new session ID), the fixed system SHALL return all records belonging to that user when `getHistory` is called with `Auth::id()`, and SHALL grant ownership on redownload when `record['user_id'] === Auth::id()`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation — Cross-User Ownership Enforcement

_For any_ redownload request where the authenticated user's ID does NOT match the `user_id` stored on the record (i.e., the bug condition does NOT apply — the record exists and belongs to a different user), the fixed `HistoryController::redownload` SHALL return 403 Forbidden, identical to the original behavior.

**Validates: Requirements 3.1, 3.2**

## Fix Implementation

### Changes Required

#### 1. New Migration — `translation_history`: add `user_id`, drop `session_id`

**File**: `database/migrations/2026_05_09_000001_replace_session_id_with_user_id_in_translation_history.php`

**Specific Changes**:
- Add `user_id` column (`bigint unsigned`, not null, foreign key → `users.id`).
- Drop the `session_id` column.
- Drop the old `(session_id, created_at)` index.
- Add a new `(user_id, created_at)` index.

> **Note**: The `translation_history` table lives in Supabase (PostgreSQL), not in the local SQLite database. The migration file documents the schema change for version control and serves as the authoritative reference for the manual SQL that must be run against Supabase. The SQL equivalent is:
> ```sql
> ALTER TABLE translation_history
>   ADD COLUMN user_id bigint NOT NULL REFERENCES users(id);
> DROP INDEX IF EXISTS translation_history_session_id_created_at_index;
> CREATE INDEX translation_history_user_id_created_at_index
>   ON translation_history (user_id, created_at);
> ALTER TABLE translation_history DROP COLUMN session_id;
> ```

---

#### 2. `HistoryService::insertRecord` — use `user_id`

**File**: `app/Services/HistoryService.php`

**Specific Changes**:
- Replace `'session_id' => $data['session_id'] ?? null` with `'user_id' => $data['user_id'] ?? null` in the payload builder.
- Update the docblock to document `user_id` instead of `session_id`.

---

#### 3. `HistoryService::getHistory` — filter by `user_id`

**File**: `app/Services/HistoryService.php`

**Specific Changes**:
- Rename the parameter from `string $sessionId` to `int $userId`.
- Change the query parameter from `'session_id' => "eq.{$sessionId}"` to `'user_id' => "eq.{$userId}"`.
- Update the docblock accordingly.

---

#### 4. `TranslationController::translate` — pass `Auth::id()` as `user_id`

**File**: `app/Http/Controllers/TranslationController.php`

**Specific Changes**:
- Add `use Illuminate\Support\Facades\Auth;` import.
- In the document translation branch:
  - Change `$storagePath = session()->getId() . '/' . basename($outputPath)` to `$storagePath = Auth::id() . '/' . basename($outputPath)`.
  - Change `'session_id' => session()->getId()` to `'user_id' => Auth::id()` in the `insertRecord` call.
  - Update the error log context key from `'session_id'` to `'user_id'`.
- In the text translation branch:
  - Change `'session_id' => session()->getId()` to `'user_id' => Auth::id()` in the `insertRecord` call.
  - Update the error log context key from `'session_id'` to `'user_id'`.

---

#### 5. `HistoryController` — use `Auth::id()` for history fetch and ownership check

**File**: `app/Http/Controllers/HistoryController.php`

**Specific Changes**:
- Add `use Illuminate\Support\Facades\Auth;` import.
- In `index`: change `$this->history->getHistory(session()->getId())` to `$this->history->getHistory(Auth::id())`.
- In `index` error log: change `'session_id' => session()->getId()` to `'user_id' => Auth::id()`.
- In `redownload`: change `$record['session_id'] !== session()->getId()` to `$record['user_id'] !== Auth::id()`.

---

#### 6. `DocumentsController` — use `Auth::id()`

**File**: `app/Http/Controllers/DocumentsController.php`

**Specific Changes**:
- Add `use Illuminate\Support\Facades\Auth;` import.
- Change `$this->history->getHistory(session()->getId())` to `$this->history->getHistory(Auth::id())`.
- Update the error log context key from `'session_id'` to `'user_id'`.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write unit tests that simulate a user creating history records under one session ID, then querying with a different session ID (simulating re-login). Run these tests on the UNFIXED code to observe that records are not returned.

**Test Cases**:
1. **History invisible after session change**: Insert a record with `session_id = 'session-A'`, call `getHistory('session-B')` — expect empty array. On unfixed code this confirms the bug; on fixed code (using `user_id`) this scenario is eliminated. (will fail to demonstrate bug on fixed code)
2. **Redownload 403 after session change**: Insert a record with `session_id = 'session-A'`, simulate redownload with `session()->getId() = 'session-B'` — expect 403. On unfixed code this confirms the bug. (will fail to demonstrate bug on fixed code)
3. **Storage path changes on re-login**: Verify that `session()->getId()` produces a different prefix after session regeneration, making the stored `storage_path` stale. (confirms root cause 4)
4. **Documents page empty after session change**: Call `DocumentsController::index` with a new session — expect empty documents array on unfixed code.

**Expected Counterexamples**:
- `getHistory` returns `[]` even though records exist for the user under a different session ID.
- `redownload` returns 403 for the legitimate owner because the session ID changed.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed system produces the expected behavior.

**Pseudocode:**
```
FOR ALL user WHERE isBugCondition({ userId: user.id, currentSessionId: newSession, storedSessionId: oldSession }) DO
  records := getHistory_fixed(user.id)
  ASSERT records contains all records created by user.id
  
  FOR ALL record IN records DO
    ASSERT redownload_fixed(record.id, user.id) returns 200 (not 403)
  END FOR
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed system produces the same result as the original system.

**Pseudocode:**
```
FOR ALL (requestUserId, recordUserId) WHERE requestUserId != recordUserId DO
  ASSERT redownload_original(record.id, requestUserId) = redownload_fixed(record.id, requestUserId)
  -- Both return 403 Forbidden
END FOR

FOR ALL nonExistentId DO
  ASSERT redownload_original(nonExistentId) = redownload_fixed(nonExistentId)
  -- Both return 404 Not Found
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (random user IDs, record IDs, ownership combinations).
- It catches edge cases that manual unit tests might miss (e.g., `user_id = 0`, very large IDs).
- It provides strong guarantees that the 403/404 behavior is unchanged for all non-buggy inputs.

**Test Plan**: Observe behavior on UNFIXED code first for cross-user and missing-record scenarios, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Cross-user 403 preservation**: Generate random pairs of `(ownerUserId, requestUserId)` where they differ — verify 403 is always returned.
2. **Missing record 404 preservation**: Generate random non-existent record IDs — verify 404 is always returned.
3. **Ordering preservation**: Verify records are still returned ordered by `created_at` descending, capped at 200.
4. **Error handling preservation**: Verify that a failed `insertRecord` still logs the error and does not block the translation response.

### Unit Tests

- Test `HistoryService::insertRecord` sends `user_id` (not `session_id`) in the Supabase POST payload.
- Test `HistoryService::getHistory` queries by `user_id` (not `session_id`).
- Test `HistoryController::redownload` returns 403 when `record['user_id'] !== Auth::id()`.
- Test `HistoryController::redownload` returns 200 when `record['user_id'] === Auth::id()`.
- Test `TranslationController::translate` (document mode) builds `storage_path` as `{userId}/{filename}`.
- Test `TranslationController::translate` (document mode) passes `user_id` to `insertRecord`.
- Test `TranslationController::translate` (text mode) passes `user_id` to `insertRecord`.
- Test `DocumentsController::index` calls `getHistory` with `Auth::id()`.

### Property-Based Tests

- Generate random authenticated user IDs and verify `getHistory(userId)` always returns only records belonging to that user.
- Generate random pairs of distinct user IDs and verify `redownload` always returns 403 when the requesting user is not the owner.
- Generate random non-existent record IDs and verify `redownload` always returns 404.
- Generate random valid user IDs and verify the storage path prefix is always `{userId}/` (integer, not a UUID session string).

### Integration Tests

- Full flow: authenticate as User A, create a translation, log out, log back in as User A — verify history page shows the record.
- Full flow: authenticate as User A, create a document translation, log out, log back in as User A — verify My Documents page shows the document and redownload succeeds.
- Cross-user isolation: authenticate as User A, create a record, authenticate as User B — verify User B cannot redownload User A's record (403).
- Verify the Supabase Storage path for a new document upload is `{userId}/{filename}` after the fix.
