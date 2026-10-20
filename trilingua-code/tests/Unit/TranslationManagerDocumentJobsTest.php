<?php

namespace Tests\Unit;

use App\Exceptions\TranslationException;
use App\Services\Translation\TranslationManager;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Sleep;
use Tests\TestCase;

class TranslationManagerDocumentJobsTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        config(['translation.python_service.document_jobs' => true,
            'translation.python_service.url' => 'https://engine.example.test',
            'translation.python_service.token' => 'test-service-token']);
        Sleep::fake();
        Http::preventStrayRequests();
    }

    public function test_submission_polls_short_requests_and_preserves_review_data(): void
    {
        $id = 'eaef25cc-fd3f-463b-9e73-db49dab738cd';
        $url = 'https://engine.example.test/translate/document/jobs';
        Http::fake([
            $url => Http::response(['id' => $id, 'status' => 'queued'], 202),
            "$url/$id" => Http::sequence()->push(['status' => 'queued'])->push(['status' => 'processing'])->push(['status' => 'completed']),
            "$url/$id/result" => Http::response(['file_base64' => base64_encode('translated bytes'),
                'blocks' => [['block_index' => 0]], 'sidecar' => ['format' => '.txt'],
                'metrics' => ['provider_usage' => ['request_count' => 2]], 'download_filename' => 'translated.txt']),
        ]);
        $beats = 0;
        $result = app(TranslationManager::class)->translateDocument(UploadedFile::fake()->createWithContent('original.txt', 'source'),
            'English', 'Filipino', engineJobId: $id, heartbeat: function () use (&$beats) { $beats++; });
        $this->assertSame('translated bytes', $result['body']);
        $this->assertSame([['block_index' => 0]], $result['blocks']);
        $this->assertSame(['format' => '.txt'], $result['sidecar']);
        $this->assertSame(3, $beats);
        Http::assertSentCount(5);
        Http::assertSent(fn ($request) => $request->method() === 'POST' && $request->url() === $url
            && collect($request->data())->contains(fn ($field) => ($field['name'] ?? null) === 'job_id' && $field['contents'] === $id));
        Http::assertSent(fn ($request) => $request->hasHeader('X-Service-Token', 'test-service-token'));
    }

    public function test_provider_stop_is_terminal_without_a_second_submission_or_fallback(): void
    {
        Http::fake([
            '*/jobs' => Http::response(['status' => 'queued'], 202),
            '*/jobs/*' => Http::response(['status' => 'failed', 'error_status' => 429, 'error' => 'Provider stopped']),
        ]);
        try {
            app(TranslationManager::class)->translateDocument(UploadedFile::fake()->createWithContent('original.txt', 'source'), 'English', 'Filipino');
            $this->fail('Expected a terminal provider failure');
        } catch (TranslationException $error) {
            $this->assertSame(429, $error->getCode());
        }
        Http::assertSentCount(2);
    }

    public function test_acknowledgement_failure_does_not_remove_a_completed_translation(): void
    {
        Http::fake(['*/jobs/*' => Http::response([], 503)]);
        app(TranslationManager::class)->acknowledgeDocumentJob('eaef25cc-fd3f-463b-9e73-db49dab738cd');
        Http::assertSent(fn ($request) => $request->method() === 'DELETE');
    }

    public function test_polling_auth_failure_is_terminal_and_is_not_reported_as_a_connection_retry(): void
    {
        Http::fake(['*/jobs' => Http::response(['status' => 'queued'], 202),
            '*/jobs/*' => Http::response([], 401)]);
        try {
            app(TranslationManager::class)->translateDocument(UploadedFile::fake()->createWithContent('original.txt', 'source'), 'English', 'Filipino');
            $this->fail('Expected a terminal service authentication failure');
        } catch (TranslationException $error) {
            $this->assertSame(401, $error->getCode());
            $this->assertStringNotContainsString('could not connect', strtolower($error->getMessage()));
        }
        Http::assertSentCount(2);
    }
}
