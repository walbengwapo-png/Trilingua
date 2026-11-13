<?php

namespace Tests\Unit;

use App\Exceptions\TranslationException;
use App\Models\TranslationJob;
use App\Services\Translation\TranslationManager;
use Illuminate\Config\Repository;
use Illuminate\Container\Container;
use Illuminate\Database\Capsule\Manager as Capsule;
use Illuminate\Http\Client\Factory;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Facade;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use PHPUnit\Framework\TestCase;

/** Only mocked HTTP and SQL compilation. No application boot or database connection. */
class ReliabilityHandoffTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        $app = new class extends Container { public function runningUnitTests(): bool { return true; } };
        Container::setInstance($app);
        $app->instance('config', new Repository(['translation' => ['python_service' => [
            'url' => 'http://engine.invalid', 'timeout' => 30, 'token' => 'test-only', 'document_jobs' => true,
        ]]]));
        Facade::setFacadeApplication($app); Facade::clearResolvedInstances();
        Http::swap(new Factory); Http::preventStrayRequests();
        Log::swap(new \Psr\Log\NullLogger);
        $capsule = new Capsule($app);
        $capsule->addConnection(['driver' => 'pgsql', 'host' => '127.0.0.1', 'database' => 'trilingua_engine_test',
            'username' => 'test', 'password' => 'unused']);
        $capsule->setAsGlobal(); $capsule->bootEloquent();
        DB::swap($capsule->getDatabaseManager());
        $pdo = $this->createMock(\PDO::class);
        $pdo->method('quote')->willReturnCallback(fn ($value) => "'".str_replace("'", "''", $value)."'");
        $pdo->method('getAttribute')->willReturnCallback(fn ($attribute) => $attribute === \PDO::ATTR_DRIVER_NAME ? 'pgsql' : '16.0');
        DB::connection()->setPdo($pdo)->setReadPdo($pdo);
    }

    protected function tearDown(): void
    {
        Facade::clearResolvedInstances(); Facade::setFacadeApplication(null); Container::setInstance(null);
        parent::tearDown();
    }

    public function test_python_original_status_and_details_survive_the_laravel_exception(): void
    {
        $details = ['category' => 'credentials', 'original_status' => 401, 'reference_id' => 'reference-1',
            'body_excerpt' => 'Unauthorized', 'requested_model' => 'configured-model'];
        Http::fake(['*' => Http::response(['status' => 'failed', 'error' => 'Safe message. Reference: reference-1',
            'error_status' => 401, 'error_details' => $details])]);
        try {
            (new TranslationManager)->resumeDocumentJob('engine-id');
            $this->fail('Expected a typed translation exception');
        } catch (TranslationException $error) {
            $this->assertSame(401, $error->getCode());
            $this->assertSame($details, $error->errorDetails);
            $job = new TranslationJob(['id' => 3, 'status' => 'processing', 'attempts' => 2]);
            $queries = DB::connection()->pretend(fn () => $job->markTerminallyFailed($error, true));
            $bindings = $queries[0]['bindings'];
            $this->assertContains(json_encode($details), $bindings);
            $this->assertStringContainsString('"attempts" = ', $queries[0]['query']);
        }
        Http::assertSentCount(1);
    }

    public function test_completed_engine_result_resumes_with_get_requests_and_no_generation(): void
    {
        Http::fake([
            '*/engine-id' => Http::response(['status' => 'completed']),
            '*/engine-id/result' => Http::response(['file_base64' => base64_encode('retained-result'),
                'download_filename' => 'translated.txt', 'blocks' => []]),
        ]);
        $manager = new TranslationManager;
        $this->assertSame('completed', $manager->inspectDocumentJob('engine-id')['status']);
        $this->assertSame('retained-result', $manager->resumeDocumentJob('engine-id')['body']);
        Http::assertSentCount(3);
        Http::assertNotSent(fn ($request) => $request->method() !== 'GET');
    }

    public function test_unknown_engine_outcome_never_submits_a_replacement(): void
    {
        Http::fake(['*' => Http::response([], 404)]);
        try {
            (new TranslationManager)->inspectDocumentJob('engine-id');
            $this->fail('Missing engine job must require review');
        } catch (TranslationException $error) {
            $this->assertSame('engine_outcome_unknown', $error->errorDetails['category']);
        }
        Http::assertSentCount(1);
        Http::assertNotSent(fn ($request) => $request->method() !== 'GET');
    }

    public function test_retry_and_execution_queries_are_strict_compare_and_set(): void
    {
        $job = new TranslationJob(['id' => 3, 'status' => 'failed', 'attempts' => 2, 'engine_job_uuid' => 'previous']);
        $queued = DB::connection()->pretend(fn () => $job->markQueued(recovered: true));
        $this->assertStringContainsString('"attempts" = ', $queued[0]['query']);
        $this->assertContains('failed', $queued[0]['bindings']);
        $this->assertNotContains('processing', $queued[0]['bindings']);
        $this->assertStringNotContainsString('"engine_job_uuid" =', $queued[0]['query']);
        $job->status = 'queued';
        $claim = DB::connection()->pretend(fn () => $job->markProcessing(3));
        $this->assertContains('queued', $claim[0]['bindings']);
        $this->assertStringContainsString('"attempts" = attempts + 1', $claim[0]['query']);
        $this->assertSame(2, $claim[0]['bindings'][count($claim[0]['bindings']) - 1]);
    }

    public function test_progress_and_completion_are_fenced_to_the_loaded_attempt(): void
    {
        $job = new TranslationJob(['id' => 3, 'status' => 'processing', 'attempts' => 5]);
        $progress = DB::connection()->pretend(fn () => $job->noteProgress(50));
        $complete = DB::connection()->pretend(fn () => $job->markCompleted('supabase', 'retained', 7));
        foreach ([$progress[0], $complete[0]] as $query) {
            $this->assertStringContainsString('"attempts" = ', $query['query']);
            $this->assertSame(5, $query['bindings'][count($query['bindings']) - 1]);
        }
        $this->assertStringContainsString('"status" = ', $complete[0]['query']);
    }

    public function test_probe_command_never_executes_a_database_release(): void
    {
        Http::fake(['*' => Http::response(['status' => 'validated_awaiting_approval'])]);
        DB::shouldReceive('selectOne')->never();
        try {
            $this->assertSame(0, $this->runRecovery(['--probe' => true]));
            Http::assertSentCount(1);
            Http::assertSent(fn ($request) => str_ends_with($request->url(), '/internal/provider/probe'));
        } finally { \Mockery::close(); }
    }

    public function test_release_command_requires_manifest_hash_and_uses_one_atomic_rpc(): void
    {
        $manifest = ['incident_id' => '11111111-1111-4111-8111-111111111111', 'version' => 2,
            'probe_evidence_id' => '22222222-2222-4222-8222-222222222222',
            'legacy_rows' => array_fill(0, 12, ['id' => 'reviewed-row', 'row_sha256' => 'reviewed-hash'])];
        $bytes = json_encode($manifest, JSON_THROW_ON_ERROR);
        $path = tempnam(sys_get_temp_dir(), 'trilingua-release-'); file_put_contents($path, $bytes);
        DB::shouldReceive('selectOne')->once()->withArgs(fn ($sql, $bindings) =>
            str_contains($sql, 'release_provider_incident_v2') && $bindings[0] === $manifest['incident_id']
            && $bindings[1] === 2 && $bindings[2] === $manifest['probe_evidence_id'])
            ->andReturn((object) ['released' => '{"released_rows":12}']);
        try {
            $this->assertSame(1, $this->runRecovery(['--release-incident' => $path, '--approve-sha256' => 'wrong']));
            $this->assertSame(0, $this->runRecovery(['--release-incident' => $path, '--approve-sha256' => hash('sha256', $bytes)]));
            Http::assertNothingSent();
        } finally { unlink($path); \Mockery::close(); }
    }

    private function runRecovery(array $options): int
    {
        $command = new \App\Console\Commands\ProviderRecover;
        $command->setLaravel(Container::getInstance());
        $input = new \Symfony\Component\Console\Input\ArrayInput([
            'incident' => '11111111-1111-4111-8111-111111111111', 'version' => 2, '--actor' => 'test-operator', ...$options,
        ], $command->getDefinition());
        return $command->run($input, new \Symfony\Component\Console\Output\BufferedOutput);
    }
}
