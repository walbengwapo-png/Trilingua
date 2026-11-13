<?php

namespace Tests\Feature;

use App\Models\TranslationJob;
use App\Models\User;
use App\Services\TranslationAdmission;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use Tests\TestCase;

class TranslationAdmissionTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        config(['translation.admission_enabled' => true]);
        Http::preventStrayRequests();
    }

    private function admission(): TranslationAdmission { return app(TranslationAdmission::class); }

    private function job(User $user, array $values = []): TranslationJob
    {
        return TranslationJob::create($values + ['user_id' => $user->id, 'payload_hash' => hash('sha256', Str::uuid()),
            'original_name' => 'synthetic.docx', 'original_ext' => '.docx',
            'source_lang' => 'English', 'target_lang' => 'Cebuano', 'status' => 'created']);
    }

    private function requestFor(User $user, string $owner): void
    {
        $request = Request::create('/translate', 'POST');
        $request->attributes->set('translation_admission_owner', $owner);
        $this->app->instance('request', $request);
        $request->setUserResolver(fn () => $user);
    }

    public function test_one_user_cannot_reserve_twice_but_three_other_users_can(): void
    {
        $users = User::factory()->count(4)->create();
        foreach ($users as $user) {
            $lease = $this->admission()->acquire($user->id);
            $this->assertNotNull($lease['owner']);
            $this->assertNull($this->admission()->acquire($user->id)['owner']);
        }
        $this->assertSame(4, DB::table('translation_admissions')->whereNotNull('owner')->count());
    }

    public function test_stale_owner_cannot_release_a_new_reservation(): void
    {
        $user = User::factory()->create();
        $old = $this->admission()->acquire($user->id)['owner'];
        $this->admission()->finishRequest($user->id, $old, false);
        $new = $this->admission()->acquire($user->id)['owner'];
        $this->admission()->finishRequest($user->id, $old, true);
        $this->assertSame($new, DB::table('translation_admissions')->where('user_id', $user->id)->value('owner'));
    }

    public function test_acceptance_rollback_does_not_leave_a_document_binding(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $job = $this->job($user);
        try {
            DB::transaction(function () use ($job): void {
                $this->assertTrue($job->markQueued());
                $this->admission()->bindDocument($job);
                throw new \RuntimeException('Synthetic queue insert failure');
            });
        } catch (\RuntimeException $error) {
            $this->assertSame('Synthetic queue insert failure', $error->getMessage());
        }
        $this->assertSame('intake', DB::table('translation_admissions')->where('user_id', $user->id)->value('phase'));
        $this->assertSame('created', $job->fresh()->status);
        $job->delete();
        $this->admission()->finishRequest($user->id, $owner, false);
        $this->assertNotNull($this->admission()->acquire($user->id)['owner']);
    }

    public function test_queued_document_keeps_admission_and_old_attempt_cannot_release_it(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $job = $this->job($user);
        DB::transaction(function () use ($job): void {
            $job->markQueued();
            $this->admission()->bindDocument($job);
        });
        $this->admission()->finishRequest($user->id, $owner, false);
        $busy = $this->admission()->acquire($user->id);
        $this->assertNull($busy['owner']);
        $this->assertSame($job->uuid, $busy['job_id']);
        $this->assertSame('queued', $busy['status']);
        $job->markProcessing(1);
        $job->update(['status' => 'completed']);
        $this->admission()->finishDocument($job->id, 0);
        $this->assertSame($owner, DB::table('translation_admissions')->where('user_id', $user->id)->value('owner'));
        $this->assertNotNull($this->admission()->acquire($user->id)['owner'], 'Terminal attempt is reconciled on next intake');
    }

    public function test_uncertain_text_is_not_released_by_an_expired_timer(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $this->admission()->beginText();
        $this->admission()->finishRequest($user->id, $owner, false);
        DB::table('translation_admissions')->where('user_id', $user->id)->update(['deadline_at' => now()->subDay()]);
        $busy = $this->admission()->acquire($user->id);
        $this->assertNull($busy['owner']);
        $this->assertSame('recovery_required', $busy['status']);
        $this->admission()->finishRequest($user->id, $owner, true);
        $this->assertNull($this->admission()->acquire($user->id)['owner'], 'Late generic callbacks cannot free uncertain text');
    }

    public function test_confirmed_text_terminal_response_releases_the_matching_owner(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $this->admission()->beginText();
        $this->admission()->finishRequest($user->id, $owner, true);
        $this->assertNotNull($this->admission()->acquire($user->id)['owner']);
    }

    public function test_never_claimed_failed_document_does_not_permanently_reserve_the_user(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $job = $this->job($user);
        DB::transaction(function () use ($job): void {
            $job->markQueued();
            $this->admission()->bindDocument($job);
        });
        $job->update(['status' => 'failed']); // Queue expiry before markProcessing increments the attempt.
        $this->assertNotNull($this->admission()->acquire($user->id)['owner']);
    }

    public function test_failed_php_job_cannot_release_a_running_or_recently_expired_engine(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        $engineId = (string) Str::uuid();
        DB::table('python_document_jobs')->insert(['id' => $engineId, 'fingerprint' => hash('sha256', $engineId),
            'filename' => 'synthetic.docx', 'input_path' => 'synthetic/'.$engineId, 'options' => '{}', 'status' => 'processing']);
        $job = $this->job($user, ['engine_job_uuid' => $engineId]);
        DB::transaction(function () use ($job): void {
            $job->markQueued();
            $this->admission()->bindDocument($job);
        });
        $job->markProcessing(1);
        $job->update(['status' => 'failed']);
        $busy = $this->admission()->acquire($user->id);
        $this->assertSame('recovery_required', $busy['status']);
        $this->assertNull($busy['owner']);
        $this->artisan('translations:admission', ['user' => $user->id, '--release-owner' => $owner, '--drained' => true])->assertFailed();
        DB::table('python_document_jobs')->where('id', $engineId)->update(['status' => 'failed', 'error_status' => 408, 'lease_until' => now()->subSeconds(30)]);
        $this->assertNull($this->admission()->acquire($user->id)['owner']);
        DB::table('python_document_jobs')->where('id', $engineId)->update(['lease_until' => now()->subSeconds(61)]);
        $this->assertNotNull($this->admission()->acquire($user->id)['owner']);
    }

    public function test_busy_http_submission_returns_only_its_owners_job_reference(): void
    {
        $user = User::factory()->create();
        $job = $this->job($user, ['status' => 'queued']);
        $this->actingAs($user)->postJson('/translate', ['text' => 'second request'])
            ->assertStatus(409)->assertJsonPath('job_id', $job->uuid)->assertJsonPath('status', 'queued');
        $other = User::factory()->create();
        $this->actingAs($other)->postJson('/translate', [])
            ->assertStatus(422)->assertJsonMissingPath('job_id');
    }

    public function test_admin_retry_reserves_the_document_owner_rather_than_the_admin(): void
    {
        $user = User::factory()->create();
        $this->job($user, ['status' => 'queued']);
        $failed = $this->job($user, ['status' => 'failed']);
        $admin = User::factory()->create(['is_admin' => true]);
        $this->actingAs($admin)->post(route('admin.translation-jobs.retry', $failed->id))
            ->assertRedirect(route('admin.jobs.index'))->assertSessionHas('status', 'queue-user-already-active');
        $this->assertFalse(DB::table('translation_admissions')->where('user_id', $admin->id)->exists());
    }

    public function test_manual_release_requires_exact_owner_and_drain_confirmation(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        DB::table('translation_admissions')->where('user_id', $user->id)->update(['phase' => 'uncertain']);
        $this->artisan('translations:admission', ['user' => $user->id, '--release-owner' => $owner])->assertFailed();
        $this->artisan('translations:admission', ['user' => $user->id, '--release-owner' => (string) Str::uuid(), '--drained' => true])->assertFailed();
        $this->artisan('translations:admission', ['user' => $user->id, '--release-owner' => $owner, '--drained' => true])->assertSuccessful();
    }

    public function test_proxy_timeout_has_no_terminal_proof_but_python_failure_does(): void
    {
        $user = User::factory()->create();
        $owner = $this->admission()->acquire($user->id)['owner'];
        $this->requestFor($user, $owner);
        Http::fake(['*' => Http::sequence()->push(['detail' => 'Synthetic timeout'], 504)
            ->push(['detail' => 'Synthetic timeout'], 504, ['X-Translation-Terminal' => '1'])]);
        foreach ([false, true] as $expectedTerminal) {
            request()->attributes->remove('translation_text_terminal');
            try {
                app(TranslationManager::class)->translateText(new TranslationRequest('Synthetic', 'English', 'Cebuano'));
                $this->fail('Expected a service failure');
            } catch (\App\Exceptions\TranslationException) {
                $this->assertSame($expectedTerminal, request()->attributes->get('translation_text_terminal') === true);
            }
        }
    }
}
