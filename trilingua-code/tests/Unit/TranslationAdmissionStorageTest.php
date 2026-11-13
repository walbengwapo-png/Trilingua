<?php

namespace Tests\Unit;

use App\Models\TranslationJob;
use App\Services\TranslationAdmission;
use App\Services\Translation\TranslationManager;
use App\Services\Translation\DTO\TranslationRequest;
use Illuminate\Config\Repository;
use Illuminate\Container\Container;
use Illuminate\Database\Capsule\Manager as Capsule;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Http\Request;
use Illuminate\Http\Client\Factory;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Facade;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use PHPUnit\Framework\TestCase;

/** Real in-memory SQL for lifecycle/rollback, without application boot.
 * This does NOT prove PostgreSQL locking, grants, or separate-session races.
 */
class TranslationAdmissionStorageTest extends TestCase
{
    private TranslationAdmission $admission;
    private object $migration;

    protected function setUp(): void
    {
        parent::setUp();
        $app = new Container;
        Container::setInstance($app);
        $app->instance('config', new Repository(['translation' => ['admission_enabled' => true,
            'python_service' => ['document_jobs' => true]], 'timeouts' => ['job' => 1300]]));
        Facade::setFacadeApplication($app);
        Facade::clearResolvedInstances();
        $capsule = new Capsule($app);
        $capsule->addConnection(['driver' => 'sqlite', 'database' => ':memory:', 'prefix' => '', 'foreign_key_constraints' => true]);
        $capsule->setAsGlobal();
        $capsule->bootEloquent();
        DB::swap($capsule->getDatabaseManager());
        Schema::swap(DB::connection()->getSchemaBuilder());
        Schema::create('users', fn (Blueprint $table) => $table->id());
        foreach (range(1, 4) as $user) { DB::table('users')->insert(['id' => $user]); }
        Schema::create('translation_jobs', function (Blueprint $table): void {
            $table->id(); $table->string('uuid'); $table->unsignedBigInteger('user_id');
            $table->string('status'); $table->integer('attempts')->default(0);
            $table->string('engine_job_uuid')->nullable(); $table->timestamps();
        });
        Schema::create('python_document_jobs', function (Blueprint $table): void {
            $table->string('id')->primary(); $table->string('status');
            $table->integer('error_status')->nullable(); $table->timestamp('lease_until')->nullable();
        });
        $this->migration = require dirname(__DIR__, 2).'/database/migrations/2026_11_13_000004_create_translation_admissions.php';
        $this->migration->up();
        $this->admission = new TranslationAdmission;
    }

    protected function tearDown(): void
    {
        DB::disconnect();
        Facade::clearResolvedInstances();
        Facade::setFacadeApplication(null);
        Container::setInstance(null);
        parent::tearDown();
    }

    private function bind(int $user = 1, ?string $engine = null): array
    {
        $owner = $this->admission->acquire($user)['owner'];
        $request = Request::create('/translate', 'POST');
        $request->setUserResolver(fn () => (object) ['id' => $user]);
        $request->attributes->set('translation_admission_owner', $owner);
        app()->instance('request', $request);
        $job = TranslationJob::create(['uuid' => (string) Str::uuid(), 'user_id' => $user,
            'status' => 'queued', 'attempts' => 0, 'engine_job_uuid' => $engine]);
        DB::transaction(fn () => $this->admission->bindDocument($job));
        return [$job, $owner];
    }

    public function test_one_outstanding_operation_per_user_with_independent_other_users(): void
    {
        foreach (range(1, 4) as $user) {
            $this->assertNotNull($this->admission->acquire($user)['owner']);
            $this->assertNull($this->admission->acquire($user)['owner']);
        }
    }

    public function test_queue_retains_owner_then_reconciles_completed_generation(): void
    {
        [$job, $owner] = $this->bind();
        $this->admission->finishRequest(1, $owner, true);
        $busy = $this->admission->acquire(1);
        $this->assertNull($busy['owner']);
        $this->assertSame('queued', $busy['status']);
        $this->assertSame($job->uuid, $busy['job_id']);
        $job->update(['status' => 'completed', 'attempts' => 1]);
        $new = $this->admission->acquire(1)['owner'];
        $this->assertNotNull($new);
        $this->admission->finishRequest(1, $owner, true);
        $this->assertSame($new, DB::table('translation_admissions')->where('user_id', 1)->value('owner'));
    }

    public function test_acceptance_rollback_keeps_intake_releasable(): void
    {
        [$job, $owner] = $this->bind();
        DB::table('translation_admissions')->where('user_id', 1)->update(['phase' => 'intake', 'translation_job_id' => null, 'expected_attempt' => null]);
        try {
            DB::transaction(function () use ($job): void {
                $this->admission->bindDocument($job);
                throw new \RuntimeException('Synthetic failed queue insert');
            });
        } catch (\RuntimeException $error) { $this->assertSame('Synthetic failed queue insert', $error->getMessage()); }
        $this->assertSame('intake', DB::table('translation_admissions')->where('user_id', 1)->value('phase'));
        $job->delete();
        $this->admission->finishRequest(1, $owner, false);
        $this->assertNotNull($this->admission->acquire(1)['owner']);
    }

