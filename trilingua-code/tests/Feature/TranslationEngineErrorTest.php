<?php

namespace Tests\Feature;

use App\Exceptions\TranslationException;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\TranslationManager;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\TestCase;

class TranslationEngineErrorTest extends TestCase
{
    public static function endpoints(): array
    {
        return [['text'], ['document'], ['regenerate']];
    }

    #[DataProvider('endpoints')]
    public function test_structured_engine_error_preserves_its_message_and_http_code(string $endpoint): void
    {
        $message = 'Saved PDF validation failed: missing rendered text.';
        Http::fake(['*' => Http::response(['detail' => [
            'message' => $message, 'validation' => ['status' => 'failed'],
        ]], 422)]);
        $this->expectException(TranslationException::class);
        $this->expectExceptionMessage($message);
        $this->expectExceptionCode(422);
        $manager = app(TranslationManager::class);
        match ($endpoint) {
            'text' => $manager->translateText(new TranslationRequest('Source', 'English', 'Cebuano')),
            'document' => $manager->translateDocument(
                UploadedFile::fake()->createWithContent('source.pdf', '%PDF-1.4'), 'English', 'Cebuano'),
            'regenerate' => $manager->regenerateDocument('%PDF-1.4', 'source.pdf', []),
        };
    }

    public function test_engine_validation_lists_are_reported_as_text(): void
    {
        $detail = [['loc' => ['body', 'file'], 'msg' => 'Field required']];
        Http::fake(['*' => Http::response(['detail' => $detail], 422)]);
        $this->expectException(TranslationException::class);
        $this->expectExceptionMessage(json_encode($detail));
        app(TranslationManager::class)->translateText(new TranslationRequest('Source', 'English', 'Cebuano'));
    }
}
