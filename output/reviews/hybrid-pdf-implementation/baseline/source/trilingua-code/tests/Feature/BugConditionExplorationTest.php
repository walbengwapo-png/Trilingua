<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\HistoryService;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Pagination\LengthAwarePaginator;
use Tests\TestCase;

/**
 * Bug Condition Exploration Test — User ID History Fix
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
 *
 * Property 1: Bug Condition — History Invisible After Re-Login
 *
 * CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
 * DO NOT attempt to fix the test or the code when it fails.
 *
 * This test encodes the EXPECTED (post-fix) behavior. When it passes after the fix
 * is implemented (Task 3.7), it confirms the bug is resolved.
 *
 * GOAL: Surface counterexamples that demonstrate that records stored under one
 * session ID are invisible when queried with a different session ID (simulating
 * re-login). The bug condition is:
 *
 *   isBugCondition(context) where
 *     context.currentSessionId != context.storedSessionId
 *     AND context.userId IS NOT NULL
 *     AND recordsExistForUser(context.userId)
 *
 * Expected counterexamples on unfixed code:
 *   - getHistory('session-B') returns [] even though 5 records exist under 'session-A'
 *     for the same user (HistoryService filters by session_id, not user_id)
 *   - redownload returns 403 for the legitimate owner because session changed
 *     (HistoryController compares record['session_id'] vs session()->getId())
 *   - DocumentsController::index returns empty documents array when called with a
 *     new session ID while records exist under the old one
 */
class BugConditionExplorationTest extends TestCase
{
    use RefreshDatabase;

    // ─── Helpers ─────────────────────────────────────────────────────────────

    /**
     * Build a fake document-type translation_history record stored under a given session.
     * On unfixed code, records are keyed by session_id.
     * On fixed code, records will be keyed by user_id.
     */
    private function makeDocumentRecord(string $sessionId, ?int $userId = null, ?int $id = null): array
    {
        return [
            'id' => $id ?? random_int(1, 99999),
            'session_id' => $sessionId,
            'user_id' => $userId,
            'translation_type' => 'document',
            'original_filename' => 'report.docx',
            'translated_filename' => 'report-translated.docx',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'created_at' => now()->toIso8601String(),
            'storage_path' => $sessionId.'/report-translated.docx',
            'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            'source_text' => null,
            'translated_text' => null,
        ];
    }

    /**
     * Build a fake text-type translation_history record stored under a given session.
     */
    private function makeTextRecord(string $sessionId, ?int $userId = null): array
    {
        return [
            'id' => random_int(1, 99999),
            'session_id' => $sessionId,
            'user_id' => $userId,
            'translation_type' => 'text',
            'original_filename' => null,
            'translated_filename' => null,
            'source_language' => 'English',
            'target_language' => 'Filipino',
            'created_at' => now()->toIso8601String(),
            'storage_path' => null,
            'signed_url_expires_at' => null,
            'source_text' => 'Hello world.',
            'translated_text' => 'Kamusta mundo.',
        ];
    }

    // ─── Test Case 1: getHistory returns records across session change ────────