    public function test_unknown_text_cannot_be_released_by_timeout_or_late_callback(): void
    {
        $owner = $this->admission->acquire(1)['owner'];
        $request = Request::create('/translate', 'POST');
        $request->setUserResolver(fn () => (object) ['id' => 1]);
        $request->attributes->set('translation_admission_owner', $owner);
        app()->instance('request', $request);
        $this->admission->beginText();
        $this->admission->finishRequest(1, $owner, false);
        DB::table('translation_admissions')->where('user_id', 1)->update(['deadline_at' => now()->subDay()]);
        $this->admission->finishRequest(1, $owner, true);
        $this->assertSame('recovery_required', $this->admission->acquire(1)['status']);
        $this->assertNull($this->admission->acquire(1)['owner']);
    }

    public function test_active_engine_and_expiry_safety_window_prevent_readmission(): void
    {
        DB::table('python_document_jobs')->insert(['id' => 'engine', 'status' => 'processing']);
        [$job] = $this->bind(engine: 'engine');
        $this->assertSame('queued', $job->publicStatus());
        $job->update(['status' => 'failed', 'attempts' => 1]);
        $this->assertNull($this->admission->acquire(1)['owner']);
        DB::table('python_document_jobs')->where('id', 'engine')->update(['status' => 'failed', 'error_status' => 408, 'lease_until' => now()->subSeconds(30)]);
        $this->assertNull($this->admission->acquire(1)['owner']);
        DB::table('python_document_jobs')->where('id', 'engine')->update(['lease_until' => now()->subSeconds(61)]);
        $this->assertNotNull($this->admission->acquire(1)['owner']);
    }

    public function test_unclaimed_terminal_job_is_reconciled_but_old_attempt_cannot_release_newer_binding(): void
    {
        [$job] = $this->bind();
        $job->update(['status' => 'failed']);
        $new = $this->admission->acquire(1)['owner'];
        $this->assertNotNull($new);
        DB::table('translation_admissions')->where('user_id', 1)->update(['phase' => 'document', 'translation_job_id' => $job->id, 'expected_attempt' => 2]);
        $job->update(['status' => 'queued', 'attempts' => 1]);
        $this->admission->finishDocument($job->id, 1);
        $this->assertSame($new, DB::table('translation_admissions')->where('user_id', 1)->value('owner'));
    }

    public function test_rollback_refuses_to_discard_an_outstanding_reservation(): void
    {
        $this->admission->acquire(1);
        try { $this->migration->down(); $this->fail('Outstanding admission was dropped'); }
        catch (\RuntimeException $error) { $this->assertSame('Drain/reconcile translation admissions before rollback.', $error->getMessage()); }
        $this->assertSame(1, DB::table('translation_admissions')->count());
    }

    public function test_php_worker_ownership_does_not_hide_the_engine_queue(): void
    {
        DB::table('python_document_jobs')->insert(['id' => 'engine', 'status' => 'queued']);
        [$job] = $this->bind(engine: 'engine');
        $job->update(['status' => 'processing', 'attempts' => 1]);
        $this->assertSame('queued', $job->publicStatus());
        DB::table('python_document_jobs')->where('id', 'engine')->update(['status' => 'processing']);
        $this->assertSame('processing', $job->publicStatus());
    }

    public function test_only_python_terminal_proof_allows_text_release_after_a_failure(): void
    {
        Http::swap(new Factory);
        Http::preventStrayRequests();
        Log::swap(new \Psr\Log\NullLogger);
        config(['translation.python_service.url' => 'http://engine.invalid', 'translation.python_service.timeout' => 30]);
        Http::fake(['*' => Http::sequence()->push(['detail' => 'Synthetic timeout'], 504)
            ->push(['detail' => 'Synthetic timeout'], 504, ['X-Translation-Terminal' => '1'])]);
        $manager = new TranslationManager;
        foreach ([1 => false, 2 => true] as $user => $expectedTerminal) {
            $owner = $this->admission->acquire($user)['owner'];
            $request = Request::create('/translate', 'POST');
            $request->setUserResolver(fn () => (object) ['id' => $user]);
            $request->attributes->set('translation_admission_owner', $owner);
            app()->instance('request', $request);
            $this->admission->beginText();
            try { $manager->translateText(new TranslationRequest('Synthetic', 'English', 'Cebuano')); $this->fail('Expected service failure'); }
            catch (\App\Exceptions\TranslationException) {
                $terminal = $request->attributes->get('translation_text_terminal') === true;
                $this->assertSame($expectedTerminal, $terminal);
                $this->admission->finishRequest($user, $owner, $terminal);
                $this->assertSame($expectedTerminal, $this->admission->acquire($user)['owner'] !== null);
            }
        }
        Http::assertSentCount(2);
    }
}
