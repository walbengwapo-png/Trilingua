<?php

namespace Tests\Feature;

use App\Models\TranslationHistory;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

/**
 * POST /history/{id}/rename — rename a document's display filename.
 */
class HistoryRenameTest extends TestCase
{
    use RefreshDatabase;

    private function makeUser(): User
    {
        return User::factory()->create(['is_admin' => false]);
    }

    private function makeDoc(User $user, array $overrides = []): TranslationHistory
    {
        return TranslationHistory::create(array_merge([
            'user_id'             => $user->id,
            'translation_type'    => 'document',
            'original_filename'   => 'contract.pdf',
            'translated_filename' => 'contract_ceb.pdf',
            'source_language'     => 'English',
            'target_language'     => 'Cebuano',
            'original_storage_path' => '1/originals/contract.pdf',
            'status'              => 'completed',
        ], $overrides));
    }

    public function test_owner_can_rename_a_translation_filename(): void
    {
        $user  = $this->makeUser();
        $doc   = $this->makeDoc($user);

        $response = $this->actingAs($user)->postJson("/history/{$doc->id}/rename", [
            'name' => 'Final Agreement',
        ]);

        $response->assertOk();
        $response->assertJson(['success' => true]);
        $this->assertSame('Final Agreement.pdf', $doc->fresh()->translated_filename);
    }

    public function test_rename_preserves_extension(): void
    {
        $user  = $this->makeUser();
        $doc   = $this->makeDoc($user);

        $this->actingAs($user)->postJson("/history/{$doc->id}/rename", [
            'name' => 'agreement',
        ])->assertOk();

        $this->assertSame('agreement.pdf', $doc->fresh()->translated_filename);
    }

    public function test_rename_rejects_a_different_extension(): void
    {
        $user  = $this->makeUser();
        $doc   = $this->makeDoc($user);

        $this->actingAs($user)->postJson("/history/{$doc->id}/rename", [
            'name' => 'agreement.docx',
        ])->assertStatus(422);

        $this->assertSame('contract_ceb.pdf', $doc->fresh()->translated_filename);
    }

    public function test_rename_requires_a_name(): void
    {
        $user  = $this->makeUser();
        $doc   = $this->makeDoc($user);

        $this->actingAs($user)->postJson("/history/{$doc->id}/rename", [
            'name' => '',
        ])->assertStatus(422);
    }

    public function test_rename_renames_original_filename_for_original_documents(): void
    {
        $user = $this->makeUser();
        $doc  = $this->makeDoc($user, ['translated_filename' => null]);

        $this->actingAs($user)->postJson("/history/{$doc->id}/rename", [
            'name' => 'Original Contract',
        ])->assertOk();

        $this->assertSame('Original Contract.pdf', $doc->fresh()->original_filename);
    }

    public function test_rename_is_forbidden_for_another_users_document(): void
    {
        $owner = $this->makeUser();
        $other = $this->makeUser();
        $doc   = $this->makeDoc($owner);

        $this->actingAs($other)->postJson("/history/{$doc->id}/rename", [
            'name' => 'Hijacked',
        ])->assertForbidden();

        $this->assertSame('contract_ceb.pdf', $doc->fresh()->translated_filename);
    }
}
