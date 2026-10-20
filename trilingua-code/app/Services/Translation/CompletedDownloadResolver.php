<?php

namespace App\Services\Translation;

use App\Models\TranslationHistory;
use App\Services\StorageService;
use Illuminate\Support\Facades\Log;

/**
 * The single storage-availability rule for a completed translation's download.
 *
 * Every completed payload must obey the same contract, whether it is produced
 * by /translate/status/{jobId}, by a fresh-upload dedup reuse, or by a
 * re-translation reuse. Before this class existed those paths disagreed:
 * TranslationController asked the backend whether the object was really there,
 * while DocumentsController::historyDownloadUrl() answered any failure by
 * silently handing back the streaming route — so a completed re-translation
 * could promise a download for a file that was confirmed deleted.
 *
 * The rule, in one place:
 *
 *   present  -> a signed URL when one can be produced, otherwise the
 *               owner-authorized streaming route.
 *   missing  -> a terminal, non-recoverable failure. The output is gone, so no
 *               URL is offered and the caller must not present one.
 *   unknown  -> the record stays completed and no download link is asserted,
 *               because a storage outage cannot prove the object is gone. The
 *               database state is never flipped by an outage.
 */
class CompletedDownloadResolver
{
    public function __construct(private StorageService $storage) {}

    /**
     * @return array{status: string, download_url?: string, download_filename?: string,
     *               signed_url_expires_at?: string, download_available?: bool,
     *               message?: string, error?: string, recoverable?: bool}
     */
    public function resolve(TranslationHistory $history): array
    {
        $backend = $history->storage_backend ?: StorageService::BACKEND_SUPABASE;

        if ($backend === StorageService::BACKEND_LOCAL) {
            // The streaming route reads through the backend; no signer exists.
            return $this->readableOrUnavailable($history, $backend);
        }

        try {
            $signedResult = $this->storage->generateSignedUrl((string) $history->storage_path);

            return [
                'status'                => 'completed',
                'download_url'          => $signedResult['signed_url'],
                'download_filename'     => $history->translated_filename,
                'signed_url_expires_at' => $signedResult['signed_url_expires_at'],
            ];
        } catch (\Throwable $e) {
            Log::warning('Failed to generate signed URL for completed translation; verifying object before fallback', [
                'exception'              => $e->getMessage(),
                'translation_history_id' => $history->id,
                'storage_path'           => $history->storage_path,
            ]);
        }

        // Signed-URL failure: only fall back to the owner route when
        // backend-specific evidence PROVES the object is readable. We never
        // present a completed link we cannot stand behind.
        return $this->readableOrUnavailable($history, $backend);
    }

    /**
     * Build a completed payload only when the object is proven readable.
     *
     * See the class docblock for the three-state contract.
     */
    private function readableOrUnavailable(TranslationHistory $history, string $backend): array
    {
        $state = $this->storage->exists($backend, (string) $history->storage_path);

        if ($state === StorageService::PRESENCE_PRESENT) {
            return $this->authenticatedRoutePayload($history);
        }

        if ($state === StorageService::PRESENCE_MISSING) {
            Log::error('Completed translation object is confirmed missing from storage', [
                'translation_history_id' => $history->id,
                'storage_backend'        => $backend,
                'storage_path'           => $history->storage_path,
            ]);

            return [
                'status'      => 'failed',
                'error'       => 'The translated file is no longer available in storage. Please retry the translation.',
                'recoverable' => false,
            ];
        }

        // Storage uncertainty (network/authorisation outage): do NOT turn a
        // completed record into a durable failure, and do NOT assert an unproven
        // download link.
        Log::warning('Could not verify completed translation readability; deferring download', [
            'translation_history_id' => $history->id,
            'storage_backend'        => $backend,
            'storage_path'           => $history->storage_path,
        ]);

        return [
            'status'             => 'completed',
            'download_available' => false,
            'download_filename'  => $history->translated_filename,
            'message'            => 'Your translation is complete, but the download could not be verified right now. Please try again shortly.',
        ];
    }

    /**
     * The owner-authorized streaming route works for every backend and requires
     * no working Supabase signer, so it is the completion invariant's download
     * path whenever a signed URL cannot be produced.
     */
    private function authenticatedRoutePayload(TranslationHistory $history): array
    {
        return [
            'status'            => 'completed',
            'download_url'      => route('history.file', ['id' => $history->id]),
            'download_filename' => $history->translated_filename,
        ];
    }
}