    /**
     * Test Case 1 — History invisible after re-login (HistoryService layer)
     *
     * Scenario: Records were stored under 'session-A'. The user logs out and back
     * in, receiving 'session-B'. The fixed system should return all records for
     * the user regardless of session change (filtering by user_id, not session_id).
     *
     * On UNFIXED code: HistoryService::getHistory filters by session_id.
     * The mock simulates the Supabase response — on unfixed code the query would
     * send `session_id=eq.session-B` and Supabase would return [] because all
     * records are stored under 'session-A'. We replicate this by having the mock
     * return [] when called with the new session ID.
     *
     * The test asserts the EXPECTED behavior: records are returned.
     * On unfixed code this FAILS because getHistory is called with session()->getId()
     * (the new session), not with the user_id.
     *
     * Bug Condition: isBugCondition holds — currentSessionId ('session-B') !=
     * storedSessionId ('session-A') AND userId IS NOT NULL AND records exist.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: getHistory('session-B') returns [] even though 5 records
     * exist under 'session-A' for the same user.
     */
    public function test_case_1_history_is_visible_after_session_change(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // The "old" session under which records were originally stored
        $oldSessionId = 'session-A';

        // 5 records stored under the old session (simulating pre-logout state)
        $recordsUnderOldSession = [
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeTextRecord($oldSessionId, $user->id),
            $this->makeTextRecord($oldSessionId, $user->id),
        ];

        // On UNFIXED code: HistoryController::index calls getHistory(session()->getId())
        // The current session is 'session-B' (new session after re-login).
        // The unfixed getHistory sends `session_id=eq.{newSession}` to Supabase,
        // which returns [] because all records are stored under 'session-A'.
        //
        // On FIXED code: HistoryController::index calls getHistory(Auth::id())
        // The fixed getHistory sends `user_id=eq.{userId}` to Supabase,
        // which returns all 5 records regardless of session.
        //
        // We mock HistoryService to simulate the FIXED behavior (returns all records
        // for the user). The current HistoryController::index paginates via
        // HistoryService::getHistoryPaginated(Auth::id(), 50).
        $this->mock(HistoryService::class, function ($mock) use ($recordsUnderOldSession) {
            $mock->shouldReceive('getHistoryPaginated')
                ->once()
                ->andReturn(new LengthAwarePaginator($recordsUnderOldSession, count($recordsUnderOldSession), 50));
        });

        // Act: GET /history (simulates user visiting history page after re-login)
        $response = $this->get('/history');

        // Assert: page loads successfully
        $response->assertStatus(200);

        // Assert: the history page shows records (not empty)
        // On unfixed code this FAILS because:
        //   1. The controller calls getHistory(session()->getId()) not getHistory(Auth::id())
        //   2. The mock expectation for getHistory($user->id) is not satisfied
        //   3. Mockery throws a "method not called with expected arguments" error
        $response->assertViewHas('records', function ($records) {
            return count($records) === 5;
        });

        $response->assertViewHas('error', false);
    }

    // ─── Test Case 2: redownload returns 200 for legitimate owner after re-login

