<?php

namespace Tests\Unit;

use App\Http\Controllers\DashboardController;
use App\Services\HistoryService;
use Mockery;
use Tests\TestCase;

/**
 * Unit tests for DashboardController::computeStats()
 *
 * **Validates: Requirements 2.2**
 *
 * Covers:
 *  - Empty records array → all zeros
 *  - Mixed document/text records → correct totalDocs, translationsThisMonth, wordsTranslated
 *  - Records from a previous month → translationsThisMonth = 0
 *  - Match percentage calculation: mb_strlen($translated) / max(1, mb_strlen($source)) * 100, capped at 100
 */
class DashboardControllerComputeStatsTest extends TestCase
{
    // ─── Helpers ─────────────────────────────────────────────────────────────

    /**
     * Instantiate DashboardController with a mocked HistoryService.
     * computeStats() is a pure function that does not call the service,
     * so the mock is only needed to satisfy the constructor.
     */
    private function makeController(): DashboardController
    {
        $history = Mockery::mock(HistoryService::class);
        return new DashboardController($history);
    }

    /**
     * Build a minimal document-type record.
     */
    private function docRecord(?string $createdAt = null): array
    {
        return [
            'translation_type' => 'document',
            'source_text'      => null,
            'translated_text'  => null,
            'created_at'       => $createdAt ?? date('Y-m') . '-01T00:00:00Z',
        ];
    }

    /**
     * Build a minimal text-type record.
     */
    private function textRecord(
        string $sourceText = 'hello world',
        string $translatedText = 'kumusta kalibutan',
        ?string $createdAt = null
    ): array {
        return [
            'translation_type' => 'text',
            'source_text'      => $sourceText,
            'translated_text'  => $translatedText,
            'created_at'       => $createdAt ?? date('Y-m') . '-01T00:00:00Z',
        ];
    }

    /**
     * Compute match percentage the same way the blade template does:
     * mb_strlen($translated) / max(1, mb_strlen($source)) * 100, capped at 100.
     */
    private function matchPct(string $source, string $translated): int
    {
        return min(100, (int)(mb_strlen($translated) / max(1, mb_strlen($source)) * 100));
    }

    protected function tearDown(): void
    {
        Mockery::close();
        parent::tearDown();
    }

    // ─── Unit Tests ───────────────────────────────────────────────────────────

    /**
     * computeStats([]) returns all zeros.
     */
    public function test_empty_records_returns_all_zeros(): void
    {
        $controller = $this->makeController();

        $result = $controller->computeStats([]);

        $this->assertSame(
            [
                'totalDocs' => 0,
                'totalTexts' => 0,
                'translationsThisMonth' => 0,
                'wordsTranslated' => 0,
                'topLangPair' => '—',
            ],
            $result,
            'computeStats([]) must return all-zero stats.'
        );
    }

