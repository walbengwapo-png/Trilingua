<?php

namespace App\Services\Translation;

use App\Exceptions\TranslationException;
use App\Services\Translation\DTO\TranslationRequest;
use App\Services\Translation\DTO\TranslationResponse;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * TranslationManager — Laravel's ONLY translation entry point.
 * 
 * Responsibilities:
 * - Validate requests
 * - Upload document to storage
 * - Call Python AI Engine
 * - Wait for result
 * - Store history
 * - Return response
 * 
 * Laravel NEVER knows:
 * - which AI provider is being used
 * - how chunking works
 * - how prompts work
 * - how context works
 * - how reconstruction works
 */
class TranslationManager
{
    private string $pythonUrl;
    private int $timeout;

    public function __construct()
    {
        $this->pythonUrl = rtrim(config('translation.python_service.url', 'http://127.0.0.1:5000'), '/');
        $this->timeout = (int) config('translation.python_service.timeout', 600);
    }

    /**
     * Translate a text string via the Python AI Engine.
     *
     * @throws TranslationException
     */
    public function translateText(TranslationRequest $request): TranslationResponse
    {
        $startTime = microtime(true);

        try {
            $response = Http::timeout($this->timeout)
                ->post("{$this->pythonUrl}/translate/text", $request->toArray());

            if ($response->failed()) {
                $errorMessage = $response->json('detail') 
                    ?? $response->json('error') 
                    ?? "Python service returned status {$response->status()}";
                
                Log::error('TranslationManager: Python text translation failed', [
                    'status' => $response->status(),
                    'error' => $errorMessage,
                    'source_lang' => $request->sourceLang,
                    'target_lang' => $request->targetLang,
                ]);

                throw new TranslationException($errorMessage, $response->status());
            }

            $data = $response->json();
            $elapsedMs = (microtime(true) - $startTime) * 1000;

            Log::info('TranslationManager: Text translation completed', [
                'provider' => $data['provider'] ?? 'unknown',
                'model' => $data['model'] ?? 'unknown',
                'execution_time_ms' => $data['execution_time_ms'] ?? $elapsedMs,
                'token_usage' => $data['token_usage'] ?? [],
            ]);

            return TranslationResponse::fromArray($data);

        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('TranslationManager: Cannot connect to Python service', [
                'url' => $this->pythonUrl,
                'error' => $e->getMessage(),
            ]);
            throw new TranslationException(
                'Could not connect to the translation service. Make sure it is running: python Model/server.py'
            );
        }
    }

    /**
     * Translate a document via the Python AI Engine.
     *
     * @throws TranslationException
     */
    public function translateDocument(UploadedFile $file, string $sourceLang, string $targetLang, string $pdfColumnMode = 'auto'): array
    {
        $ext = strtolower('.' . $file->getClientOriginalExtension());
        $outExt = config('translation.extension_map.' . ltrim($ext, '.'), $ext);

        $startTime = microtime(true);

        try {
            $response = Http::timeout($this->timeout)
                ->attach(
                    'file',
                    file_get_contents($file->getRealPath()),
                    $file->getClientOriginalName()
                )
                ->post("{$this->pythonUrl}/translate/document", [
                    'source_lang' => $sourceLang,
                    'target_lang' => $targetLang,
                    'pdf_column_mode' => $pdfColumnMode,
                ]);

            if ($response->failed()) {
                $errorMessage = $response->json('detail') 
                    ?? $response->json('error') 
                    ?? "Python service returned status {$response->status()}";

                Log::error('TranslationManager: Python document translation failed', [
                    'status' => $response->status(),
                    'error' => $errorMessage,
                    'source_lang' => $sourceLang,
                    'target_lang' => $targetLang,
                ]);

                throw new TranslationException($errorMessage, $response->status());
            }

            // The response is the translated file binary
            $body = $response->body();
            $elapsedMs = (microtime(true) - $startTime) * 1000;

            Log::info('TranslationManager: Document translation completed', [
                'file' => $file->getClientOriginalName(),
                'size' => strlen($body),
                'execution_time_ms' => $elapsedMs,
            ]);

            // Build output filename
            $stem = pathinfo($file->getClientOriginalName(), PATHINFO_FILENAME);
            $downloadFilename = $stem . '_translated' . $outExt;

            return [
                'body' => $body,
                'download_filename' => $downloadFilename,
                'mime_type' => $response->header('Content-Type', 'application/octet-stream'),
            ];

        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('TranslationManager: Cannot connect to Python service for document', [
                'url' => $this->pythonUrl,
                'error' => $e->getMessage(),
            ]);
            throw new TranslationException(
                'Could not connect to the translation service. Make sure it is running: python Model/server.py'
            );
        }
    }

    /**
     * Check the health of the Python AI Engine.
     */
    public function health(): array
    {
        try {
            $response = Http::timeout(5)->get("{$this->pythonUrl}/health");
            if ($response->successful()) {
                return $response->json();
            }
            return ['status' => 'unavailable', 'error' => "HTTP {$response->status()}"];
        } catch (\Exception $e) {
            return ['status' => 'unavailable', 'error' => $e->getMessage()];
        }
    }

    /**
     * Get the output filename based on original filename and extension.
     */
    public function getOutputFilename(string $originalName, string $ext): string
    {
        $outExt = config('translation.extension_map.' . ltrim($ext, '.'), $ext);
        $stem = pathinfo($originalName, PATHINFO_FILENAME);
        return $stem . '_translated.' . $outExt;
    }
}