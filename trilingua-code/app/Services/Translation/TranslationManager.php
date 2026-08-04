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
     * The Python service returns a JSON envelope:
     *   {
     *     "file_base64": "<base64-encoded output file>",
     *     "blocks": [{ "block_index", "block_type", "source_text",
     *                  "ai_translated_text", "current_text", "quality_score",
     *                  "quality_issues", ... }],
     *     "sidecar": { ... },
     *     "download_filename": "...",
     *     "mime_type": "..."
     *   }
     *
     * @return array{body: string, blocks: array, sidecar: ?array, download_filename: string, mime_type: string}
     * @throws TranslationException
     */
    public function translateDocument(
        UploadedFile $file,
        string $sourceLang,
        string $targetLang,
        string $pdfColumnMode = 'auto',
        string $mode = 'balanced',
    ): array {
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
                    'mode' => $mode,
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

            $data = $response->json();
            $elapsedMs = (microtime(true) - $startTime) * 1000;

            // The response is a JSON envelope — decode the base64 file bytes.
            $fileBase64 = $data['file_base64'] ?? '';
            if ($fileBase64 === '') {
                throw new TranslationException(
                    'Python service returned an empty file. The document may be too large or the service may have failed while rebuilding the output.'
                );
            }

            $body = base64_decode($fileBase64, true);
            if ($body === false) {
                throw new TranslationException(
                    'Python service returned an invalid file payload.'
                );
            }

            Log::info('TranslationManager: Document translation completed', [
                'file' => $file->getClientOriginalName(),
                'size' => strlen($body),
                'blocks' => count($data['blocks'] ?? []),
                'execution_time_ms' => $elapsedMs,
            ]);

            // Build output filename
            $stem = pathinfo($file->getClientOriginalName(), PATHINFO_FILENAME);
            $downloadFilename = $data['download_filename'] ?? ($stem . '_translated' . $outExt);

            return [
                'body' => $body,
                'blocks' => $data['blocks'] ?? [],
                'sidecar' => $data['sidecar'] ?? null,
                'download_filename' => $downloadFilename,
                'mime_type' => $data['mime_type'] ?? 'application/octet-stream',
            ];

        } catch (TranslationException $e) {
            throw $e;
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
     * Regenerate an edited document via the Python AI Engine.
     *
     * Reconstruction-only — no extraction, analysis, or translation is
     * re-run. Admin edits (overrides) are replayed onto the original file.
     *
     * @param  string|null $originalBytes  Raw bytes of the ORIGINAL source file
     *                                     (required for PDF and in-place formats).
     * @param  string      $originalName   Original source filename (for extension).
     * @param  array       $sidecar        The sidecar captured at translate time.
     * @param  array       $overrides      {block_index: edited_text}
     * @return array{body: string, download_filename: string, mime_type: string}
     * @throws TranslationException
     */
    public function regenerateDocument(
        ?string $originalBytes,
        string $originalName,
        array $sidecar,
        array $overrides = [],
        string $sourceLang = '',
        string $targetLang = '',
        string $pdfColumnMode = 'auto',
    ): array {
        $startTime = microtime(true);

        try {
            $http = Http::timeout($this->timeout);

            if ($originalBytes !== null && $originalBytes !== '') {
                $http->attach(
                    'file',
                    $originalBytes,
                    $originalName
                );
            } else {
                // Some text formats don't need the original file; the Python
                // endpoint still requires the 'file' field, so send an empty one.
                $http->attach(
                    'file',
                    '',
                    'original.txt'
                );
            }

            $response = $http->post("{$this->pythonUrl}/translate/document/regenerate", [
                'sidecar' => json_encode($sidecar),
                'overrides' => json_encode($overrides),
                'source_lang' => $sourceLang,
                'target_lang' => $targetLang,
                'pdf_column_mode' => $pdfColumnMode,
            ]);

            if ($response->failed()) {
                $errorMessage = $response->json('detail') 
                    ?? $response->json('error') 
                    ?? "Python service returned status {$response->status()}";

                Log::error('TranslationManager: Python document regeneration failed', [
                    'status' => $response->status(),
                    'error' => $errorMessage,
                    'source_lang' => $sourceLang,
                    'target_lang' => $targetLang,
                ]);

                throw new TranslationException($errorMessage, $response->status());
            }

            $body = $response->body();
            $elapsedMs = (microtime(true) - $startTime) * 1000;

            if ($body === '' || $body === false) {
                throw new TranslationException(
                    'The regeneration service returned an empty file.'
                );
            }

            Log::info('TranslationManager: Document regeneration completed', [
                'file' => $originalName,
                'overrides' => count($overrides),
                'size' => strlen($body),
                'execution_time_ms' => $elapsedMs,
            ]);

            // The regenerate endpoint streams the binary file back.
            $ext = strtolower('.' . pathinfo($originalName, PATHINFO_EXTENSION));
            $outExt = config('translation.extension_map.' . ltrim($ext, '.'), $ext);
            $stem = pathinfo($originalName, PATHINFO_FILENAME);
            $downloadFilename = $stem . '_regenerated' . $outExt;

            return [
                'body' => $body,
                'download_filename' => $downloadFilename,
                'mime_type' => $response->header('Content-Type', 'application/octet-stream'),
            ];

        } catch (\Illuminate\Http\Client\ConnectionException $e) {
            Log::error('TranslationManager: Cannot connect to Python service for regeneration', [
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