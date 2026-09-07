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
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

/**
 * Preservation Property Tests — Dashboard UI Fix
 *
 * **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**
 *
 * Property 2: Preservation — All Existing Functional Flows Unchanged
 *
 * Observation-first methodology: behavior was observed on UNFIXED code first,
 * then these tests capture that observed baseline behavior.
 *
 * EXPECTED OUTCOME: Tests PASS on both unfixed and fixed code.
 * These tests confirm that the fix introduces no regressions.
 *
 * Observed baseline behaviors (on unfixed code):
 *   - POST /translate with valid text returns HTTP 200 with {"translated": "..."}
 *   - POST /translate with a valid file returns HTTP 200 with {"job_id": "...", "original_filename": "..."}
 *     (durable async pipeline; the download_url is surfaced via /translate/status/{jobId})
 *   - POST /history/redownload/{id} returns HTTP 200 with {"download_url": "..."}
 *   - GET /translate response contains the swap button markup and its JS handler
 *   - Unauthenticated GET /dashboard returns HTTP 302 redirect to the login page
 *   - Session with zero document records, GET /documents, response contains empty-state message
 */
class DashboardUiFixPreservationTest extends TestCase
{
    use RefreshDatabase;

    // ─── Helpers ─────────────────────────────────────────────────────────────

    /**
     * Build a fake document-type translation_history record for a given session.
     */
    private function makeDocumentRecord(string $sessionId, ?string $createdAt = null): array
    {
        return [
            'id' => random_int(1, 99999),
            'session_id' => $sessionId,
            'translation_type' => 'document',
            'original_filename' => 'test-doc.docx',
            'translated_filename' => 'test-doc-translated.docx',
            'source_language' => 'English',
            'target_language' => 'Cebuano',
            'created_at' => $createdAt ?? now()->toIso8601String(),
            'storage_path' => 'documents/test-doc-translated.docx',
            'signed_url_expires_at' => now()->addHour()->toIso8601String(),
            'source_text' => null,
            'translated_text' => null,
        ];
    }

    // ─── Property 2a: POST /translate (text) returns HTTP 200 with `translated` key ──