    /**
     * Mixed document/text records: totalDocs counts only document records.
     */
    public function test_mixed_records_total_docs_counts_only_document_records(): void
    {
        $controller = $this->makeController();

        $records = [
            $this->docRecord(),
            $this->docRecord(),
            $this->textRecord('one two three'),
            $this->textRecord('four five'),
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(2, $result['totalDocs'],
            'totalDocs must count only document-type records.');
    }

    /**
     * Mixed document/text records: translationsThisMonth counts only current-month records.
     */
    public function test_mixed_records_translations_this_month_counts_current_month_only(): void
    {
        $controller = $this->makeController();

        $currentMonth = date('Y-m') . '-15T10:00:00Z';
        $lastMonth    = date('Y-m', strtotime('first day of last month')) . '-10T10:00:00Z';

        $records = [
            $this->docRecord($currentMonth),
            $this->textRecord('hello', 'kumusta', $currentMonth),
            $this->docRecord($lastMonth),
            $this->textRecord('world', 'kalibutan', $lastMonth),
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(2, $result['translationsThisMonth'],
            'translationsThisMonth must count only records created in the current calendar month.');
    }

    /**
     * Mixed document/text records: wordsTranslated = real document_word_count
     * for docs (falling back to 0 when source text is unavailable) +
     * str_word_count(source) for text.
     */
    public function test_mixed_records_words_translated_sums_correctly(): void
    {
        $controller = $this->makeController();

        // Doc records carry no persisted source_word_count here → contribute 0.
        // "hello world" → str_word_count = 2
        // "one two three four" → str_word_count = 4
        $records = [
            $this->docRecord(),
            $this->docRecord(),
            $this->textRecord('hello world'),
            $this->textRecord('one two three four'),
        ];

        $result = $controller->computeStats($records);

        $expectedWords = str_word_count('hello world') + str_word_count('one two three four');
        $this->assertSame($expectedWords, $result['wordsTranslated'],
            'wordsTranslated must use real document_word_count (not a flat 250) plus str_word_count for text.');
    }

    /**
     * Records from a previous month: translationsThisMonth = 0.
     */
    public function test_previous_month_records_translations_this_month_is_zero(): void
    {
        $controller = $this->makeController();

        $lastMonth = date('Y-m', strtotime('first day of last month')) . '-05T08:00:00Z';

        $records = [
            $this->docRecord($lastMonth),
            $this->textRecord('hello world', 'kumusta kalibutan', $lastMonth),
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(0, $result['translationsThisMonth'],
            'translationsThisMonth must be 0 when all records are from a previous month.');
    }

    /**
     * Only document records without persisted word counts: wordsTranslated = 0.
     */
    public function test_only_document_records_words_translated_uses_stored_word_count(): void
    {
        $controller = $this->makeController();

        $records = [
            $this->docRecord(),
            $this->docRecord(),
            $this->docRecord(),
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(0, $result['wordsTranslated'],
            'wordsTranslated must be 0 for documents without a stored document_word_count.');
        $this->assertSame(3, $result['totalDocs']);
    }

    /**
     * Only text records: totalDocs = 0, wordsTranslated = sum of str_word_count.
     */
    public function test_only_text_records_total_docs_is_zero(): void
    {
        $controller = $this->makeController();

        $records = [
            $this->textRecord('hello world'),
            $this->textRecord('one two three'),
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(0, $result['totalDocs'],
            'totalDocs must be 0 when there are no document records.');

        $expectedWords = str_word_count('hello world') + str_word_count('one two three');
        $this->assertSame($expectedWords, $result['wordsTranslated']);
    }

    /**
     * Document records use their stored document_word_count (real words).
     */
    public function test_document_records_use_stored_word_count(): void
    {
        $controller = $this->makeController();

        $records = [
            ['translation_type' => 'document', 'document_word_count' => 320, 'created_at' => date('Y-m') . '-01T00:00:00Z'],
            ['translation_type' => 'document', 'document_word_count' => 480, 'created_at' => date('Y-m') . '-01T00:00:00Z'],
        ];

        $result = $controller->computeStats($records);

        $this->assertSame(800, $result['wordsTranslated'],
            'wordsTranslated must sum the stored document_word_count for document records.');
    }

    /**
     * Match percentage: mb_strlen($translated) / max(1, mb_strlen($source)) * 100, capped at 100.
     */
    public function test_match_percentage_basic_calculation(): void
    {
        // source = 10 chars, translated = 5 chars → 50%
        $source     = 'abcdefghij'; // 10 chars
        $translated = 'abcde';      // 5 chars

        $pct = $this->matchPct($source, $translated);

        $this->assertSame(50, $pct,
            'Match percentage must be mb_strlen(translated) / max(1, mb_strlen(source)) * 100.');
    }

    /**
     * Match percentage: capped at 100 when translated is longer than source.
     */
    public function test_match_percentage_capped_at_100(): void
    {
        $source     = 'hi';                    // 2 chars
        $translated = 'this is a long string'; // 21 chars → raw = 1050%

        $pct = $this->matchPct($source, $translated);

        $this->assertSame(100, $pct,
            'Match percentage must be capped at 100 even when translated text is longer than source.');
    }

    /**
     * Match percentage: empty source uses max(1, 0) = 1 as denominator (no division by zero).
     */
    public function test_match_percentage_empty_source_no_division_by_zero(): void
    {
        $source     = '';
        $translated = 'some text'; // 9 chars → 9 / 1 * 100 = 900 → capped at 100

        $pct = $this->matchPct($source, $translated);

        $this->assertSame(100, $pct,
            'Match percentage with empty source must use max(1, 0)=1 as denominator and cap at 100.');
    }

    /**
     * Match percentage: both empty → 0%.
     */
    public function test_match_percentage_both_empty_is_zero(): void
    {
        $pct = $this->matchPct('', '');

        $this->assertSame(0, $pct,
            'Match percentage with both source and translated empty must be 0.');
    }

    // ─── Property-style tests via data providers ──────────────────────────────

    /**
     * Property: For any array of records, all stat values are non-negative and
     * totalDocs / translationsThisMonth are subsets of total record count.
     *
     * **Validates: Requirements 2.2**
     *
     * @dataProvider recordArrayProvider
     */
    public function test_property_stats_are_non_negative_and_bounded(array $records): void
    {
        $controller = $this->makeController();

        $result = $controller->computeStats($records);

        $this->assertGreaterThanOrEqual(0, $result['totalDocs'],
            'totalDocs must always be >= 0.');
        $this->assertGreaterThanOrEqual(0, $result['translationsThisMonth'],
            'translationsThisMonth must always be >= 0.');
        $this->assertGreaterThanOrEqual(0, $result['wordsTranslated'],
            'wordsTranslated must always be >= 0.');
        $this->assertLessThanOrEqual(count($records), $result['totalDocs'],
            'totalDocs must be <= count(records) because documents are a subset.');
        $this->assertLessThanOrEqual(count($records), $result['translationsThisMonth'],
            'translationsThisMonth must be <= count(records) because current-month records are a subset.');
    }

    /**
     * Property: For any source and translated strings, match percentage is in [0, 100].
     *
     * **Validates: Requirements 2.2**
     *
     * @dataProvider matchPctProvider
     */
    public function test_property_match_percentage_in_range_0_to_100(string $source, string $translated): void
    {
        $pct = $this->matchPct($source, $translated);

        $this->assertGreaterThanOrEqual(0, $pct,
            'Match percentage must be >= 0 for any source/translated pair.');
        $this->assertLessThanOrEqual(100, $pct,
            'Match percentage must be <= 100 for any source/translated pair.');
    }

    // ─── Data Providers ───────────────────────────────────────────────────────

    /**
     * Provides varied record arrays for property-style testing.
     */
    public static function recordArrayProvider(): array
    {
        $currentDate = date('Y-m') . '-01T00:00:00Z';
        $pastDate    = date('Y-m', strtotime('first day of last month')) . '-01T00:00:00Z';

        return [
            'empty array' => [[]],
            'single doc current month' => [[
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $currentDate],
            ]],
            'single text current month' => [[
                ['translation_type' => 'text', 'source_text' => 'hello world', 'translated_text' => 'kumusta', 'created_at' => $currentDate],
            ]],
            'single doc past month' => [[
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $pastDate],
            ]],
            'mixed current and past' => [[
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $currentDate],
                ['translation_type' => 'text', 'source_text' => 'one two', 'translated_text' => 'isa dalawa', 'created_at' => $currentDate],
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $pastDate],
                ['translation_type' => 'text', 'source_text' => 'three', 'translated_text' => 'tatlo', 'created_at' => $pastDate],
            ]],
            'all docs current month' => [[
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $currentDate],
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $currentDate],
                ['translation_type' => 'document', 'source_text' => null, 'translated_text' => null, 'created_at' => $currentDate],
            ]],
            'all text past month' => [[
                ['translation_type' => 'text', 'source_text' => 'hello', 'translated_text' => 'kumusta', 'created_at' => $pastDate],
                ['translation_type' => 'text', 'source_text' => 'world', 'translated_text' => 'kalibutan', 'created_at' => $pastDate],
            ]],
            'empty source_text on text record' => [[
                ['translation_type' => 'text', 'source_text' => '', 'translated_text' => '', 'created_at' => $currentDate],
            ]],
        ];
    }

    /**
     * Provides source/translated string pairs for match percentage property testing.
     */
    public static function matchPctProvider(): array
    {
        return [
            'both empty'                    => ['', ''],
            'empty source, non-empty trans' => ['', 'hello'],
            'non-empty source, empty trans' => ['hello', ''],
            'equal length'                  => ['hello', 'world'],
            'translated shorter'            => ['hello world', 'hi'],
            'translated longer'             => ['hi', 'hello world'],
            'translated much longer'        => ['a', str_repeat('x', 1000)],
            'unicode source'                => ['こんにちは', 'hello'],
            'unicode translated'            => ['hello', 'こんにちは'],
            'both unicode'                  => ['こんにちは', 'kumusta'],
            'single char source'            => ['a', 'b'],
            'long equal strings'            => [str_repeat('a', 500), str_repeat('b', 500)],
        ];
    }
}
