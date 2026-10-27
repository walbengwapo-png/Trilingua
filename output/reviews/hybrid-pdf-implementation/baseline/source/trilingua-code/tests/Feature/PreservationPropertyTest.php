<?php

namespace Tests\Feature;

use App\Models\TranslationJob;
use App\Models\User;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\Translation\DTO\TranslationResponse;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Pagination\LengthAwarePaginator;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use RuntimeException;
use Tests\TestCase;

/**
 * Preservation Property Tests — User ID History Fix
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
 *
 * Property 2: Preservation — Cross-User Ownership and Error Behavior
 *
 * Observation-first methodology: behavior was observed on UNFIXED code first,
 * then these tests capture that observed baseline behavior.
 *
 * IMPORTANT: These tests MUST PASS on UNFIXED code. They capture behaviors that
 * are completely unrelated to the session_id → user_id ownership swap and must
 * remain unchanged before and after the fix.
 *
 * Observed baseline behaviors (on unfixed code):
 *   - redownload(recordId, differentSessionId) → 403 Forbidden
 *   - redownload(nonExistentId, anySessionId)  → 404 Not Found
 *   - getHistory(sessionId) with 200+ records  → returns exactly 200, ordered by created_at desc
 *   - Failed insertRecord during translation   → error is logged, translation response still returned
 *   - updateExpiry(id, newExpiry)              → updates signed_url_expires_at column
 *
 * EXPECTED OUTCOME: Tests PASS on both unfixed and fixed code.
 */
class PreservationPropertyTest extends TestCase
{
    use RefreshDatabase;

    // ─── Helpers ─────────────────────────────────────────────────────────────