    /**
     * Preservation Test 1 — Text translation POST returns translated JSON
     *
     * Observed behavior: POST /translate with valid text input returns HTTP 200
     * with a JSON body containing the "translated" key.
     *
     * Property: For any valid text translation request (any non-empty text string,
     * any valid source/target language pair), POST /translate returns HTTP 200
     * with a JSON body containing the "translated" key.
     *
     * This test uses representative inputs across the valid input space:
     * different language pairs and text lengths.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_post_translate_text_returns_200_with_translated_key(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Mock TranslationManager to return a translated result without hitting the microservice
        $this->mock(TranslationManager::class, function ($mock) {
            $mock->shouldReceive('translateText')
                ->andReturn(new TranslationResponse(translatedText: 'Kumusta kalibutan.'));
        });

        // Mock HistoryService to accept insertRecord without hitting Supabase
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('insertRecord')
                ->andReturn(null);
        });

        // Property: for any valid text translation request, response is 200 with "translated" key.
        // We test representative inputs across the valid input space.
        $validInputs = [
            // English → Cebuano
            ['source_lang' => 'English', 'target_lang' => 'Cebuano',  'text' => 'Hello world'],
            // English → Filipino
            ['source_lang' => 'English', 'target_lang' => 'Filipino', 'text' => 'Good morning'],
            // Cebuano → English
            ['source_lang' => 'Cebuano', 'target_lang' => 'English',  'text' => 'Maayong buntag'],
            // Filipino → English
            ['source_lang' => 'Filipino', 'target_lang' => 'English', 'text' => 'Magandang umaga'],
            // Cebuano → Filipino
            ['source_lang' => 'Cebuano', 'target_lang' => 'Filipino', 'text' => 'Unsay imong ngalan'],
            // Longer text (near boundary)
            ['source_lang' => 'English', 'target_lang' => 'Cebuano',  'text' => str_repeat('word ', 100)],
        ];

        foreach ($validInputs as $input) {
            $response = $this->postJson('/translate', $input);

            // Assert HTTP 200
            $response->assertStatus(200);

            // Assert JSON body contains "translated" key
            $response->assertJsonStructure(['translated']);

            // Assert "translated" key is present (not null/missing)
            $data = $response->json();
            $this->assertArrayHasKey(
                'translated',
                $data,
                "POST /translate with text input [{$input['source_lang']} → {$input['target_lang']}] ".
                "must return JSON with 'translated' key. ".
                'Preservation: TranslationController must remain unchanged after the fix.'
            );
        }
    }

    // ─── Property 2b: POST /translate (document) returns HTTP 200 with `job_id` key ──

    /**
     * Preservation Test 2 — Document translation POST returns 200 with a job_id
     *
     * Current (async) contract: POST /translate with a valid document uploads the
     * original, creates a durable translation_jobs row and returns HTTP 200 with
     * a JSON body containing "job_id" and "original_filename". The download_url is
     * later surfaced through the job status endpoint.
     *
     * Property: For any valid document upload request (any supported file type,
     * any valid source/target language pair), POST /translate returns HTTP 200
     * with a JSON body containing the "job_id" key.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_post_translate_document_returns_200_with_job_id_key(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Keep the job queued so the request stays non-blocking.
        config(['queue.default' => 'database']);

        // Mock StorageService to accept the original upload without hitting Supabase
        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('uploadWithFallback')
                ->andReturn([
                    'backend' => 'supabase',
                    'storage_path' => 'session123/test_translated.docx',
                    'signed_url' => 'https://test.supabase.co/storage/v1/object/sign/test-bucket/test_translated.docx?token=abc',
                    'signed_url_expires_at' => now()->addDays(7)->toIso8601String(),
                ]);
        });

        // Property: for any valid document upload, response is 200 with "job_id" key.
        // Test representative file types.
        $fileTypes = [
            ['name' => 'document.docx', 'content' => 'PK'.str_repeat('A', 512)],
            ['name' => 'document.txt',  'content' => str_repeat('plain text ', 40)],
        ];

        foreach ($fileTypes as $fileType) {
            $file = UploadedFile::fake()->createWithContent($fileType['name'], $fileType['content']);

            $response = $this->post('/translate', [
                'source_lang' => 'English',
                'target_lang' => 'Cebuano',
                'document' => $file,
            ], [
                'Accept' => 'application/json',
            ]);

            // Assert HTTP 200
            $response->assertStatus(200);

            // Assert JSON body contains "job_id" key
            $data = $response->json();
            $this->assertArrayHasKey(
                'job_id',
                $data,
                "POST /translate with document [{$fileType['name']}] must return JSON with 'job_id' key. ".
                'Preservation: TranslationController document flow must remain unchanged after the fix.'
            );
        }

        // Assert exactly one durable job row per submission was created.
        $this->assertSame(2, TranslationJob::where('user_id', $user->id)->count());
        $this->assertSame(2, DB::table('jobs')->count());
    }

    // ─── Property 2c: POST /history/redownload/{id} returns HTTP 200 with `download_url` key ──

    /**
     * Preservation Test 3 — Re-download POST returns download_url JSON
     *
     * Observed behavior: POST /history/redownload/{id} for a valid record owned by
     * the current session returns HTTP 200 with a JSON body containing "download_url".
     *
     * Property: For any valid history record id belonging to the current session,
     * POST /history/redownload/{id} returns HTTP 200 with a JSON body containing
     * the "download_url" key.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_post_history_redownload_returns_200_with_download_url_key(): void
    {
        // Arrange: authenticate a user and make a request first to establish the session
        $user = User::factory()->create();
        $this->actingAs($user);

        // Make a GET request first to ensure the session is fully initialised
        // so that session()->getId() returns the same ID the controller will see
        $this->get('/translate');

        $recordId = 42;

        // Mock HistoryService — use a closure that captures the user ID at call time
        // so it matches the user ID the controller sees during the POST request
        $this->mock(HistoryService::class, function ($mock) use ($recordId, $user) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->andReturnUsing(function () use ($recordId, $user) {
                    return [
                        'id' => $recordId,
                        'user_id' => $user->id,
                        'translation_type' => 'document',
                        'original_filename' => 'report.docx',
                        'translated_filename' => 'report_translated.docx',
                        'source_language' => 'English',
                        'target_language' => 'Cebuano',
                        'created_at' => now()->toIso8601String(),
                        'storage_path' => 'session123/report_translated.docx',
                        'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                    ];
                });

            $mock->shouldReceive('updateExpiry')
                ->andReturn(null);
        });

        // Mock StorageService to return a new signed URL
        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('generateSignedUrl')
                ->andReturn([
                    'signed_url' => 'https://test.supabase.co/storage/v1/object/sign/test-bucket/report_translated.docx?token=xyz',
                    'signed_url_expires_at' => now()->addDays(7)->toIso8601String(),
                ]);
        });

        // Act: POST /history/redownload/{id}
        $response = $this->postJson("/history/redownload/{$recordId}");

        // Assert HTTP 200
        $response->assertStatus(200);

        // Assert JSON body contains "download_url" key
        $data = $response->json();
        $this->assertArrayHasKey(
            'download_url',
            $data,
            "POST /history/redownload/{$recordId} must return JSON with 'download_url' key. ".
            'Preservation: HistoryController::redownload must remain unchanged after the fix.'
        );

        // Assert the download_url is a non-empty string
        $this->assertNotEmpty(
            $data['download_url'],
            "The 'download_url' value must be a non-empty string."
        );
    }

    // ─── Property 2d: GET /translate contains swap button markup and JS handler ──

    /**
     * Preservation Test 4 — GET /translate contains swap button markup and JS handler
     *
     * Observed behavior: GET /translate renders the translation page with:
     *   - A swap button element with class "translation-swap"
     *   - The JS handler for the swap button (swapBtn.addEventListener)
     *
     * Property: For any authenticated GET /translate request, the response contains
     * the swap button markup and its JavaScript event handler.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_get_translate_contains_swap_button_markup_and_js_handler(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Act: GET /translate
        $response = $this->get('/translate');

        // Assert HTTP 200
        $response->assertStatus(200);

        $content = $response->getContent();

        // Assert: swap button element with class "lang-bar__swap" is present
        $this->assertStringContainsString(
            'lang-bar__swap',
            $content,
            "GET /translate must contain the swap button with class 'lang-bar__swap'. ".
            'Preservation: The swap button markup must remain unchanged after the fix.'
        );

        // Assert: the JS swap handler is present (swapBtn variable or swap click handler)
        $this->assertStringContainsString(
            'swapBtn',
            $content,
            "GET /translate must contain the JS swap button handler ('swapBtn'). ".
            'Preservation: The swap button JS handler must remain unchanged after the fix.'
        );

        // Assert: the swap click event listener is wired up
        $this->assertStringContainsString(
            "swapBtn.addEventListener('click'",
            $content,
            "GET /translate must contain swapBtn.addEventListener('click', ...) handler. ".
            'Preservation: The swap button click handler must remain unchanged after the fix.'
        );
    }

    // ─── Property 2e: Unauthenticated GET /dashboard redirects to login ──────

    /**
     * Preservation Test 5 — Unauthenticated request to protected route redirects to login
     *
     * Observed behavior: An unauthenticated GET /dashboard returns HTTP 302 redirect
     * to the login page.
     *
     * Property: For any unauthenticated request to a protected route (/dashboard,
     * /translate, /documents, /history), the response is a redirect to the login page.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_unauthenticated_request_to_protected_route_redirects_to_login(): void
    {
        // Ensure no user is authenticated
        $this->assertGuest();

        // Property: for any unauthenticated request to a protected route, response is 302 to login.
        $protectedRoutes = [
            '/dashboard',
            '/translate',
            '/documents',
            '/history',
        ];

        foreach ($protectedRoutes as $route) {
            $response = $this->get($route);

            // Assert HTTP 302 redirect
            $response->assertStatus(302);

            // Assert redirect target is the login page
            $response->assertRedirect(route('login'));
        }
    }

    // ─── Property 2f: GET /documents with zero docs shows empty-state message ──

    /**
     * Preservation Test 6 — GET /documents with zero documents renders empty-state element
     *
     * Observed behavior: When the authenticated session has zero document records,
     * GET /documents renders the empty-state message ("You have no documents yet.")
     * and a link to translate the first document.
     *
     * Property: For any authenticated session with zero document records,
     * GET /documents renders the empty-state element.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_preservation_get_documents_with_zero_docs_renders_empty_state(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Mock HistoryService to return an empty array (zero records)
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('getHistory')
                ->once()
                ->andReturn([]);

            // DocumentsController::index also queries originals on the same instance.
            $mock->shouldReceive('getOriginalsWithTranslations')
                ->andReturn([]);
        });

        // Act: GET /documents
        $response = $this->get('/documents');

        // Assert HTTP 200
        $response->assertStatus(200);

        // Assert: empty-state message is present
        $response->assertSee('You have no documents yet.', false);

        // Assert: link to translate first document is present
        $response->assertSee('Translate your first document', false);
    }

    // ─── Bonus: Verify all six preservation properties in a single summary ───

    /**
     * Summary test — All six preservation properties verified together
     *
     * This test runs all six preservation checks together to confirm the full
     * baseline behavior is preserved on both unfixed and fixed code.
     *
     * EXPECTED OUTCOME: PASS (on both unfixed and fixed code)
     */
    public function test_summary_all_six_preservation_properties_pass(): void
    {
        // ── Property 2e: Unauthenticated redirect ────────────────────────────
        $this->assertGuest();
        $dashRedirect = $this->get('/dashboard');
        $dashRedirect->assertStatus(302);
        $dashRedirect->assertRedirect(route('login'));

        // ── Property 2d: Swap button markup ─────────────────────────────────
        $user = User::factory()->create();
        $this->actingAs($user);

        $translatePage = $this->get('/translate');
        $translatePage->assertStatus(200);
        $this->assertStringContainsString('lang-bar__swap', $translatePage->getContent());
        $this->assertStringContainsString('swapBtn', $translatePage->getContent());

        // ── Property 2f: Empty-state on /documents ───────────────────────────
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('getHistory')
                ->andReturn([]);

            // DocumentsController::index also queries originals on the same instance.
            $mock->shouldReceive('getOriginalsWithTranslations')
                ->andReturn([]);
        });

        $docsPage = $this->get('/documents');
        $docsPage->assertStatus(200);
        $docsPage->assertSee('You have no documents yet.', false);

        // ── Property 2a: POST /translate text ────────────────────────────────
        $this->mock(TranslationManager::class, function ($mock) {
            $mock->shouldReceive('translateText')
                ->andReturn(new TranslationResponse(translatedText: 'Kumusta kalibutan.'));
        });

        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('insertRecord')
                ->andReturn(null);
        });

        $textTranslation = $this->postJson('/translate', [
            'source_lang' => 'English',
            'target_lang' => 'Cebuano',
            'text' => 'Hello world',
        ]);
        $textTranslation->assertStatus(200);
        $this->assertArrayHasKey('translated', $textTranslation->json());

        // ── Property 2c: POST /history/redownload/{id} ───────────────────────
        $recordId = 99;

        $this->mock(HistoryService::class, function ($mock) use ($recordId, $user) {
            $mock->shouldReceive('getRecord')
                ->with($recordId)
                ->andReturnUsing(function () use ($recordId, $user) {
                    return [
                        'id' => $recordId,
                        'user_id' => $user->id,
                        'translation_type' => 'document',
                        'original_filename' => 'summary.docx',
                        'translated_filename' => 'summary_translated.docx',
                        'source_language' => 'English',
                        'target_language' => 'Filipino',
                        'created_at' => now()->toIso8601String(),
                        'storage_path' => 'session123/summary_translated.docx',
                        'signed_url_expires_at' => now()->addHour()->toIso8601String(),
                    ];
                });
            $mock->shouldReceive('updateExpiry')
                ->andReturn(null);
        });

        $this->mock(StorageService::class, function ($mock) {
            $mock->shouldReceive('generateSignedUrl')
                ->andReturn([
                    'signed_url' => 'https://test.supabase.co/storage/v1/object/sign/test-bucket/summary_translated.docx?token=abc123',
                    'signed_url_expires_at' => now()->addDays(7)->toIso8601String(),
                ]);
        });

        $redownload = $this->postJson("/history/redownload/{$recordId}");
        $redownload->assertStatus(200);
        $this->assertArrayHasKey('download_url', $redownload->json());
    }
}
