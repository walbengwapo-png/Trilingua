<?php

namespace Tests\Feature;

use App\Models\User;
use App\Services\HistoryService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Pagination\LengthAwarePaginator;
use Tests\TestCase;

/**
 * Bug Condition Exploration Test — Dashboard UI Fix
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14**
 *
 * Property 1: Bug Condition — Hardcoded Data and Missing UI Elements on All Four Pages
 *
 * CRITICAL: This test MUST FAIL on unfixed code — failure confirms the bug exists.
 * DO NOT attempt to fix the test or the code when it fails.
 *
 * This test encodes the EXPECTED (post-fix) behavior. When it passes after the fix
 * is implemented (Task 3.8), it confirms the bug is resolved.
 *
 * GOAL: Surface counterexamples that demonstrate the bug exists across all four
 * affected pages: Dashboard, New Translation, My Documents, Saved Translations.
 *
 * Scoped PBT Approach: Scope the property to the concrete failing cases below
 * for reproducibility.
 *
 * Expected counterexamples on unfixed code:
 *   - Dashboard renders "24" regardless of seeded record count
 *   - /translate response contains "8000" not "5000"
 *   - No element with id "speak-source-btn" in /translate response
 *   - No elements with class "tab-btn" in /documents response
 *   - No elements with class "history-group" in /history response
 *   - Dashboard greeting does not contain the authenticated user's real name
 */
