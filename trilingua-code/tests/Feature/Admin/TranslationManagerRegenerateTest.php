<?php

namespace Tests\Feature\Admin;

use App\Exceptions\TranslationException;
use App\Services\Translation\TranslationManager;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

/**
 * Regression: the regeneration payload must send `overrides` as a JSON OBJECT
 * ({block_index: edited_text}), never a JSON list. Python's apply_overrides()
 * calls overrides.items(), so a list (what json_encode produces for sequential
 * integer keys) crashes regeneration with "'list' object has no attribute 'items'".
 */
class TranslationManagerRegenerateTest extends TestCase
{
    use RefreshDatabase;

    public function test_hybrid_reply_keeps_binary_file_and_updated_render_plan(): void
    {
        $signed = ['version' => 3, 'signature' => ['algorithm' => 'HMAC-SHA256',
            'purpose' => 'render-plan', 'value' => 'opaque-python-owned-signature']];
        $updated = ['version' => 3, 'render_plan' => $signed + ['native_fit_decisions' => []],
            'content_summary' => ['status' => 'partial', 'translated' => 1, 'held' => 1]];
        Http::fake(['*/translate/document/regenerate' => Http::response([
            'file_base64' => base64_encode('fixed-file-bytes'), 'sidecar' => $updated, 'mime_type' => 'application/pdf',
        ])]);
        $result = app(TranslationManager::class)->regenerateDocument(
            originalBytes: 'original-bytes', originalName: 'contract.pdf',
            sidecar: ['version' => 3, 'render_plan' => $signed, 'content_summary' => $updated['content_summary']], overrides: [],
        );
        $this->assertSame('fixed-file-bytes', $result['body']);
        $this->assertSame($updated, $result['sidecar']);
        $this->assertSame('application/pdf', $result['mime_type']);
        $this->assertSame('contract_regenerated_partial.pdf', $result['download_filename']);
        Http::assertSent(function ($request) use ($signed) {
            foreach ($request->data() as $field) {
                if (is_array($field) && ($field['name'] ?? null) === 'sidecar') {
                    return json_decode($field['contents'], true)['render_plan'] === $signed;
                }
            }
            return false;
        });
    }

    public function test_regenerate_sends_overrides_as_json_object(): void
    {
        Http::fake([
            '*/translate/document/regenerate' => Http::response('fake-file-bytes', 200),
        ]);

        $captured = null;

        Http::assertNothingSent();

        $manager = app(TranslationManager::class);
        $result = $manager->regenerateDocument(
            originalBytes: 'original-bytes',
            originalName: 'contract.pdf',
            sidecar: [
                'format' => '.pdf',
                'blocks' => [
                    ['block_index' => 0, 'text' => 'a', 'current_text' => 'a'],
                    ['block_index' => 1, 'text' => 'b', 'current_text' => 'b'],
                ],
            ],
            overrides: [0 => 'Edited a', 1 => 'Edited b'],
        );

        $this->assertSame('fake-file-bytes', $result['body']);
        $this->assertSame('contract_regenerated.pdf', $result['download_filename']);

        Http::assertSent(function ($request) use (&$captured) {
            if (str_contains($request->url(), '/translate/document/regenerate')) {
                $captured = $request;
                return true;
            }
            return false;
        });

        $this->assertNotNull($captured, 'Expected a regenerate request to be sent.');

        // Multipart form data: extract the overrides field payload.
        $overridesJson = null;
        foreach ($captured->data() as $field) {
            if (is_array($field) && ($field['name'] ?? null) === 'overrides') {
                $overridesJson = $field['contents'] ?? null;
                break;
            }
        }

        $this->assertIsString($overridesJson);
        // The critical guard: overrides must be a JSON OBJECT ({block_index: text}),
        // never a sequential list — otherwise Python's .items() would crash.
        $this->assertStringStartsWith('{', trim($overridesJson), 'overrides must be a JSON object, not a list.');
        $this->assertJson($overridesJson);
        $decoded = json_decode($overridesJson, true);
        $this->assertIsArray($decoded);
        $this->assertArrayHasKey('0', $decoded);
        $this->assertArrayHasKey('1', $decoded);
        $this->assertSame('Edited a', $decoded['0']);
        $this->assertSame('Edited b', $decoded['1']);
    }
}
