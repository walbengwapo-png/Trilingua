<?php

namespace App\Services;

use App\Models\TranslationHistory;
use Illuminate\Support\Facades\DB;

class HistoryService
{
    /**
     * Insert a new translation job record into translation_history.
     *
     * For document translations, pass:
     *   user_id, translation_type='document', original_filename, translated_filename,
     *   source_language, target_language, created_at, storage_path, original_storage_path,
     *   parent_document_id, file_size, status, signed_url_expires_at
     *
     * For text translations, pass:
     *   user_id, translation_type='text', source_text, translated_text,
     *   source_language, target_language, created_at
     */
    public function insertRecord(array $data): TranslationHistory
    {
        return TranslationHistory::create([
            'user_id'               => $data['user_id'] ?? null,
            'translation_type'      => $data['translation_type'] ?? 'document',
            'original_filename'     => $data['original_filename'] ?? null,
            'translated_filename'   => $data['translated_filename'] ?? null,
            'source_language'       => $data['source_language'] ?? null,
            'target_language'       => $data['target_language'] ?? null,
            'created_at'            => $data['created_at'] ?? now(),
            'storage_path'          => $data['storage_path'] ?? null,
            'original_storage_path' => $data['original_storage_path'] ?? null,
            'parent_document_id'    => $data['parent_document_id'] ?? null,
            'file_size'             => $data['file_size'] ?? null,
            'status'                => $data['status'] ?? 'completed',
            'signed_url_expires_at' => $data['signed_url_expires_at'] ?? null,
            'source_text'           => $data['source_text'] ?? null,
            'translated_text'       => $data['translated_text'] ?? null,
        ]);
    }

    /**
     * Fetch history records for a user, newest first, capped at 200.
     *
     * @param  int  $userId  The authenticated user's ID.
     * @return array<int, array>  Each element is a translation_history row.
     */
    public function getHistory(int $userId): array
    {
        return TranslationHistory::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->limit(200)
            ->get()
            ->toArray();
    }

    /**
     * Fetch a user's bookmarked records, newest first, capped at 500.
     *
     * @param  int  $userId  The authenticated user's ID.
     * @return array<int, array>  Each element is a translation_history row.
     */
    public function getBookmarked(int $userId): array
    {
        return TranslationHistory::where('user_id', $userId)
            ->where('is_bookmarked', '=', DB::raw('true'))
            ->orderBy('created_at', 'desc')
            ->limit(500)
            ->get()
            ->toArray();
    }

    /**
     * Fetch a page of history records for a user, newest first.
     *
     * @param  int  $userId  The authenticated user's ID.
     * @param  int  $perPage  Records per page.
     * @return \Illuminate\Contracts\Pagination\LengthAwarePaginator<int, array<string, mixed>>
     */
    public function getHistoryPaginated(int $userId, int $perPage = 50)
    {
        return TranslationHistory::where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->paginate($perPage);
    }

    /**
     * Fetch a single record by ID.
     *
     * @return array|null  Null if not found.
     */
    public function getRecord(int $id): ?array
    {
        $record = TranslationHistory::find($id);

        return $record?->toArray();
    }

    /**
     * Fetch a single record with its translations (child documents).
     *
     * @return array|null  Null if not found. Includes 'translations' key.
     */
    public function getRecordWithTranslations(int $id): ?array
    {
        $record = TranslationHistory::with('translations')->find($id);

        if (!$record) {
            return null;
        }

        $data = $record->toArray();
        $data['translations'] = $record->translations->toArray();

        return $data;
    }

    /**
     * Fetch all translations generated from a given original document.
     *
     * @param  int $parentId  The parent document's ID.
     * @param  int $userId    The authenticated user's ID (ownership check).
     * @return array<int, array>
     */
    public function getTranslationsForDocument(int $parentId, int $userId): array
    {
        return TranslationHistory::where('parent_document_id', $parentId)
            ->where('user_id', $userId)
            ->orderBy('created_at', 'desc')
            ->get()
            ->toArray();
    }

    /**
     * Fetch all original documents (not translations) for a user, with their translations eager-loaded.
     *
     * @param  int $userId  The authenticated user's ID.
     * @return array<int, array>
     */
    public function getOriginalsWithTranslations(int $userId): array
    {
        $originals = TranslationHistory::with('translations')
            ->where('user_id', $userId)
            ->whereNull('parent_document_id')
            ->where('translation_type', 'document')
            ->orderBy('created_at', 'desc')
            ->limit(200)
            ->get();

        $result = [];
        foreach ($originals as $original) {
            $data = $original->toArray();
            $data['translations'] = $original->translations->toArray();
            $data['translation_count'] = $original->translations()->count();
            $result[] = $data;
        }

        return $result;
    }

    /**
     * Delete a history record and its child translations.
     * Also returns storage paths so the caller can delete files from Supabase.
     *
     * @param  int $id      The record ID.
     * @param  int $userId  The authenticated user's ID (ownership check).
     * @return array{deleted: bool, storage_paths: string[], original_storage_paths: string[]}
     */
    public function deleteRecord(int $id, int $userId): array
    {
        $record = TranslationHistory::find($id);

        if (!$record || (int) $record->user_id !== $userId) {
            return ['deleted' => false, 'storage_paths' => [], 'original_storage_paths' => []];
        }

        $storagePaths = [];
        $originalStoragePaths = [];

        // Collect child translations' storage paths
        $children = TranslationHistory::where('parent_document_id', $id)->get();
        foreach ($children as $child) {
            if ($child->storage_path) {
                $storagePaths[] = $child->storage_path;
            }
            if ($child->original_storage_path) {
                $originalStoragePaths[] = $child->original_storage_path;
            }
            $child->delete();
        }

        // Collect this record's own storage paths
        if ($record->storage_path) {
            $storagePaths[] = $record->storage_path;
        }
        if ($record->original_storage_path) {
            $originalStoragePaths[] = $record->original_storage_path;
        }

        $record->delete();

        return [
            'deleted' => true,
            'storage_paths' => $storagePaths,
            'original_storage_paths' => $originalStoragePaths,
        ];
    }

    /**
     * Update the signed_url_expires_at column for a record.
     */
    public function updateExpiry(int $id, string $newExpiry): void
    {
        TranslationHistory::where('id', $id)->update([
            'signed_url_expires_at' => $newExpiry,
        ]);
    }

    /**
     * Rename a record's display filename.
     *
     * Translations show their translated_filename, originals show their
     * original_filename — rename whichever is the record's display name. The
     * stored storage_path is untouched, so the file itself is unaffected.
     *
     * @param  int  $id      The record ID.
     * @param  int  $userId  The authenticated user's ID (ownership check).
     * @param  string  $newName  The new display filename (extension preserved).
     * @return array{renamed: bool, record: array|null}
     */
    public function renameRecord(int $id, int $userId, string $newName): array
    {
        $record = TranslationHistory::find($id);

        if (!$record || (int) $record->user_id !== $userId) {
            return ['renamed' => false, 'record' => null];
        }

        if (blank($record->translated_filename)) {
            $record->original_filename = $newName;
        } else {
            $record->translated_filename = $newName;
        }
        $record->save();

        return ['renamed' => true, 'record' => $record->toArray()];
    }
}