class DashboardUiFixBugConditionTest extends TestCase
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

    /**
     * Build a fake text-type translation_history record for a given session.
     */
    private function makeTextRecord(string $sessionId, string $sourceLang = 'English', string $targetLang = 'Cebuano', ?string $createdAt = null): array
    {
        return [
            'id' => random_int(1, 99999),
            'session_id' => $sessionId,
            'translation_type' => 'text',
            'original_filename' => null,
            'translated_filename' => null,
            'source_language' => $sourceLang,
            'target_language' => $targetLang,
            'created_at' => $createdAt ?? now()->toIso8601String(),
            'storage_path' => null,
            'signed_url_expires_at' => null,
            'source_text' => 'Hello world this is a test sentence.',
            'translated_text' => 'Kumusta kalibutan kini usa ka pagsulay nga tudling.',
        ];
    }

    // ─── Test Case 1: Dashboard stat cards show real count, not hardcoded "24" ──

    /**
     * Test Case 1 — Dashboard stat cards
     *
     * Seed 3 document records for the session, GET /dashboard, assert response
     * contains "3" (not "24") for Total Documents.
     *
     * Bug Condition: Dashboard renders hardcoded "24" regardless of seeded record count.
     * Expected Behavior: Dashboard renders the real count derived from session records.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: Response contains "24" instead of "3".
     */
    public function test_case_1_dashboard_stat_cards_show_real_count_not_hardcoded(): void
    {
        // Arrange: create and authenticate a user
        $user = User::factory()->create(['name' => 'Test User']);
        $this->actingAs($user);

        // Seed 3 document records via a mocked HistoryService
        $sessionId = session()->getId();
        $records = [
            $this->makeDocumentRecord($sessionId),
            $this->makeDocumentRecord($sessionId),
            $this->makeDocumentRecord($sessionId),
        ];

        // Mock HistoryService to return exactly 3 document records
        $this->mock(HistoryService::class, function ($mock) use ($records) {
            $mock->shouldReceive('getHistory')
                ->once()
                ->andReturn($records);
        });

        // Act: GET /dashboard
        $response = $this->get('/dashboard');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains "3" for Total Documents (real count)
        // On unfixed code this FAILS because the blade hardcodes "24"
        $content = $response->getContent();

        $this->assertStringContainsString(
            '>3<',
            $content,
            'COUNTEREXAMPLE: Dashboard stat card shows hardcoded "24" instead of real count "3". '.
            'The dashboard route renders the view directly without querying HistoryService, '.
            'so the stat card always shows the hardcoded value regardless of actual records.'
        );

        // Also assert the hardcoded value "24" is NOT present as a stat value
        // (it may appear elsewhere, so we check the specific stat card context)
        $this->assertStringNotContainsString(
            '>24<',
            $content,
            'COUNTEREXAMPLE: Dashboard still shows hardcoded "24" — real count "3" was not rendered.'
        );
    }

    // ─── Test Case 2: Dashboard greeting contains the real user name ──────────

    /**
     * Test Case 2 — Dashboard greeting
     *
     * Authenticate as a user named "Maria Santos", GET /dashboard, assert
     * response contains "Maria Santos".
     *
     * Bug Condition: Dashboard greeting shows no real user name.
     * Expected Behavior: Dashboard shows "Welcome back, Maria Santos".
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: Response does not contain "Maria Santos" in the greeting area.
     */
    public function test_case_2_dashboard_greeting_contains_real_user_name(): void
    {
        // Arrange: create and authenticate as "Maria Santos"
        $user = User::factory()->create(['name' => 'Maria Santos']);
        $this->actingAs($user);

        // Mock HistoryService to return empty records (we only care about the greeting)
        $this->mock(HistoryService::class, function ($mock) {
            $mock->shouldReceive('getHistory')
                ->andReturn([]);
        });

        // Act: GET /dashboard
        $response = $this->get('/dashboard');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains the user's real name
        // On unfixed code this FAILS because the dashboard blade has no greeting with the user name
        $response->assertSee('Maria Santos', false);
    }

    // ─── Test Case 3: New Translation counter shows "0/5000" not "0/8000" ─────

    /**
     * Test Case 3 — New Translation counter
     *
     * GET /translate, assert response contains "0/5000" (not "0/8000").
     *
     * Bug Condition: Character counter shows wrong limit "0/8000".
     * Expected Behavior: Counter shows "0/5000" matching the design.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: Response contains "0/8000" instead of "0/5000".
     */
    public function test_case_3_new_translation_counter_shows_5000_limit(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Act: GET /translate
        $response = $this->get('/translate');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains "0/5000" (correct limit)
        // On unfixed code this FAILS because the blade has "0/8000" and MAX_CHARS = 8000
        $response->assertSee('0/5000', false);

        // Also assert "0/8000" is NOT present
        $response->assertDontSee('0/8000', false);
    }

    // ─── Test Case 4: Speaker icons present on New Translation page ───────────

    /**
     * Test Case 4 — Speaker icons
     *
     * GET /translate, assert response contains element with id "speak-source-btn".
     *
     * Bug Condition: Speaker (text-to-speech) icon buttons are absent from both panels.
     * Expected Behavior: Speaker button with id "speak-source-btn" is present in source panel.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: No element with id "speak-source-btn" exists in the response HTML.
     */
    public function test_case_4_speaker_icons_present_on_translate_page(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Act: GET /translate
        $response = $this->get('/translate');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains the speak-source-btn element
        // On unfixed code this FAILS because no speaker buttons exist in the blade
        $response->assertSee('speak-source-btn', false);
    }

    // ─── Test Case 5: My Documents tab filters present ────────────────────────

    /**
     * Test Case 5 — My Documents tab filters
     *
     * GET /documents, assert response contains element with class "tab-btn".
     *
     * Bug Condition: My Documents page has no tab filters (All, Recent, Shared, Archived).
     * Expected Behavior: Tab filter buttons with class "tab-btn" are present.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: No element with class "tab-btn" exists in the response HTML.
     */
    public function test_case_5_my_documents_tab_filters_present(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Mock HistoryService to return some document records so the grid renders
        $sessionId = session()->getId();
        $records = [
            $this->makeDocumentRecord($sessionId),
            $this->makeDocumentRecord($sessionId),
        ];

        $this->mock(HistoryService::class, function ($mock) use ($records) {
            $mock->shouldReceive('getHistory')
                ->once()
                ->andReturn($records);

            // DocumentsController::index also queries originals on the same instance.
            $mock->shouldReceive('getOriginalsWithTranslations')
                ->andReturn([]);
        });

        // Act: GET /documents
        $response = $this->get('/documents');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains an element with class "tab-btn"
        // On unfixed code this FAILS because the my-documents blade has no tab filter markup
        $response->assertSee('tab-btn', false);
    }

    // ─── Test Case 6: History grouping present ────────────────────────────────

    /**
     * Test Case 6 — History grouping
     *
     * GET /history, assert response contains element with class "history-group".
     *
     * Bug Condition: Saved Translations page renders a flat table with no grouping.
     * Expected Behavior: Records are grouped by language pair in sections with class "history-group".
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL
     * Counterexample: No element with class "history-group" exists in the response HTML.
     */
    public function test_case_6_history_grouping_present(): void
    {
        // Arrange: authenticate a user
        $user = User::factory()->create();
        $this->actingAs($user);

        // Mock HistoryService to return some text records with different language pairs
        $sessionId = session()->getId();
        $records = [
            $this->makeTextRecord($sessionId, 'English', 'Cebuano'),
            $this->makeTextRecord($sessionId, 'English', 'Filipino'),
            $this->makeTextRecord($sessionId, 'Cebuano', 'English'),
        ];

        // HistoryController::index paginates via getHistoryPaginated.
        $this->mock(HistoryService::class, function ($mock) use ($records) {
            $mock->shouldReceive('getHistoryPaginated')
                ->once()
                ->andReturn(new LengthAwarePaginator($records, count($records), 50));
        });

        // Act: GET /history
        $response = $this->get('/history');

        // Assert: page loads
        $response->assertStatus(200);

        // Assert: response contains an element with class "history-group"
        // On unfixed code this FAILS because the history blade renders a flat <table>
        $response->assertSee('history-group', false);
    }

    // ─── Bonus: Verify all six bug conditions in a single summary assertion ───

    /**
     * Summary test — All six bug conditions documented
     *
     * This test runs all six checks together and documents the full set of
     * counterexamples found on unfixed code.
     *
     * EXPECTED OUTCOME ON UNFIXED CODE: FAIL (multiple assertions fail)
     * This is the SUCCESS case for the exploration test — it proves the bugs exist.
     */
    public function test_summary_all_six_bug_conditions_documented(): void
    {
        $user = User::factory()->create(['name' => 'Maria Santos']);
        $this->actingAs($user);
        $sessionId = session()->getId();

        $docRecords = [
            $this->makeDocumentRecord($sessionId),
            $this->makeDocumentRecord($sessionId),
            $this->makeDocumentRecord($sessionId),
        ];

        $textRecords = [
            $this->makeTextRecord($sessionId, 'English', 'Cebuano'),
            $this->makeTextRecord($sessionId, 'English', 'Filipino'),
        ];

        // ── Bug 1 & 2: Dashboard ─────────────────────────────────────────────
        $this->mock(HistoryService::class, function ($mock) use ($docRecords) {
            $mock->shouldReceive('getHistory')
                ->andReturn($docRecords);
        });

        $dashResponse = $this->get('/dashboard');
        $dashResponse->assertStatus(200);
        $dashContent = $dashResponse->getContent();

        // Bug 1: stat card shows hardcoded "24" not real count "3"
        $this->assertStringContainsString(
            '>3<',
            $dashContent,
            'BUG 1 CONFIRMED: Dashboard stat card shows hardcoded "24" instead of real count "3". '.
            'Root cause: GET /dashboard route renders view directly without querying HistoryService.'
        );

        // Bug 2: greeting lacks real user name
        $this->assertStringContainsString(
            'Maria Santos',
            $dashContent,
            'BUG 2 CONFIRMED: Dashboard greeting does not contain real user name "Maria Santos". '.
            'Root cause: dashboard.blade.php has no greeting with auth()->user()->name.'
        );

        // ── Bug 3 & 4: New Translation ───────────────────────────────────────
        $translateResponse = $this->get('/translate');
        $translateResponse->assertStatus(200);

        // Bug 3: counter shows "0/8000" not "0/5000"
        $translateResponse->assertSee(
            '0/5000',
            false
        );

        // Bug 4: no speaker icon button
        $translateResponse->assertSee(
            'speak-source-btn',
            false
        );

        // ── Bug 5: My Documents ──────────────────────────────────────────────
        $this->mock(HistoryService::class, function ($mock) use ($docRecords) {
            $mock->shouldReceive('getHistory')
                ->andReturn($docRecords);
        });

        $docsResponse = $this->get('/documents');
        $docsResponse->assertStatus(200);

        // Bug 5: no tab-btn elements
        $docsResponse->assertSee('tab-btn', false);

        // ── Bug 6: History ───────────────────────────────────────────────────
        $this->mock(HistoryService::class, function ($mock) use ($textRecords) {
            $mock->shouldReceive('getHistory')
                ->andReturn($textRecords);
        });

        $historyResponse = $this->get('/history');
        $historyResponse->assertStatus(200);

        // Bug 6: no history-group elements
        $historyResponse->assertSee('history-group', false);
    }
}