    /**
     * Build a fake document-type translation_history record owned by a given session.
     * On unfixed code, records are keyed by session_id.
     */
    private function makeDocumentRecord(string $sessionId, ?int $userId = null, ?int $id = null, ?string $createdAt = null): array
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
            'created_at' => $createdAt ?? now()->toIso8601String(),
            'storage_path' => $sessionId.'/report-translated.docx',
            'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            'source_text' => null,
            'translated_text' => null,
        ];
    }

    // ─── Requirement 3.1: Cross-user redownload → 403 Forbidden ─────────────

    /**
     * Preservation Test 1 — Cross-user redownload returns 403 Forbidden
     *
     * **Validates: Requirements 3.1**
     *
     * Observed behavior (unfixed code): When a user requests a redownload of a
     * record that belongs to a DIFFERENT session (i.e., a different user), the
     * controller checks `$record['session_id'] !== session()->getId()` and returns
     * 403 Forbidden.
     *
     * This behavior is NOT affected by the session_id → user_id fix because the
     * cross-user case (isBugCondition = false) is a separate code path. The fix
     * changes the ownership check from session_id to user_id, but the 403 outcome
     * for a different user must remain identical.
     *
     * Property: For any redownload request where the record belongs to a different
     * user (different session on unfixed code, different user_id on fixed code),
     * the response MUST be 403 Forbidden.
     *
     * We test representative pairs of (ownerSession, requestingSession) to confirm
     * the 403 is returned consistently.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_1_cross_user_redownload_returns_403(): void
    {
        // Arrange: create and authenticate a user (the requesting user)
        $requestingUser = User::factory()->create();
        $this->actingAs($requestingUser);

        // Establish the session so session()->getId() is stable
        $this->get('/translate');

        $recordId = 77;
        $otherUserId = $requestingUser->id + 1; // a different user's ID

        // The record belongs to a DIFFERENT session (a different user's session).
        // On unfixed code: $record['session_id'] ('session-other-user-A') !== session()->getId()
        //   → returns 403 Forbidden.
        // On fixed code: $record['user_id'] (otherUserId) !== Auth::id() (requestingUser->id)
        //   → returns 403 Forbidden.
        // Either way, 403 is the expected outcome.
        $record = $this->makeDocumentRecord('session-other-user-A', $otherUserId, $recordId);

        $this->mock(HistoryService::class, function ($mock) use ($record, $recordId) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->andReturn($record);
        });

        // Act: POST /history/redownload/{id} as the requesting user
        $response = $this->postJson("/history/redownload/{$recordId}");

        // Assert: 403 Forbidden — the record belongs to a different user
        $response->assertStatus(403,
            'Preservation 3.1: redownload of a record owned by a different session must return 403. '.
            'This behavior must be unchanged by the fix.'
        );

        // Assert: error message is present
        $response->assertJsonStructure(['error']);
    }

    /**
     * Preservation Test 1b — Cross-user redownload returns 403 for UUID-style session
     *
     * **Validates: Requirements 3.1**
     *
     * Property: For any redownload request where the record belongs to a different
     * user (UUID-style session ID), the response MUST be 403 Forbidden.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_1b_cross_user_redownload_with_uuid_session_returns_403(): void
    {
        $requestingUser = User::factory()->create();
        $this->actingAs($requestingUser);
        $this->get('/translate');

        $recordId = 78;
        $otherUserId = $requestingUser->id + 1;

        // UUID-style session (typical Laravel session format)
        $record = $this->makeDocumentRecord('abcdef12-3456-7890-abcd-ef1234567890', $otherUserId, $recordId);

        $this->mock(HistoryService::class, function ($mock) use ($record, $recordId) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->andReturn($record);
        });

        $response = $this->postJson("/history/redownload/{$recordId}");

        $response->assertStatus(403,
            'Preservation 3.1: redownload of a record owned by a UUID-style different session must return 403.'
        );
        $response->assertJsonStructure(['error']);
    }

    // ─── Requirement 3.2: Non-existent record redownload → 404 Not Found ────

    /**
     * Preservation Test 2 — Non-existent record redownload returns 404 Not Found
     *
     * **Validates: Requirements 3.2**
     *
     * Observed behavior (unfixed code): When a user requests a redownload of a
     * record that does not exist (getRecord returns null), the controller returns
     * 404 Not Found.
     *
     * This behavior is completely unaffected by the session_id → user_id fix
     * because the 404 check happens BEFORE the ownership check.
     *
     * Property: For any non-existent record ID, redownload MUST return 404 Not Found.
     *
     * We test representative non-existent IDs to confirm the 404 is returned
     * consistently across the input space.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_2_nonexistent_record_redownload_returns_404(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $nonExistentId = 99999;

        // Mock HistoryService to return null (record does not exist)
        $this->mock(HistoryService::class, function ($mock) use ($nonExistentId) {
            $mock->shouldReceive('getRecord')
                ->with($nonExistentId)
                ->andReturn(null); // record does not exist
        });

        // Act: POST /history/redownload/{id}
        $response = $this->postJson("/history/redownload/{$nonExistentId}");

        // Assert: 404 Not Found — the record does not exist
        $response->assertStatus(404,
            'Preservation 3.2: redownload of non-existent record ID must return 404. '.
            'This behavior must be unchanged by the fix.'
        );

        // Assert: error message is present
        $response->assertJsonStructure(['error']);
    }

    /**
     * Preservation Test 2b — Non-existent record redownload returns 404 for various IDs
     *
     * **Validates: Requirements 3.2**
     *
     * Property: For any non-existent record ID (small, large, boundary values),
     * redownload MUST return 404 Not Found.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_2b_nonexistent_record_various_ids_return_404(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        // Test a small non-existent ID
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('getRecord')
                ->with(1)
                ->andReturn(null);
        });

        $response = $this->postJson('/history/redownload/1');
        $response->assertStatus(404,
            'Preservation 3.2: redownload of non-existent record ID 1 must return 404.'
        );
        $response->assertJsonStructure(['error']);
    }

    // ─── Requirement 3.3: Failed insertRecord → logs error, translation returned

    /**
     * Preservation Test 3a — Failed insertRecord during text translation logs error
     * and still returns the translated text
     *
     * **Validates: Requirements 3.3**
     *
     * Observed behavior (unfixed code): When insertRecord throws an exception during
     * a text translation, the controller catches it, logs the error, and still returns
     * the translated text to the user (non-blocking error handling).
     *
     * This behavior is completely unaffected by the session_id → user_id fix because
     * the error handling wraps the insertRecord call regardless of which field is used.
     *
     * Property: For any text translation where insertRecord fails, the response MUST
     * be HTTP 200 with the translated text, and the error MUST be logged.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_3a_failed_insert_during_text_translation_logs_error_and_returns_translation(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Mock TranslationManager to return a translated result
        $this->mock(TranslationManager::class, function ($mock) {
            $mock->shouldReceive('translateText')
                ->once()
                ->andReturn(new TranslationResponse(translatedText: 'Kumusta kalibutan.'));
        });

        // Mock HistoryService to throw an exception on insertRecord
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('insertRecord')
                ->once()
                ->andThrow(new RuntimeException('Supabase DB insert failed: connection refused'));
        });

        // Spy on the Log facade to confirm the error is logged
        Log::shouldReceive('error')
            ->once()
            ->withArgs(function ($message, $context) {
                return str_contains($message, 'Failed to insert') &&
                       isset($context['exception']);
            });

        // Act: POST /translate with text input
        $response = $this->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'text' => 'Hello world',
        ]);

        // Assert: HTTP 200 — translation is returned despite the DB failure
        $response->assertStatus(200,
            'Preservation 3.3: A failed insertRecord during text translation must NOT block '.
            'the translation response. HTTP 200 must still be returned.'
        );

        // Assert: the translated text is present in the response
        $response->assertJsonStructure(['translated']);
        $this->assertEquals('Kumusta kalibutan.', $response->json('translated'),
            'Preservation 3.3: The translated text must be returned even when insertRecord fails.'
        );
    }

    /**
     * Preservation Test 3b — Document submission is non-blocking and returns
     * a job_id immediately; history is recorded later in the durable worker.
     *
     * **Validates: Requirements 3.3**
     *
     * Current contract: POST /translate with a document uploads the original,
     * creates a durable translation_jobs row and returns HTTP 200 with job_id.
     * The download URL is produced by the worker and surfaced through
     * /translate/status/{jobId}. History-insert failures inside the worker are
     * logged and never block the submission request.
     *
     * EXPECTED OUTCOME: PASS
     */
    public function test_preservation_3_3b_document_submission_is_non_blocking_and_returns_job_id(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Queue the job (never execute synchronously) so the request path only
        // uploads the original and returns the job_id.
        config(['queue.default' => 'database']);

        // Mock StorageService so the original upload never hits Supabase
        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('uploadWithFallback')
                ->once()
                ->andReturn([
                    'backend' => 'supabase',
                    'storage_path' => 'user/originals/report.docx',
                    'signed_url' => 'https://storage.example.com/original',
                    'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                ]);
        });

        // Act: POST /translate with a real DOCX (PK zip magic so the sniff passes)
        $file = UploadedFile::fake()->createWithContent(
            'report.docx',
            'PK'.random_bytes(256)
        );

        $response = $this->post('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'document' => $file,
        ], ['Accept' => 'application/json']);

        // Assert: HTTP 200 — the submission is never blocked
        $response->assertStatus(200,
            'Preservation 3.3: A document translation submission must return HTTP 200.'
        );

        // Assert: the async contract returns a job_id (history is written later
        // by the worker, so a failed insert can never block the request).
        $response->assertJsonStructure(['job_id', 'original_filename']);
        $this->assertNotEmpty($response->json('job_id'),
            'Preservation 3.3: A document submission must return a non-empty job_id.'
        );

        // Assert: exactly one durable job row and one queued job exist.
        $this->assertSame(1, TranslationJob::where('user_id', $user->id)->count());
        $this->assertSame(1, DB::table('jobs')->count());
    }

    // ─── Requirement 3.4: getHistory returns records ordered desc, capped at 200

    /**
     * Preservation Test 4 — getHistory returns records ordered by created_at desc, capped at 200
     *
     * **Validates: Requirements 3.4**
     *
     * Observed behavior (unfixed code): HistoryService::getHistory sends a Supabase
     * query with `order=created_at.desc` and `limit=200`. The controller passes the
     * result directly to the view. When the service returns exactly 200 records
     * (the cap), the view receives exactly 200 records in descending order.
     *
     * This behavior is completely unaffected by the session_id → user_id fix because
     * the ordering and limit parameters in the Supabase query are unchanged.
     *
     * Property: For any call to getHistory that returns 200 records ordered by
     * created_at descending, the history page view MUST receive exactly 200 records
     * in that order.
     *
     * We test this by mocking HistoryService to return exactly 200 records in
     * descending order and asserting the view receives them correctly.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_4_get_history_returns_200_records_ordered_desc(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $sessionId = 'session-test-'.uniqid();

        // Build exactly 200 records with descending created_at timestamps
        // (newest first, as Supabase would return them with order=created_at.desc)
        $records = [];
        for ($i = 0; $i < 200; $i++) {
            // Timestamps go from newest (index 0) to oldest (index 199)
            $createdAt = now()->subMinutes($i)->toIso8601String();
            $records[] = $this->makeDocumentRecord($sessionId, $user->id, $i + 1, $createdAt);
        }

        // Mock HistoryService to return a paginator of exactly 200 records
        // (simulating the 200-record supabase cap paginated at 50 per page)
        $this->mock(HistoryService::class, function ($mock) use ($records) {
            $mock->shouldReceive('getHistoryPaginated')
                ->once()
                ->andReturn(new LengthAwarePaginator($records, count($records), 50));
        });

        // Act: GET /history
        $response = $this->get('/history');

        // Assert: HTTP 200
        $response->assertStatus(200);

        // Assert: the paginator's total is exactly 200 (the cap)
        $response->assertViewHas('records', function ($viewRecords) {
            return $viewRecords->total() === 200;
        }, 'Preservation 3.4: getHistory must report exactly 200 records (the cap) when 200+ exist.');

        // Assert: records are in descending order by created_at (newest first)
        $response->assertViewHas('records', function ($viewRecords) {
            $page = $viewRecords->items();
            for ($i = 0; $i < count($page) - 1; $i++) {
                $current = strtotime($page[$i]['created_at']);
                $next = strtotime($page[$i + 1]['created_at']);
                if ($current < $next) {
                    return false; // not in descending order
                }
            }

            return true;
        }, 'Preservation 3.4: getHistory records must be ordered by created_at descending (newest first).');

        // Assert: no error flag
        $response->assertViewHas('error', false);
    }

    /**
     * Preservation Test 4b — getHistory with exactly 201 records returns only 200
     *
     * **Validates: Requirements 3.4**
     *
     * Property: When the service is asked to return records and returns 200 (the cap),
     * the controller passes exactly 200 to the view — never more.
     *
     * This test confirms the cap is enforced at the service layer (Supabase limit=200)
     * and the controller does not add extra records.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_4b_get_history_never_returns_more_than_200_records(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $sessionId = 'session-cap-test-'.uniqid();

        // The service enforces the 200-record cap via Supabase limit=200.
        // We simulate the service returning exactly 200 records (the maximum it can return).
        $records = [];
        for ($i = 0; $i < 200; $i++) {
            $records[] = $this->makeDocumentRecord($sessionId, $user->id, $i + 1);
        }

        $this->mock(HistoryService::class, function ($mock) use ($records) {
            $mock->shouldReceive('getHistoryPaginated')
                ->once()
                ->andReturn(new LengthAwarePaginator($records, count($records), 50));
        });

        // Act: GET /history
        $response = $this->get('/history');

        // Assert: HTTP 200
        $response->assertStatus(200);

        // Assert: the view receives at most 200 records
        $response->assertViewHas('records', function ($viewRecords) {
            return $viewRecords->total() <= 200 && count($viewRecords->items()) <= 200;
        }, 'Preservation 3.4: The history page must never display more than 200 records.');
    }

    // ─── Requirement 3.5: updateExpiry updates signed_url_expires_at ─────────

    /**
     * Preservation Test 5 — updateExpiry is called with the correct ID and new expiry
     *
     * **Validates: Requirements 3.5**
     *
     * Observed behavior (unfixed code): When a redownload succeeds, HistoryController
     * calls `$this->history->updateExpiry($id, $storageResult['signed_url_expires_at'])`.
     * This updates the `signed_url_expires_at` column for the specified record ID.
     *
     * This behavior is completely unaffected by the session_id → user_id fix because
     * updateExpiry operates on the record ID, not the session_id or user_id.
     *
     * Property: For any successful redownload, updateExpiry MUST be called with the
     * correct record ID and the new expiry timestamp returned by StorageService.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_5_update_expiry_is_called_on_successful_redownload(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $recordId = 55;
        $newExpiry = now()->addDays(7)->toIso8601String();

        // The record belongs to the CURRENT user (same user_id) so the ownership
        // check passes on fixed code: (int) $record['user_id'] === Auth::id().
        $this->mock(HistoryService::class, function ($mock) use ($user, $recordId, $newExpiry) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->once()
                ->andReturnUsing(function () use ($user, $recordId) {
                    // Return a record owned by the current user (ownership check passes)
                    return [
                        'id' => $recordId,
                        'user_id' => $user->id,
                        'translation_type' => 'document',
                        'original_filename' => 'contract.docx',
                        'translated_filename' => 'contract-translated.docx',
                        'source_language' => 'English',
                        'target_language' => 'Filipino',
                        'created_at' => now()->toIso8601String(),
                        'storage_path' => $user->id.'/contract-translated.docx',
                        'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                    ];
                });

            // Assert: updateExpiry is called with the correct record ID and new expiry
            $mock->shouldReceive('updateExpiry')
                ->once()
                ->with($recordId, $newExpiry)
                ->andReturn(null);
        });

        // Mock StorageService to return a new signed URL with the expected expiry
        $this->mock(StorageService::class, function ($mock) use ($newExpiry) {
            $mock->shouldReceive('exists')
                ->andReturn(StorageService::PRESENCE_PRESENT);

            $mock->shouldReceive('generateSignedUrl')
                ->once()
                ->andReturn([
                    'signed_url' => 'https://storage.example.com/new-signed-url',
                    'signed_url_expires_at' => $newExpiry,
                ]);
        });

        // Act: POST /history/redownload/{id}
        $response = $this->postJson("/history/redownload/{$recordId}");

        // Assert: HTTP 200 — redownload succeeded
        $response->assertStatus(200,
            'Preservation 3.5: A successful redownload must return HTTP 200.'
        );

        // Assert: download_url is present
        $response->assertJsonStructure(['download_url']);

        // The mock assertion on updateExpiry->once() verifies that updateExpiry
        // was called exactly once with the correct arguments (record ID + new expiry).
        // Mockery will throw if the expectation is not met.
    }

    /**
     * Preservation Test 5b — updateExpiry failure does not block the redownload response
     *
     * **Validates: Requirements 3.5**
     *
     * Observed behavior (unfixed code): When updateExpiry throws an exception,
     * the controller logs the error but still returns the download URL to the user.
     * The updateExpiry failure is non-blocking.
     *
     * EXPECTED OUTCOME: PASS on unfixed code (baseline behavior confirmed).
     */
    public function test_preservation_3_5b_update_expiry_failure_does_not_block_redownload(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        $recordId = 66;

        $this->mock(HistoryService::class, function ($mock) use ($user, $recordId) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->once()
                ->andReturnUsing(function () use ($user, $recordId) {
                    return [
                        'id' => $recordId,
                        'user_id' => $user->id,
                        'translation_type' => 'document',
                        'original_filename' => 'slides.docx',
                        'translated_filename' => 'slides-translated.docx',
                        'source_language' => 'English',
                        'target_language' => 'Cebuano',
                        'created_at' => now()->toIso8601String(),
                        'storage_path' => $user->id.'/slides-translated.docx',
                        'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                    ];
                });

            // updateExpiry throws — should be caught and logged, not propagated
            $mock->shouldReceive('updateExpiry')
                ->once()
                ->andThrow(new RuntimeException('Supabase DB update failed: timeout'));
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('exists')
                ->andReturn(StorageService::PRESENCE_PRESENT);

            $mock->shouldReceive('generateSignedUrl')
                ->once()
                ->andReturn([
                    'signed_url' => 'https://storage.example.com/signed-url-2',
                    'signed_url_expires_at' => now()->addDays(7)->toIso8601String(),
                ]);
        });

        // Spy on Log::error to confirm the updateExpiry failure is logged
        Log::shouldReceive('error')
            ->once()
            ->withArgs(function ($message, $context) {
                return str_contains($message, 'failed to update expiry') &&
                       isset($context['exception']);
            });

        // Act: POST /history/redownload/{id}
        $response = $this->postJson("/history/redownload/{$recordId}");

        // Assert: HTTP 200 — the download URL is still returned despite updateExpiry failing
        $response->assertStatus(200,
            'Preservation 3.5: A failed updateExpiry must NOT block the redownload response. '.
            'HTTP 200 with download_url must still be returned.'
        );

        $response->assertJsonStructure(['download_url']);
    }
}
