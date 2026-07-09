<?php

namespace App\Services;

use GuzzleHttp\Client;
use GuzzleHttp\Exception\ConnectException;

class StorageService
{
    /**
     * Signed URL expiry in seconds (7 days).
     */
    public const SIGNED_URL_EXPIRY_SECONDS = 604800;

    public function __construct(private Client $guzzle) {}

    /**
     * Upload a local file to Supabase Storage and return a signed download URL.
     *
     * @param  string $localPath   Absolute path to the file on disk.
     * @param  string $storagePath Destination path inside the bucket, e.g. "{session_id}/{uuid}_translated.docx".
     * @return array{storage_path: string, signed_url: string, signed_url_expires_at: string}
     * @throws \RuntimeException on upload or signed-URL failure.
     */
    public function uploadFile(string $localPath, string $storagePath): array
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
}
