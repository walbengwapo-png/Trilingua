<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\TranslationJob;
use App\Models\User;
use App\Services\StorageService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class DocumentBugFixesTest extends TestCase
{
    use RefreshDatabase;

    public function test_empty_admin_status_lists_all_jobs_and_explicit_filters_work(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        foreach (['processing', 'completed'] as $status) {
            TranslationJob::create(['user_id' => $admin->id, 'payload_hash' => hash('sha256', $status),
                'status' => $status, 'original_name' => $status.'.pdf', 'original_ext' => '.pdf',
                'source_lang' => 'English', 'target_lang' => 'Cebuano']);
        }
        $this->actingAs($admin)->get('/admin/jobs?status=')->assertOk()
            ->assertViewHas('jobs', fn ($jobs) => $jobs->total() === 2);
        $this->get('/admin/jobs?status=processing')->assertOk()
            ->assertViewHas('jobs', fn ($jobs) => $jobs->total() === 1 && $jobs->first()->status === 'processing');
        $this->get('/admin/jobs?q=completed')->assertOk()
            ->assertViewHas('jobs', fn ($jobs) => $jobs->total() === 1);
        $this->getJson('/admin/jobs?status=invalid')->assertUnprocessable();
    }

    public function test_markdown_download_is_attachment_but_preview_stays_inline_and_owner_only(): void
    {
        $owner = User::factory()->create();
        $record = TranslationHistory::create(['user_id' => $owner->id, 'translation_type' => 'document',
            'original_filename' => 'input.md', 'translated_filename' => 'Cebuano "notes".md',
            'source_language' => 'English', 'target_language' => 'Cebuano',
            'status' => 'completed', 'storage_path' => 'owner/out.md', 'storage_backend' => 'local']);
        $body = "# Mga nota\n\n- Maayong adlaw\n```php\necho 'test';\n```\n";
        $this->mock(StorageService::class, fn ($m) => $m->shouldReceive('read')->twice()
            ->with('local', 'owner/out.md')->andReturn($body));
        $download = $this->actingAs($owner)->get('/history/'.$record->id.'/file?download=1')->assertOk()
            ->assertHeader('Content-Type', 'text/plain; charset=UTF-8')
            ->assertStreamedContent($body);
        $this->assertStringStartsWith('attachment;', $download->headers->get('Content-Disposition'));
        $this->assertStringContainsString('filename*=UTF-8', $download->headers->get('Content-Disposition'));
        $preview = $this->get('/history/'.$record->id.'/file')->assertOk()->assertStreamedContent($body);
        $this->assertStringStartsWith('inline;', $preview->headers->get('Content-Disposition'));
        $this->actingAs(User::factory()->create())->get('/history/'.$record->id.'/file?download=1')->assertForbidden();
    }

    public function test_only_matching_engine_revision_is_eligible_for_completed_reuse(): void
    {
        $record = new TranslationHistory(['sidecar' => null]);
        $this->assertFalse($record->hasReusableArtifact());
        $record->sidecar = ['engine_revision' => 'old'];
        $this->assertFalse($record->hasReusableArtifact());
        $record->sidecar = ['engine_revision' => config('translation.result_revision')];
        $this->assertTrue($record->hasReusableArtifact());
        $record->sidecar = ['engine_revision' => config('translation.result_revision'),
            'content_summary' => ['status' => 'untranslated']];
        $this->assertFalse($record->hasReusableArtifact());
    }

    public function test_completed_job_discloses_partial_content_separately(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        $history = TranslationHistory::create(['user_id' => $admin->id, 'translation_type' => 'document',
            'source_language' => 'English', 'target_language' => 'Cebuano', 'status' => 'completed',
            'sidecar' => ['content_summary' => ['status' => 'partial']]]);
        TranslationJob::create(['user_id' => $admin->id, 'payload_hash' => hash('sha256', 'partial'),
            'status' => 'completed', 'original_name' => 'partial.pdf', 'original_ext' => '.pdf',
            'source_lang' => 'English', 'target_lang' => 'Cebuano', 'translation_history_id' => $history->id]);
        $this->actingAs($admin)->get('/admin/jobs')->assertOk()->assertSee('Partly translated')
            ->assertSee('Job status')->assertSee('Translation content');
    }
}
