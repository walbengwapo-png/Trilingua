# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - History Invisible After Re-Login
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate that records stored under one session ID are invisible when queried with a different session ID (simulating re-login)
  - **Scoped PBT Approach**: For deterministic bugs, scope the property to the concrete failing cases to ensure reproducibility
  - Test cases to cover (from Bug Condition in design):
    - Insert a record with `session_id = 'session-A'` via a mocked Supabase call, then call `getHistory('session-B')` — assert the result is empty (confirms `isBugCondition` holds: `currentSessionId != storedSessionId`)
    - Simulate `HistoryController::redownload` with a record whose `session_id = 'session-A'` and current session `'session-B'` — assert 403 is returned
    - Verify `DocumentsController::index` returns an empty documents array when called with a new session ID while records exist under the old one
  - The test assertions should match the Expected Behavior Properties from design (records returned by `user_id`, ownership check passes for same user)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g., "`getHistory('session-B')` returns `[]` even though 5 records exist under `'session-A'` for the same user")
  - Mark task complete when tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Cross-User Ownership and Error Behavior
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs (cases where `isBugCondition` returns false — i.e., the requesting user is NOT the legitimate owner, or the record does not exist)
  - Observations to record on unfixed code:
    - `redownload(recordId, differentSessionId)` → 403 Forbidden
    - `redownload(nonExistentId, anySessionId)` → 404 Not Found
    - `getHistory(sessionId)` with 200+ records → returns exactly 200, ordered by `created_at` descending
    - Failed `insertRecord` during translation → error is logged, translation response is still returned
  - Write property-based tests (using Hypothesis or equivalent) capturing these observed behaviors:
    - For all pairs `(ownerUserId, requestUserId)` where they differ → `redownload` returns 403
    - For all non-existent record IDs → `redownload` returns 404
    - For any valid user with records → `getHistory` result is ordered descending and capped at 200
  - Verify all tests PASS on UNFIXED code (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix: Replace session_id with user_id across all layers

  - [x] 3.1 Create migration to add `user_id` and drop `session_id` in `translation_history`
    - Create file `database/migrations/2026_05_09_000001_replace_session_id_with_user_id_in_translation_history.php`
    - Add `user_id` column (`bigint unsigned`, not null, foreign key → `users.id`)
    - Drop the `session_id` column
    - Drop the old `(session_id, created_at)` index
    - Add new `(user_id, created_at)` index
    - Run the equivalent SQL against the Supabase PostgreSQL instance:
      ```sql
      ALTER TABLE translation_history
        ADD COLUMN user_id bigint NOT NULL REFERENCES users(id);
      DROP INDEX IF EXISTS translation_history_session_id_created_at_index;
      CREATE INDEX translation_history_user_id_created_at_index
        ON translation_history (user_id, created_at);
      ALTER TABLE translation_history DROP COLUMN session_id;
      ```
    - _Bug_Condition: isBugCondition(context) where context.currentSessionId != context.storedSessionId AND context.userId IS NOT NULL_
    - _Expected_Behavior: Records are keyed by user_id (stable across sessions) instead of session_id (changes on every login)_
    - _Preservation: Schema change only affects the ownership column; all other columns and indexes are unchanged_
    - _Requirements: 2.3, 2.5_

  - [x] 3.2 Update `HistoryService::insertRecord` to use `user_id`
    - In `app/Services/HistoryService.php`, replace `'session_id' => $data['session_id'] ?? null` with `'user_id' => $data['user_id'] ?? null` in the payload builder
    - Update the docblock to document `user_id` instead of `session_id`
    - _Bug_Condition: isBugCondition — payload was storing session_id, causing records to be invisible after re-login_
    - _Expected_Behavior: Payload now stores user_id so records persist across sessions_
    - _Preservation: All other payload fields (translation_type, filenames, languages, timestamps, etc.) are unchanged_
    - _Requirements: 2.3_

  - [x] 3.3 Update `HistoryService::getHistory` to filter by `user_id`
    - In `app/Services/HistoryService.php`, rename parameter from `string $sessionId` to `int $userId`
    - Change query parameter from `'session_id' => "eq.{$sessionId}"` to `'user_id' => "eq.{$userId}"`
    - Update the docblock accordingly
    - _Bug_Condition: isBugCondition — query was filtering by session_id, returning empty results after re-login_
    - _Expected_Behavior: Query filters by user_id, returning all records for the user across all sessions_
    - _Preservation: Ordering (created_at desc), limit (200), and selected columns are unchanged_
    - _Requirements: 2.5, 3.4_

  - [x] 3.4 Update `TranslationController::translate` to pass `Auth::id()` as `user_id`
    - In `app/Http/Controllers/TranslationController.php`, add `use Illuminate\Support\Facades\Auth;` import
    - Document translation branch:
      - Change `$storagePath = session()->getId() . '/' . basename($outputPath)` to `$storagePath = Auth::id() . '/' . basename($outputPath)`
      - Change `'session_id' => session()->getId()` to `'user_id' => Auth::id()` in the `insertRecord` call
      - Update error log context key from `'session_id'` to `'user_id'`
    - Text translation branch:
      - Change `'session_id' => session()->getId()` to `'user_id' => Auth::id()` in the `insertRecord` call
      - Update error log context key from `'session_id'` to `'user_id'`
    - _Bug_Condition: isBugCondition — storage path and history record were keyed by session_id, becoming stale after re-login_
    - _Expected_Behavior: Storage path is `{userId}/{filename}` (stable); history record stores user_id_
    - _Preservation: Translation logic, file upload, signed URL generation, and error handling are unchanged (Requirements 3.3, 3.6, 3.7)_
    - _Requirements: 2.3, 3.3, 3.6, 3.7_

  - [x] 3.5 Update `HistoryController` to use `Auth::id()`
    - In `app/Http/Controllers/HistoryController.php`, add `use Illuminate\Support\Facades\Auth;` import
    - In `index`: change `$this->history->getHistory(session()->getId())` to `$this->history->getHistory(Auth::id())`
    - In `index` error log: change `'session_id' => session()->getId()` to `'user_id' => Auth::id()`
    - In `redownload`: change `$record['session_id'] !== session()->getId()` to `$record['user_id'] !== Auth::id()`
    - _Bug_Condition: isBugCondition — ownership check compared session_id, always failing for re-logged-in users_
    - _Expected_Behavior: Ownership check compares user_id; history fetch returns all records for the user_
    - _Preservation: 403 for different user, 404 for missing record, 500 error handling — all unchanged (Requirements 3.1, 3.2)_
    - _Requirements: 2.1, 2.4, 3.1, 3.2_

  - [x] 3.6 Update `DocumentsController` to use `Auth::id()`
    - In `app/Http/Controllers/DocumentsController.php`, add `use Illuminate\Support\Facades\Auth;` import
    - Change `$this->history->getHistory(session()->getId())` to `$this->history->getHistory(Auth::id())`
    - Update error log context key from `'session_id'` to `'user_id'`
    - _Bug_Condition: isBugCondition — documents page queried by session_id, returning empty after re-login_
    - _Expected_Behavior: Documents page queries by user_id, showing all documents across sessions_
    - _Preservation: Document-type filtering logic and error handling are unchanged_
    - _Requirements: 2.2_

  - [x] 3.7 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - History Persists Across Sessions
    - **IMPORTANT**: Re-run the SAME tests from task 1 — do NOT write new tests
    - The tests from task 1 encode the expected behavior (records returned by `user_id`, ownership check passes for same user)
    - When these tests pass, it confirms the expected behavior is satisfied
    - Run bug condition exploration tests from step 1
    - **EXPECTED OUTCOME**: Tests PASS (confirms bug is fixed — history is visible after re-login, redownload returns 200 for legitimate owner)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.8 Verify preservation tests still pass
    - **Property 2: Preservation** - Cross-User Ownership and Error Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — 403/404 behavior, ordering, error handling all unchanged)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint — Ensure all tests pass
  - Run the full test suite and confirm all tests pass
  - Verify the bug condition exploration tests (task 1 / task 3.7) pass on fixed code
  - Verify the preservation property tests (task 2 / task 3.8) pass on fixed code
  - Ask the user if any questions arise
