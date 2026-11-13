<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\DatabaseMigrations;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use Tests\TestCase;

/** Real PostgreSQL functions; no provider/network calls or production fixtures. */
class ProviderCircuitNativeTest extends TestCase
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
            $this->markTestSkipped('Native PostgreSQL profile required.');
        }
        parent::setUp();
    }

    private function rpc(string $name, array $arguments = [], array $types = []): mixed
    {
        $parameters = implode(',', array_map(fn ($type) => '?::'.$type, $types));
        $value = DB::selectOne('select public.'.$name.'('.$parameters.') as value', $arguments)->value;
        return is_string($value) && str_starts_with($value, '{') ? json_decode($value,true,32,JSON_THROW_ON_ERROR) : $value;
    }

    private function acquire(): array { return $this->rpc('acquire_provider_circuit_v1',['ollama'],['text']); }

    private function finish(array $ticket, ?array $failure): mixed
    {
        return $this->rpc('finish_provider_circuit_v1', ['ollama',$ticket['incident_id'],$ticket['version'],
            $ticket['probe_lease'] ?? null,$failure === null ? null : json_encode($failure),null],
            ['text','uuid','bigint','uuid','jsonb','text']);
    }

    private function openTransient(): void
    {
        $this->assertTrue($this->finish($this->acquire(),['category'=>'upstream_unavailable','original_status'=>503]));
    }

    private function engine(string $status='queued', ?int $errorStatus=null): string
    {
        $id=(string) Str::uuid();
        DB::table('python_document_jobs')->insert(['id'=>$id,'fingerprint'=>hash('sha256',$id),
            'filename'=>'synthetic.txt','input_path'=>'synthetic/'.$id,'options'=>'{}','status'=>$status,
            'error_status'=>$errorStatus,'error'=>$errorStatus ? 'Synthetic historical failure' : null]);
        return $id;
    }

    private function validateManualProbe(): array
    {
        $c=DB::table('provider_circuits')->where('scope','ollama')->first();
        $ticket=$this->rpc('lease_provider_recovery_v1',['ollama',$c->incident_id,$c->version,'native-test'],
            ['text','uuid','bigint','text']);
        $this->assertTrue($ticket['allowed']);
        $models=[['model'=>'gpt-oss:20b','purpose'=>'translation','valid'=>true],
                 ['model'=>'gemma4:31b','purpose'=>'analysis','valid'=>true]];
        $this->assertFalse($this->finish($ticket,null), 'Old manual success path cannot release the stop');
        return $this->rpc('record_provider_probe_v1',['ollama',$ticket['incident_id'],$ticket['version'],
            $ticket['probe_lease'],json_encode($models)],['text','uuid','bigint','uuid','jsonb']);
    }

    private function legacyRows(): array
    {
        return array_map(fn ($row) => (array)$row, DB::select("select j.id,j.created_at,j.updated_at,j.status,j.error,
            j.error_status,j.provider_stop_released,encode(sha256(convert_to(to_jsonb(j)::text,'UTF8')),'hex') as row_sha256
            from public.python_document_jobs j where j.error_status=429 order by j.id"));
    }

    private function release(array $proof,array $rows): mixed
    {
        return $this->rpc('release_provider_incident_v2',[$proof['incident_id'],$proof['version'],
            $proof['probe_evidence_id'],'native-test',json_encode($rows)],['uuid','bigint','uuid','text','jsonb']);
    }

    public function test_hard_stop_is_persistent_and_has_no_timer_release(): void
    {
        $ticket=$this->acquire();
        $this->assertTrue($this->finish($ticket,['category'=>'credentials','original_status'=>401]));
        DB::table('provider_circuits')->where('scope','ollama')->update(['cooldown_until'=>now()->subDay()]);
        DB::purge();
        $blocked=$this->acquire();
        $this->assertFalse($blocked['allowed']);
        $this->assertSame('manual',$blocked['state']);
        $this->assertSame(401,$blocked['original_error']['original_status']);
    }

    public function test_transient_cooldown_one_probe_and_two_failed_automatic_probes_require_review(): void
    {
        $this->openTransient();
        $this->assertFalse($this->acquire()['allowed']);
        DB::table('provider_circuits')->where('scope','ollama')->update(['cooldown_until'=>now()->subSecond()]);
        $first=$this->acquire();
        $this->assertTrue($first['allowed']);
        $this->assertNotNull($first['probe_lease']);
        $this->assertFalse($this->acquire()['allowed']);
        $this->assertTrue($this->finish($first,['category'=>'upstream_unavailable','original_status'=>503]));
        DB::table('provider_circuits')->where('scope','ollama')->update(['cooldown_until'=>now()->subSecond()]);
        $second=$this->acquire();
        $this->assertTrue($second['allowed']);
        $this->assertTrue($this->finish($second,['category'=>'upstream_unavailable','original_status'=>503]));
        $this->assertSame('manual',DB::table('provider_circuits')->value('state'));
        $this->assertFalse($this->acquire()['allowed']);
    }

    public function test_expired_probe_cannot_release_and_another_probe_gets_a_different_lease(): void
    {
        $this->openTransient();
        DB::table('provider_circuits')->where('scope','ollama')->update(['cooldown_until'=>now()->subSecond()]);
        $expired=$this->acquire();
        DB::table('provider_circuits')->where('scope','ollama')->update(['probe_until'=>now()->subSecond()]);
        $this->assertFalse($this->finish($expired,null));
        $next=$this->acquire();
        $this->assertTrue($next['allowed']);
        $this->assertNotSame($expired['probe_lease'],$next['probe_lease']);
    }

    public function test_stale_or_null_incident_cannot_finish_a_newer_incident(): void
    {
        $stale=$this->acquire();
        $this->assertTrue($this->finish($stale,['category'=>'credentials','original_status'=>401]));
        $this->assertFalse($this->finish($stale,null));
        $current=$this->acquire(); $current['incident_id']=null;
        $this->assertFalse($this->finish($current,null));
        $this->assertSame('manual',DB::table('provider_circuits')->value('state'));
    }

    public function test_cancelled_probe_does_not_open_another_incident_or_consume_a_probe(): void
    {
        $this->openTransient();
        DB::table('provider_circuits')->where('scope','ollama')->update(['cooldown_until'=>now()->subSecond()]);
        $ticket=$this->acquire();
        $this->assertTrue($this->rpc('cancel_provider_probe_v1',['ollama',$ticket['incident_id'],$ticket['version'],
            $ticket['probe_lease']],['text','uuid','bigint','uuid']));
        $c=DB::table('provider_circuits')->first();
        $this->assertSame($ticket['incident_id'],$c->incident_id);
        $this->assertSame('open',$c->state);
        $this->assertSame(0,(int)$c->auto_probes);
    }

    public function test_v2_claim_ignores_historical_429_and_preserves_original_finish_details(): void
    {
        $historical=$this->engine('failed',429); $queued=$this->engine();
        $row=DB::selectOne('select * from public.claim_python_document_job_v2()');
        $this->assertSame($queued,$row->id);
        $this->assertTrue($this->rpc('finish_python_document_job_v2',[$queued,$row->lease_id,null,'Safe reference',401,
            json_encode(['category'=>'credentials','original_status'=>401])],['uuid','uuid','text','text','integer','jsonb']));
        $stored=DB::table('python_document_jobs')->where('id',$queued)->first();
        $this->assertSame(401,(int)$stored->error_status);
        $this->assertSame(401,json_decode($stored->error_details,true)['original_status']);
        $this->assertFalse(DB::table('python_document_jobs')->where('id',$historical)->value('provider_stop_released'));
    }

    public function test_hard_stop_blocks_queued_jobs_without_creating_new_incidents(): void
    {
        $this->finish($this->acquire(),['category'=>'billing','original_status'=>402]);
        $before=DB::table('provider_circuits')->first(); $id=$this->engine();
        $this->assertSame([],DB::select('select * from public.claim_python_document_job_v2()'));
        $row=DB::table('python_document_jobs')->where('id',$id)->first();
        $this->assertSame('provider_blocked',json_decode($row->error_details,true)['category']);
        $this->assertSame($before->incident_id,DB::table('provider_circuits')->value('incident_id'));
        $this->assertSame((int)$before->version,(int)DB::table('provider_circuits')->value('version'));
    }

    public function test_validated_manual_probe_stays_stopped_until_atomic_reviewed_release(): void
    {
        $this->finish($this->acquire(),['category'=>'credentials','original_status'=>401]);
        for($i=0;$i<12;$i++) { $this->engine('failed',429); }
        $proof=$this->validateManualProbe(); $rows=$this->legacyRows();
        $this->assertSame('manual',DB::table('provider_circuits')->value('state'));
        $this->assertFalse($this->acquire()['allowed']);
        $result=$this->release($proof,$rows);
        $this->assertSame(12,$result['released_rows']);
        $this->assertSame('closed',DB::table('provider_circuits')->value('state'));
        $this->assertSame(12,DB::table('python_document_jobs')->where('provider_stop_released',true)->count());
        $this->assertSame(array_column($rows,'error'),array_column($this->legacyRows(),'error'));
    }

    public function test_changed_legacy_row_rolls_back_both_release_operations(): void
    {
        $this->finish($this->acquire(),['category'=>'credentials','original_status'=>401]);
        for($i=0;$i<12;$i++) { $this->engine('failed',429); }
        $proof=$this->validateManualProbe(); $rows=$this->legacyRows();
        DB::table('python_document_jobs')->where('id',$rows[0]['id'])->update(['acknowledged'=>true]);
        try { $this->release($proof,$rows); $this->fail('Changed row was released'); }
        catch(\Illuminate\Database\QueryException $error) { $this->assertSame('P0001',(string)$error->getCode()); }
        $this->assertSame('manual',DB::table('provider_circuits')->value('state'));
        $this->assertSame(0,DB::table('python_document_jobs')->where('provider_stop_released',true)->count());
    }

    public function test_all_rpcs_are_service_only_original_rpcs_remain_and_rls_is_enabled(): void
    {
        $checks=[];
        foreach(array_filter(explode(';',file_get_contents(database_path('sql/check_reliability_access.sql')))) as $query) {
            $checks=[...$checks,...DB::select($query)];
        }
        $this->assertNotEmpty($checks);
        $functions=DB::select("select p.oid,p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
            where n.nspname='public' and p.proname in ('claim_python_document_job','renew_python_document_job',
            'finish_python_document_job','finish_python_document_job_v2','claim_python_document_job_v2',
            'acquire_provider_circuit_v1','finish_provider_circuit_v1','lease_provider_recovery_v1',
            'cancel_provider_probe_v1','record_provider_probe_v1','release_legacy_provider_markers_v1','release_provider_incident_v2')");
        $this->assertCount(12,$functions);
        foreach($functions as $function) {
            $access=json_decode(DB::selectOne("select jsonb_build_object('anon',has_function_privilege('anon',?::oid,'EXECUTE'),
                'authenticated',has_function_privilege('authenticated',?::oid,'EXECUTE'),
                'service',has_function_privilege('service_role',?::oid,'EXECUTE'),
                'public',exists(select 1 from aclexplode(coalesce(proacl,acldefault('f',proowner))) a
                    where a.grantee=0 and a.privilege_type='EXECUTE')) as result from pg_proc where oid=?::oid",
                [$function->oid,$function->oid,$function->oid,$function->oid])->result,true);
            $this->assertFalse($access['anon'],$function->proname);
            $this->assertFalse($access['authenticated'],$function->proname);
            $this->assertFalse($access['public'],$function->proname);
            $this->assertTrue($access['service'],$function->proname);
        }
        foreach(['provider_circuits','python_document_jobs'] as $table) {
            $this->assertTrue(DB::selectOne('select relrowsecurity from pg_class where oid=?::regclass',['public.'.$table])->relrowsecurity);
            DB::beginTransaction();
            try { DB::statement('set local role anon'); DB::table($table)->count(); $this->fail('Anonymous table read allowed'); }
            catch(\Illuminate\Database\QueryException $error) { $this->assertSame('42501',(string)$error->getCode()); }
            finally { DB::rollBack(); }
            DB::beginTransaction();
            try { DB::statement('set local role service_role'); $this->assertIsInt(DB::table($table)->count()); }
            finally { DB::rollBack(); }
        }
    }
}