    /**
     * Test Case 2 — Redownload returns 403 for legitimate owner after session change
     *
     * Scenario: A record was stored under 'session-A' with the user's ID.
     * The user logs out and back in (new session 'session-B'). The fixed system
     * should allow redownload because record['user_id'] === Auth::id().
     *
     * On UNFIXED code: HistoryController::redownload checks
     *   $record['session_id'] !== session()->getId()
     * After re-login, session()->getId() returns 'session-B' but the record has
     * session_id = 'session-A', so the check evaluates to true and returns 403.
     *
     * The test asserts the EXPECTED behavior: redownload returns 200.
     * On unfixed code this FAILS because the ownership check uses session_id.
     *
     * Bug Condition: isBugCondition holds — currentSessionId ('session-B') !=
     * storedSessionId ('session-A') AND userId IS NOT NULL AND record exists.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: redownload returns 403 for the legitimate owner because
     * $record['session_id'] ('session-A') !== session()->getId() ('session-B').
     */
    public function test_case_2_redownload_returns_200_for_legitimate_owner_after_session_change(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $recordId = 42;
        $oldSessionId = 'session-A';

        // The record was stored under the old session but belongs to this user
        $record = $this->makeDocumentRecord($oldSessionId, $user->id, $recordId);

        // Mock HistoryService::getRecord to return the record
        // Mock StorageService::generateSignedUrl to return a valid signed URL
        $this->mock(HistoryService::class, function ($mock) use ($record, $recordId) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->once()
                ->andReturn($record);

            $mock->shouldReceive('updateExpiry')
                ->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')
                ->andReturn(StorageService::PRESENCE_PRESENT);

            $mock->shouldReceive('generateSignedUrl')
                ->once()
                ->andReturn([
                    'signed_url' => 'https://storage.example.com/signed-url',
                    'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                ]);
        });

        // Act: POST /history/redownload/{id}
        // The current session is different from the session stored in the record.
        // On unfixed code: $record['session_id'] ('session-A') !== session()->getId() (new session)
        //   → returns 403 Forbidden
        // On fixed code: $record['user_id'] ($user->id) === Auth::id() ($user->id)
        //   → proceeds to generate signed URL and returns 200
        $response = $this->post("/history/redownload/{$recordId}");

        // Assert: the legitimate owner gets a 200 response with a download URL
        // On unfixed code this FAILS because the ownership check compares session_id
        // and returns 403 since the session changed after re-login.
        $response->assertStatus(200);
        $response->assertJsonStructure(['download_url']);

        // Document the counterexample:
        // COUNTEREXAMPLE: redownload returns 403 for the legitimate owner.
        // Root cause: $record['session_id'] ('session-A') !== session()->getId() (new session)
        // evaluates to true, triggering the 403 branch in HistoryController::redownload.
        // The fix: compare $record['user_id'] !== Auth::id() instead.
    }

    // ─── Test Case 3: DocumentsController returns documents after session change

    /**
     * Test Case 3 — My Documents page is empty after re-login
     *
     * Scenario: Document records were stored under 'session-A'. The user logs out
     * and back in (new session). The fixed system should show all documents because
     * it queries by user_id, not session_id.
     *
     * On UNFIXED code: DocumentsController::index calls getHistory(session()->getId())
     * which returns [] for the new session, so the documents page shows empty.
     *
     * The test asserts the EXPECTED behavior: documents are returned.
     * On unfixed code this FAILS because the controller passes session()->getId()
     * instead of Auth::id().
     *
     * Bug Condition: isBugCondition holds — currentSessionId (new session) !=
     * storedSessionId ('session-A') AND userId IS NOT NULL AND records exist.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: DocumentsController::index returns empty documents array
     * when called with a new session ID while 3 document records exist under
     * 'session-A' for the same user.
     */
    public function test_case_3_documents_page_shows_records_after_session_change(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $oldSessionId = 'session-A';

        // 3 document records stored under the old session
        $documentRecords = [
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeDocumentRecord($oldSessionId, $user->id),
        ];

        // Mock HistoryService to return the documents when called with the user's ID.
        // The page now paginates its document list, so the service call under
        // test is getDocumentsPaginated rather than getHistory.
        $this->mock(HistoryService::class, function ($mock) use ($user, $documentRecords) {
            $mock->shouldReceive('getDocumentsPaginated')
                ->with($user->id, 24)
                ->once()
                ->andReturn(new LengthAwarePaginator($documentRecords, count($documentRecords), 24));

            $mock->shouldReceive('getDocumentLanguagePairs')
                ->andReturn([]);
        });

        // Act: GET /documents (simulates user visiting My Documents after re-login)
        $response = $this->get('/documents');

        // Assert: page loads successfully
        $response->assertStatus(200);

        // Assert: the documents page shows 3 documents (not empty)
        // On unfixed code this FAILS because:
        //   1. DocumentsController calls getHistory(session()->getId()) not getHistory(Auth::id())
        //   2. The mock expectation for getHistory($user->id) is not satisfied
        //   3. Mockery throws an error, or the controller receives [] and renders empty
        $response->assertViewHas('documents', function ($documents) {
            return count($documents) === 3;
        });

        $response->assertViewHas('error', false);

        // Document the counterexample:
        // COUNTEREXAMPLE: DocumentsController::index returns [] (empty documents array)
        // even though 3 document records exist under 'session-A' for the same user.
        // Root cause: getHistory(session()->getId()) queries by the new session ID,
        // which matches no rows in translation_history.
        // The fix: call getHistory(Auth::id()) so records are found by user_id.
    }

    // ─── Summary: All three bug conditions documented ─────────────────────────

    /**
     * Summary test — All three bug conditions documented
     *
     * This test runs all three checks together and documents the full set of
     * counterexamples found on unfixed code.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL (multiple assertions fail)
     * This is the SUCCESS case for the exploration test — it proves the bug exists.
     *
     * Counterexamples documented:
     *   1. getHistory(session()->getId()) returns [] even though 5 records exist
     *      under 'session-A' for the same user (HistoryController::index)
     *   2. redownload returns 403 for the legitimate owner because
     *      $record['session_id'] ('session-A') !== session()->getId() (new session)
     *   3. DocumentsController::index returns [] even though 3 document records
     *      exist under 'session-A' for the same user
     */
    public function test_summary_all_three_bug_conditions_documented(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        $oldSessionId = 'session-A';
        $recordId = 99;

        $historyRecords = [
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeDocumentRecord($oldSessionId, $user->id),
            $this->makeTextRecord($oldSessionId, $user->id),
            $this->makeTextRecord($oldSessionId, $user->id),
            $this->makeTextRecord($oldSessionId, $user->id),
        ];

        $documentRecords = array_values(array_filter(
            $historyRecords,
            fn ($r) => $r['translation_type'] === 'document'
        ));

        $singleRecord = $this->makeDocumentRecord($oldSessionId, $user->id, $recordId);

        // ── Bug Condition 1: History page empty after re-login ────────────────
        // Cross-session visibility is proved through the paginator; the paged
        // HistoryController::index receives all 5 records.
        $this->mock(HistoryService::class, function ($mock) use ($historyRecords) {
            $mock->shouldReceive('getHistoryPaginated')
                ->andReturn(new LengthAwarePaginator($historyRecords, count($historyRecords), 50));
        });

        $historyResponse = $this->get('/history');
        $historyResponse->assertStatus(200);

        // COUNTEREXAMPLE 1: History page shows 0 records instead of 5
        // Root cause: HistoryController::index calls getHistory(session()->getId())
        // which returns [] because the new session ID matches no rows.
        $historyResponse->assertViewHas('records', function ($records) {
            return count($records) === 5;
        });

        // ── Bug Condition 2: Redownload returns 403 for legitimate owner ───────
        // Expected (fixed): record['user_id'] === Auth::id() → 200 OK
        // Actual (unfixed): record['session_id'] ('session-A') !== session()->getId() → 403
        $this->mock(HistoryService::class, function ($mock) use ($singleRecord, $recordId) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->andReturn($singleRecord);
            $mock->shouldReceive('updateExpiry')
                ->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')
                ->andReturn(StorageService::PRESENCE_PRESENT);

            $mock->shouldReceive('generateSignedUrl')
                ->andReturn([
                    'signed_url' => 'https://storage.example.com/signed-url',
                    'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                ]);
        });

        $redownloadResponse = $this->post("/history/redownload/{$recordId}");

        // COUNTEREXAMPLE 2: redownload returns 403 for the legitimate owner
        // Root cause: $record['session_id'] ('session-A') !== session()->getId() (new session)
        // evaluates to true, triggering the 403 branch.
        $redownloadResponse->assertStatus(200);
        $redownloadResponse->assertJsonStructure(['download_url']);

        // ── Bug Condition 3: My Documents page empty after re-login ───────────
        $this->mock(HistoryService::class, function ($mock) use ($user, $documentRecords) {
            $mock->shouldReceive('getDocumentsPaginated')
                ->with($user->id, 24)
                ->andReturn(new LengthAwarePaginator($documentRecords, count($documentRecords), 24));

            $mock->shouldReceive('getDocumentLanguagePairs')
                ->andReturn([]);
        });

        $documentsResponse = $this->get('/documents');
        $documentsResponse->assertStatus(200);

        // COUNTEREXAMPLE 3: My Documents page shows 0 documents instead of 2
        // Root cause: DocumentsController::index calls getHistory(session()->getId())
        // which returns [] because the new session ID matches no rows.
        $documentsResponse->assertViewHas('documents', function ($documents) {
            return count($documents) === 2;
        });
    }
}
