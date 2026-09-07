<?php

namespace App\Services;

use GuzzleHttp\Client;
use GuzzleHttp\Exception\ConnectException;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class StorageService
{
    public const BACKEND_SUPABASE = 'supabase';
    public const BACKEND_LOCAL = 'local';

    /**
     * Signed URL expiry in seconds (7 days).
     */
    public const SIGNED_URL_EXPIRY_SECONDS = 604800;

    public function __construct(private Client $guzzle) {}

    /**
     * Upload a local file to the primary backend (Supabase) with retries.
     *
     * @param  string $localPath   Absolute path to the file on disk.
     * @param  string $storagePath Destination path inside the bucket, e.g. "{uid}/translations/{uuid}.docx".
     * @return array{storage_path: string, signed_url: string, signed_url_expires_at: string}
     * @throws \RuntimeException when every primary attempt fails.
     */
    public function uploadFile(string $localPath, string $storagePath): array
    {
        $lastMessage = 'unknown error';
        $retried = retry(3, function () use ($localPath, $storagePath, &$lastMessage) {
            try {
                return $this->uploadFileOnce($localPath, $storagePath);
            } catch (\Throwable $e) {
                $lastMessage = $e->getMessage();
                throw $e;
            }
        }, 1000);

        if ($retried === false) {
            throw new \RuntimeException('Supabase Storage upload failed after retries: ' . $lastMessage);
        }

        return $retried;
    }

    /**
     * Upload translated output durably: primary backend with retries, and if
     * every primary attempt fails, the durable fallback backend. The service
     * NEVER falls back to the queue node's local scratch space as the final
     * home for a translation — that would evaporate with the worker.
     *
     * @return array{backend: string, storage_path: string, signed_url: ?string, signed_url_expires_at: ?string}
     */
    public function uploadWithFallback(string $localPath, string $storagePath): array
    {
        try {
            $result = $this->uploadFile($localPath, $storagePath);

            return [
                'backend'               => self::BACKEND_SUPABASE,
                'storage_path'          => $result['storage_path'],
                'signed_url'            => $result['signed_url'],
                'signed_url_expires_at' => $result['signed_url_expires_at'],
            ];
        } catch (\Throwable $e) {
            Log::warning('StorageService: primary upload failed, attempting durable fallback', [
                'storage_path' => $storagePath,
                'exception'    => $e->getMessage(),
            ]);

            if (!$this->fallbackEnabled()) {
                throw new \RuntimeException(
                    'Failed to store translated file on primary backend and no durable fallback is configured: ' . $e->getMessage(),
                    0,
                    $e
                );
            }

            $this->storeLocal($storagePath, $localPath);

            return [
                'backend'               => self::BACKEND_LOCAL,
                'storage_path'          => $storagePath,
                'signed_url'            => null,
                'signed_url_expires_at' => now()->addSeconds(self::SIGNED_URL_EXPIRY_SECONDS)->toIso8601String(),
            ];
        }
    }

    /**
     * Copy a local file onto the durable fallback volume.
     */
    public function storeLocal(string $storagePath, string $localPath): void
    {
        $destination = $this->localAbsolutePath($storagePath);

        if (!is_dir(dirname($destination))) {
            mkdir(dirname($destination), 0770, true);
        }

        if (!copy($localPath, $destination)) {
            throw new \RuntimeException('Durable fallback copy failed for: ' . $storagePath);
        }

        // The caller owns $localPath. It may be the original upload still
        // needed by a queued worker, so storage operations must never delete it.
    }

    /**
     * Absolute path on the durable fallback volume for a logical storage path.
     */
    public function localAbsolutePath(string $storagePath): string
    {
        $root = rtrim((string) config('storage.fallback.path'), '/\\');
        return $root . DIRECTORY_SEPARATOR . ltrim($storagePath, '/\\');
    }

    /**
     * Read a file from any backend.
     */
    public function read(string $backend, string $storagePath): string
    {
        if ($backend === self::BACKEND_LOCAL) {
            $path = $this->localAbsolutePath($storagePath);
            if (!file_exists($path) || !is_readable($path)) {
                throw new \RuntimeException('Local storage file not found: ' . $storagePath);
            }
            $contents = @file_get_contents($path);
            if ($contents === false) {
                throw new \RuntimeException('Local storage file unreadable: ' . $storagePath);
            }
            return $contents;
        }

        return $this->downloadFile($storagePath);
    }

    /**
     * Build a user-facing download URL for a stored object on any backend.
     *
     * Supabase files use a freshly signed URL. Durable-fallback files are
     * served through the app's own auth-protected streaming route in
     * HistoryController — the returned local route keeps signed_url null.
     *
     * @return array{download_url: ?string, signed_url: ?string, signed_url_expires_at: ?string}
     */
    public function publicUrl(string $backend, string $storagePath): array
    {
        if ($backend === self::BACKEND_LOCAL) {
            return [
                'download_url'          => null, // filled in by HistoryController with the record id.
                'signed_url'            => null,
                'signed_url_expires_at' => now()->addSeconds(self::SIGNED_URL_EXPIRY_SECONDS)->toIso8601String(),
            ];
        }

        $result = $this->generateSignedUrl($storagePath);

        return [
            'download_url'          => $result['signed_url'],
            'signed_url'            => $result['signed_url'],
            'signed_url_expires_at' => $result['signed_url_expires_at'],
        ];
    }

    /**
     * Delete a file from any backend.
     */
    public function delete(string $backend, string $storagePath): void
    {
        if ($backend === self::BACKEND_LOCAL) {
            $path = $this->localAbsolutePath($storagePath);
            if (file_exists($path)) {
                @unlink($path);
            }
            return;
        }

        $this->deleteFile($storagePath);
    }

    /**
     * Delete a file from Supabase Storage.
     *
     * @param  string $storagePath Path inside the bucket.
     * @throws \RuntimeException on failure.
     */
    public function deleteFile(string $storagePath): void
    {
        $supabaseUrl    = config('services.supabase.url');
        $serviceRoleKey = config('services.supabase.service_role_key');
        $bucket         = config('services.supabase.bucket');

        $deleteUrl = rtrim($supabaseUrl, '/') . '/storage/v1/object/' . $bucket . '/' . $storagePath;

        try {
            $response = $this->guzzle->delete($deleteUrl, [
                'headers' => [
                    'Authorization' => 'Bearer ' . $serviceRoleKey,
                ],
            ]);
        } catch (ConnectException $e) {
            throw new \RuntimeException(
                'Supabase Storage delete failed: could not connect. ' . $e->getMessage(),
                0,
                $e
            );
        }

        $statusCode = $response->getStatusCode();

        // 200 OK or 404 (already gone) are both acceptable
        if ($statusCode >= 300 && $statusCode !== 404) {
            $body = (string) $response->getBody();
            throw new \RuntimeException('Supabase Storage delete failed: ' . $body);
        }
    }

    /**
     * Download a file from Supabase Storage.
     *
     * @param  string $storagePath Path inside the bucket.
     * @return string  Raw file contents.
     * @throws \RuntimeException on failure.
     */
    public function downloadFile(string $storagePath): string
    {
        $supabaseUrl    = config('services.supabase.url');
        $serviceRoleKey = config('services.supabase.service_role_key');
        $bucket         = config('services.supabase.bucket');

        $downloadUrl = rtrim($supabaseUrl, '/') . '/storage/v1/object/' . $bucket . '/' . $storagePath;

        try {
            $response = $this->guzzle->get($downloadUrl, [
                'headers' => [
                    'Authorization' => 'Bearer ' . $serviceRoleKey,
                ],
            ]);
        } catch (ConnectException $e) {
            throw new \RuntimeException(
                'Supabase Storage download failed: could not connect. ' . $e->getMessage(),
                0,
                $e
            );
        }

        $statusCode = $response->getStatusCode();
        if ($statusCode < 200 || $statusCode >= 300) {
            throw new \RuntimeException(
                'Supabase Storage download failed: HTTP ' . $statusCode
            );
        }

        return (string) $response->getBody();
    }

    /**
     * Generate a new signed URL for an existing object in Supabase Storage.
     *
     * @param  string $storagePath Path inside the bucket.
     * @return array{signed_url: string, signed_url_expires_at: string}
     * @throws \RuntimeException if the file does not exist (wraps 400/404 from Supabase).
     * @throws \RuntimeException on any other Supabase error.
     */
    public function generateSignedUrl(string $storagePath): array
    {
        $supabaseUrl    = config('services.supabase.url');
        $serviceRoleKey = config('services.supabase.service_role_key');
        $bucket         = config('services.supabase.bucket');

        $signUrl = rtrim($supabaseUrl, '/') . '/storage/v1/object/sign/' . $bucket . '/' . $storagePath;

        try {
            $response = $this->guzzle->post($signUrl, [
                'headers' => [
                    'Authorization' => 'Bearer ' . $serviceRoleKey,
                    'Content-Type'  => 'application/json',
                ],
                'json' => [
                    'expiresIn' => self::SIGNED_URL_EXPIRY_SECONDS,
                ],
            ]);
        } catch (ConnectException $e) {
            throw new \RuntimeException(
                'Supabase signed URL generation failed: could not connect to Supabase Storage. ' . $e->getMessage(),
                0,
                $e
            );
        }

        $statusCode = $response->getStatusCode();
        $body       = (string) $response->getBody();

        if ($statusCode < 200 || $statusCode >= 300) {
            if ($statusCode === 400 || $statusCode === 404) {
                throw new \RuntimeException(
                    'Supabase signed URL generation failed: file not found in storage. ' . $body
                );
            }

            throw new \RuntimeException('Supabase signed URL generation failed: ' . $body);
        }

        $data = json_decode($body, true);

        // Supabase returns a relative path in "signedURL"; prepend the base URL
        $relativeSignedUrl = $data['signedURL'] ?? '';
        $fullSignedUrl     = rtrim($supabaseUrl, '/') . '/storage/v1' . $relativeSignedUrl;

        // Expiry timestamp: now + 604800 seconds, ISO 8601 UTC
        $expiresAt = (new \DateTimeImmutable('now', new \DateTimeZone('UTC')))
            ->modify('+' . self::SIGNED_URL_EXPIRY_SECONDS . ' seconds')
            ->format(\DateTimeInterface::ATOM);

        return [
            'signed_url'            => $fullSignedUrl,
            'signed_url_expires_at' => $expiresAt,
        ];
    }

    /**
     * Canonical, opaque object key for user content.
     *
     * Storing user-controlled filenames as object keys leaks names and is a
     * directory-traversal vector. Keys are always "{uid}/{kind}/{uuid}.{ext}"
     * with the extension normalized to a safe lowercase set; the real name only
     * ever appears as metadata in the history row / Content-Disposition.
     */
    public static function makeStorageKey(int $userId, string $kind, string $originalName): string
    {
        $ext = strtolower((string) pathinfo($originalName, PATHINFO_EXTENSION));
        if ($ext === '' || strlen($ext) > 10 || !preg_match('/^[a-z0-9]+$/', $ext)) {
            $ext = 'bin';
        }

        return $userId . '/' . $kind . '/' . (string) Str::uuid() . '.' . $ext;
    }

    private function uploadFileOnce(string $localPath, string $storagePath): array
    {
        $supabaseUrl     = config('services.supabase.url');
        $serviceRoleKey  = config('services.supabase.service_role_key');
        $bucket          = config('services.supabase.bucket');

        $uploadUrl = rtrim($supabaseUrl, '/') . '/storage/v1/object/' . $bucket . '/' . $storagePath;

        $fileContents = file_get_contents($localPath);
        $mimeType     = mime_content_type($localPath) ?: 'application/octet-stream';

        try {
            $response = $this->guzzle->post($uploadUrl, [
                'headers' => [
                    'Authorization' => 'Bearer ' . $serviceRoleKey,
                    'Content-Type'  => $mimeType,
                ],
                'body' => $fileContents,
            ]);
        } catch (ConnectException $e) {
            throw new \RuntimeException(
                'Supabase Storage upload failed: could not connect to Supabase Storage. ' . $e->getMessage(),
                0,
                $e
            );
        } catch (\Throwable $e) {
            throw new \RuntimeException(
                'Supabase Storage upload failed: ' . $e->getMessage(),
                0,
                $e
            );
        }

        $statusCode = $response->getStatusCode();

        if ($statusCode < 200 || $statusCode >= 300) {
            $body = (string) $response->getBody();
            throw new \RuntimeException('Supabase Storage upload failed: ' . $body);
        }

        // Upload succeeded — generate and return the signed URL
        $signedResult = $this->generateSignedUrl($storagePath);

        return [
            'storage_path'          => $storagePath,
            'signed_url'            => $signedResult['signed_url'],
            'signed_url_expires_at' => $signedResult['signed_url_expires_at'],
        ];
    }

    private function fallbackEnabled(): bool
    {
        return (bool) config('storage.fallback.enabled', false);
    }

}
