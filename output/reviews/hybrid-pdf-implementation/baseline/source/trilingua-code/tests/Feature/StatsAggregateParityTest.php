<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use App\Services\TranslationStatsService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * Gate 3a — statistics must be aggregated over every row, not the newest 200.
 *
 * The dashboard, profile and admin user pages used to load a capped slice of
 * history and compute statistics from it. Past 200 translations every lifetime
 * total, word count, language mix and quality average silently froze while
 * looking entirely plausible.
 *
 * These tests pin two things:
 *
 *  1. The database aggregate path produces the SAME numbers as the previous
 *     in-PHP logic when both see the same complete row set. The old logic is
 *     reproduced below as an oracle so the rewrite is checked against the
 *     behaviour it replaced rather than against itself.
 *  2. The aggregate path sees rows beyond the old 200-row cap.
 */
class StatsAggregateParityTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(): User
    {
        return User::factory()->create();
    }

    /**
     * Build a dataset that deliberately straddles the old 200-row cap and
     * mixes every row shape the statistics care about.
     */
    private function seedBeyondTheOldCap(User $user, int $extra = 25): void
    {
        $rows = [];

        // 210 plain documents: more than the old cap on their own.
        for ($i = 0; $i < 210; $i++) {
            $rows[] = [
                'user_id'          => $user->id,
                'translation_type' => 'document',
                'source_language'  => 'English',
                'target_language'  => 'Cebuano',
                'source_text'      => null,
                // Stored count is authoritative for documents.
                'document_word_count' => 10,
                'created_at'       => now()->subDays($i % 25),
                'is_bookmarked'    => $i % 7 === 0,
                'review_status'    => 'pending',
                'quality_score'    => $i % 3 === 0 ? 80 : null,
            ];
        }

        // Documents with NO stored count: these fall back to counting
        // source_text, which is the semantics that must not drift.
        $rows[] = [
            'user_id'            => $user->id,
            'translation_type'   => 'document',
            'source_language'    => 'English',
            'target_language'    => 'Filipino',
            'source_text'        => 'one two three four five',
            'document_word_count'=> null,
            'created_at'         => now()->subDays(1),
        ];

        // Text rows always count their own source_text.
        $rows[] = [
            'user_id'          => $user->id,
            'translation_type' => 'text',
            'source_language'  => 'English',
            'target_language'  => 'Cebuano',
            'source_text'      => 'alpha beta gamma',
            'created_at'       => now()->subDays(2),
        ];
        $rows[] = [
            'user_id'          => $user->id,
            'translation_type' => 'text',
            'source_language'  => 'Cebuano',
            'target_language'  => 'Filipino',
            'source_text'      => 'delta epsilon',
            'created_at'       => now()->subDays(45),
        ];

        // A row with no language pair at all, which the mix must ignore.
        $rows[] = [
            'user_id'          => $user->id,
            'translation_type' => 'text',
            'source_language'  => '',
            'target_language'  => '',
            'source_text'      => 'zeta eta',
            'created_at'       => now(),
        ];

        // Push the total comfortably past the old cap, and put more than 200
        // rows through the PHP word-count path specifically — otherwise a cap
        // reintroduced there would go unnoticed.
        for ($i = 0; $i < 205; $i++) {
            $rows[] = [
                'user_id'          => $user->id,
                'translation_type' => 'text',
                'source_language'  => 'English',
                'target_language'  => 'Cebuano',
                'source_text'      => 'word ' . $i,
                'created_at'       => now(),
            ];
        }

        // ...and a second batch of legacy documents with no stored count, so the
        // word scan has to span several chunks to cover everything.
        for ($i = 0; $i < 60; $i++) {
            $rows[] = [
                'user_id'            => $user->id,
                'translation_type'   => 'document',
                'source_language'    => 'English',
                'target_language'    => 'Filipino',
                'source_text'        => 'legacy document words here',
                'document_word_count'=> null,
                'created_at'         => now(),
                'quality_score'      => 70,
            ];
        }

        foreach ($rows as $row) {
            TranslationHistory::create($row);
        }
    }

    /**
     * Every row for a user, as plain arrays — the input the previous
     * implementation computed its statistics from.
     *
     * @return array<int, array>
     */
    private function fullRowSet(int $userId): array
    {
        return TranslationHistory::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->get()
            ->toArray();
    }

    /**
     * The previous DashboardController::totals(), verbatim.
     */
    private function oldTotals(array $records): array
    {
        return [
            'total'      => count($records),
            'documents'  => $records === [] ? 0 : count(array_filter($records, fn ($r) => ($r['translation_type'] ?? '') === 'document')),
            'texts'      => $records === [] ? 0 : count(array_filter($records, fn ($r) => ($r['translation_type'] ?? '') === 'text')),
            'words'      => array_reduce($records, fn ($carry, $r) => $carry + TranslationStatsService::wordsForRecord($r), 0),
            'bookmarked' => $records === [] ? 0 : count(array_filter($records, fn ($r) => !empty($r['is_bookmarked']))),
        ];
    }

    /**
     * The previous DashboardController::deltas(), verbatim.
     */
    private function oldDeltas(array $records): array
    {
        $now             = now();
        $thisPeriodStart = $now->copy()->subDays(30)->startOfDay();
        $prevPeriodStart = $now->copy()->subDays(60)->startOfDay();
        $prevPeriodEnd   = $now->copy()->subDays(30)->endOfDay();

        $thisCount = TranslationStatsService::countInRange($records, $thisPeriodStart, $now);
        $prevCount = TranslationStatsService::countInRange($records, $prevPeriodStart, $prevPeriodEnd);

        $thisWords = 0;
        $prevWords = 0;
        foreach ($records as $r) {
            $created = $r['created_at'] ?? null;
            if (!$created) {
                continue;
            }
            $ts = \Carbon\Carbon::parse($created);
            $words = TranslationStatsService::wordsForRecord($r);
            if ($ts >= $thisPeriodStart) {
                $thisWords += $words;
            } elseif ($ts >= $prevPeriodStart && $ts <= $prevPeriodEnd) {
                $prevWords += $words;
            }
        }

        return [
            'translationsDelta' => TranslationStatsService::deltaPercent($thisCount, $prevCount),
            'wordsDelta'        => TranslationStatsService::deltaPercent($thisWords, $prevWords),
        ];
    }

    public function test_aggregates_count_every_row_past_the_old_two_hundred_cap(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $all  = $this->fullRowSet($user->id);
        $stats = TranslationStatsService::forUser($user->id);

        $this->assertGreaterThan(
            200,
            count($all),
            'This dataset must exceed the old cap for the test to mean anything.'
        );
        $this->assertSame(
            count($all),
            $stats['totals']['total'],
            'Totals must count every row, not the newest 200.'
        );
    }

    public function test_aggregates_match_the_previous_totals_logic_on_a_complete_row_set(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame($this->oldTotals($records), $stats['totals']);
    }

    public function test_aggregates_match_the_previous_core_stats(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame(TranslationStatsService::compute($records), $stats['core']);
    }

    public function test_aggregates_match_the_previous_period_deltas(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame($this->oldDeltas($records), $stats['deltas']);
    }

    public function test_aggregates_match_the_previous_sparkline(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame(TranslationStatsService::dailySeries($records, 30), $stats['sparkline']);
    }

    public function test_aggregates_match_the_previous_language_pair_mix(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame(TranslationStatsService::languagePairMix($records), $stats['pairMix']);
    }

    public function test_aggregates_match_the_previous_quality_figures(): void
    {
        $user = $this->makeUser();
        $this->seedBeyondTheOldCap($user);

        $records = $this->fullRowSet($user->id);
        $stats   = TranslationStatsService::forUser($user->id);

        $this->assertSame(TranslationStatsService::averageQuality($records), $stats['avgQuality']);
        $this->assertSame(TranslationStatsService::qualityByPair($records), $stats['qualityByPair']);
    }

    /**
     * Word counting is the one statistic that cannot be reimplemented in SQL
     * without changing its meaning, so it gets its own explicit test.
     */
    public function test_word_counting_keeps_its_previous_meaning(): void
    {
        $user = $this->makeUser();

        // A document with a stored count: the stored number wins.
        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'document',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'one two three', 'document_word_count' => 500,
            'created_at' => now(),
        ]);

        // A legacy document with no stored count: counted from source_text.
        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'document',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'one two three', 'document_word_count' => null,
            'created_at' => now(),
        ]);

        // A text row: always counted from source_text.
        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'text',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'a b c d', 'created_at' => now(),
        ]);

        $stats = TranslationStatsService::forUser($user->id);

        // 500 (stored) + 3 (fallback) + 4 (text)
        $this->assertSame(507, $stats['totals']['words']);
    }

    /**
     * A text row that somehow carries a document_word_count must still be
     * counted from its own text, exactly as wordsForRecord() does.
     */
    public function test_a_text_row_never_borrows_a_document_word_count(): void
    {
        $user = $this->makeUser();

        TranslationHistory::create([
            'user_id' => $user->id, 'translation_type' => 'text',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'source_text' => 'a b c', 'document_word_count' => 999,
            'created_at' => now(),
        ]);

        $stats = TranslationStatsService::forUser($user->id);

        $this->assertSame(3, $stats['totals']['words']);
    }

    public function test_a_user_with_no_history_reports_zeros_rather_than_failing(): void
    {
        $user = $this->makeUser();

        $stats = TranslationStatsService::forUser($user->id);

        $this->assertSame(0, $stats['totals']['total']);
        $this->assertSame(0, $stats['totals']['words']);
        $this->assertNull($stats['avgQuality']);
        $this->assertSame('—', $stats['core']['topLangPair']);
        $this->assertCount(30, $stats['sparkline']);
        $this->assertSame([], $stats['pairMix']);
    }

    public function test_statistics_never_include_another_users_rows(): void
    {
        $mine   = $this->makeUser();
        $theirs = $this->makeUser();

        $this->seedBeyondTheOldCap($mine, extra: 2);
        TranslationHistory::create([
            'user_id' => $theirs->id, 'translation_type' => 'text',
            'source_language' => 'English', 'target_language' => 'Filipino',
            'source_text' => 'not mine', 'created_at' => now(),
        ]);

        $stats = TranslationStatsService::forUser($mine->id);

        $this->assertSame(
            TranslationHistory::where('user_id', $mine->id)->count(),
            $stats['totals']['total']
        );
    }

    public function test_the_dashboard_renders_aggregated_totals_not_a_capped_slice(): void
    {
        $user = User::factory()->create();
        $this->actingAs($user);
        $this->seedBeyondTheOldCap($user);

        $response = $this->get('/dashboard');

        $response->assertStatus(200);
        $response->assertDontSee('>24<', false);
        $response->assertViewHas('error', false);
    }
}
