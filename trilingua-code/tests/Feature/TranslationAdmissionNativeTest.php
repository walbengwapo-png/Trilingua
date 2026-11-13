<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\DatabaseMigrations;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

/** PostgreSQL locking and catalog assertions cannot be established using SQLite. */
class TranslationAdmissionNativeTest extends TestCase
{
    use DatabaseMigrations;

    // These additive migrations deliberately refuse destructive rollback. Fresh
    // schemas are safe only inside the guarded disposable native database.
    public function runDatabaseMigrations(): void
    {
        $this->refreshTestDatabase();
        $this->beforeApplicationDestroyed(function (): void {
            \Illuminate\Foundation\Testing\RefreshDatabaseState::$migrated = false;
        });
    }

    protected function setUp(): void
    {
        if (getenv('TRILINGUA_ENGINE_DB_TESTS') !== '1') {
            $this->markTestSkipped('Native loopback PostgreSQL profile required.');
        }
        parent::setUp();
    }

    protected function tearDown(): void
    {
        if (isset($this->app) && $this->app && DB::getSchemaBuilder()->hasTable('translation_admissions')) {
            // Only the guarded disposable database; allow migration rollback after fixtures.
            DB::table('translation_admissions')->update(['owner' => null]);
        }
        parent::tearDown();
    }

    public function test_two_simultaneous_processes_admit_exactly_one_operation_for_a_user(): void
    {
        $user = User::factory()->create(); // Committed: DatabaseMigrations does not wrap tests in a transaction.
        $processes = $pipes = [];
        try {
            for ($i = 0; $i < 2; $i++) {
                $processes[$i] = proc_open([PHP_BINARY, base_path('tests/Integration/acquire-admission.php'), (string) $user->id],
                    [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes[$i], base_path());
                $this->assertIsResource($processes[$i]);
                stream_set_timeout($pipes[$i][1], 10);
                $this->assertSame("READY\n", fgets($pipes[$i][1]));
            }
            foreach ($pipes as $pipe) { fwrite($pipe[0], "GO\n"); fflush($pipe[0]); }
            $leases = [];
            foreach ($pipes as $pipe) { $leases[] = json_decode(fgets($pipe[1]), true, 32, JSON_THROW_ON_ERROR); }
            $this->assertCount(1, array_filter($leases, fn ($lease) => $lease['owner'] !== null));
            $this->assertSame(1, DB::table('translation_admissions')->where('user_id', $user->id)->count());
        } finally {
            foreach ($pipes as $pipe) { foreach ($pipe as $stream) { if (is_resource($stream)) { fclose($stream); } } }
            foreach ($processes as $process) {
                if (is_resource($process)) {
                    if (proc_get_status($process)['running']) { proc_terminate($process); }
                    proc_close($process);
                }
            }
        }
    }

    public function test_admissions_are_internal_and_rls_is_enabled(): void
    {
        $row = DB::selectOne("select relrowsecurity from pg_class where oid='public.translation_admissions'::regclass");
        $this->assertTrue($row->relrowsecurity);
        foreach (['anon', 'authenticated'] as $role) {
            $this->assertFalse(DB::selectOne("select has_table_privilege(?, 'public.translation_admissions', 'SELECT') as allowed", [$role])->allowed);
            $this->assertFalse(DB::selectOne("select has_table_privilege(?, 'public.translation_admissions', 'INSERT') as allowed", [$role])->allowed);
        }
        $this->assertTrue(DB::selectOne("select has_table_privilege('service_role', 'public.translation_admissions', 'UPDATE') as allowed")->allowed);
    }
}
