<?php

namespace App\Http\Controllers;

use App\Exceptions\TranslationException;
use App\Services\HistoryService;
use App\Services\StorageService;
use App\Services\TranslationService;
use Illuminate\Contracts\View\View;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class TranslationController extends Controller
{
    public function __construct(
        private TranslationService $service,
        private StorageService $storage,
        private HistoryService $history,
    ) {}

    /**
     * GET /translate — render the translation page.
     */
    public function show(): View
    {
        return view('translation');
    }

    /**
     * POST /translate — handle text or document translation.
     */
    public function translate(Request $request): JsonResponse
    {
        $sourceLang = $request->input('source_lang');

        $request->validate([
            'source_lang' => ['required', Rule::in(['English', 'Cebuano', 'Filipino'])],
            'target_lang' => [
                'required',
                Rule::in(['English', 'Cebuano', 'Filipino']),
                Rule::notIn([$sourceLang]),
            ],
            'text'     => ['required_without:document', 'nullable', 'string', 'max:8000'],
            'document' => [
                'required_without:text',
                'nullable',
                'file',
                'mimes:docx,pdf,txt,md,rtf,odt,csv',
                'max:10240',
            ],
            'pdf_column_mode' => ['nullable', Rule::in(['auto', 'single', 'left', 'right'])],
        ], [
            'target_lang.not_in' => 'The source language and target language must be different.',
        ]);

        $targetLang = $request->input('target_lang');
        $pdfColumnMode = $request->input('pdf_column_mode', 'auto');

        try {
            // Document mode — upload original to Supabase, translate, upload translated
            if ($request->hasFile('document')) {
                $uploadedFile = $request->file('document');
                $originalName = $uploadedFile->getClientOriginalName();
                $originalExt  = strtolower('.' . $uploadedFile->getClientOriginalExtension());
                $fileSize     = $uploadedFile->getSize();

                // 1. Upload the ORIGINAL file to Supabase Storage
                $originalStoragePath = Auth::id() . '/originals/' . Str::uuid() . '_' . $originalName;

                try {
                    $originalStorageResult = $this->storage->uploadFile(
                        $uploadedFile->getRealPath(),
                        $originalStoragePath
                    );
                } catch (\Throwable $e) {
                    Log::error('Supabase Storage upload failed for original file', [
                        'exception' => $e->getMessage(),
                        'storage_path' => $originalStoragePath,
                    ]);
                    return response()->json([
                        'error' => 'Failed to store original document. Please try again.',
                    ], 500);
                }

                // 2. Translate the document
                $outputPath = $this->service->translateDocument(
                    $uploadedFile,
                    $sourceLang,
                    $targetLang,
                    $pdfColumnMode
                );

                // 3. Upload the TRANSLATED file to Supabase Storage
                $translatedStoragePath = Auth::id() . '/' . basename($outputPath);

                try {
                    $storageResult = $this->storage->uploadFile($outputPath, $translatedStoragePath);
                } catch (\Throwable $e) {
                    Log::error('Supabase Storage upload failed for translated file', [
                        'exception' => $e->getMessage(),
                        'storage_path' => $translatedStoragePath,
                    ]);
                    @unlink($outputPath);
                    // Clean up the original file from storage since translation failed
                    try {
                        $this->storage->deleteFile($originalStoragePath);
                    } catch (\Throwable $deleteEx) {
                        Log::error('Failed to clean up original file after translation failure', [
                            'exception' => $deleteEx->getMessage(),
                        ]);
                    }
                    return response()->json([
                        'error' => 'Translation succeeded but file upload failed. Please try again.',
                    ], 500);
                }

                @unlink($outputPath);

                $downloadFilename = $this->service->getOriginalOutputName(
                    $originalName,
                    $originalExt
                );

                // 4. Create history record with document relationship fields
                try {
                    $this->history->insertRecord([
                        'user_id'               => Auth::id(),
                        'original_filename'     => $originalName,
                        'translated_filename'   => $downloadFilename,
                        'source_language'       => $sourceLang,
                        'target_language'       => $targetLang,
                        'created_at'            => now()->toIso8601String(),
                        'storage_path'          => $translatedStoragePath,
                        'original_storage_path' => $originalStoragePath,
                        'file_size'             => $fileSize,
                        'status'                => 'completed',
                        'signed_url_expires_at' => $storageResult['signed_url_expires_at'],
                    ]);
                } catch (\Throwable $e) {
                    Log::error('Failed to insert translation history record', [
                        'exception'    => $e->getMessage(),
                        'user_id'      => Auth::id(),
                        'storage_path' => $translatedStoragePath,
                    ]);
                }

                return response()->json([
                    'download_url'          => $storageResult['signed_url'],
                    'download_filename'     => $downloadFilename,
                    'signed_url_expires_at' => $storageResult['signed_url_expires_at'],
                ]);
            }

            // Text mode
            $result = $this->service->translateText(
                $request->input('text'),
                $sourceLang,
                $targetLang
            );

            // Log text translation to history (non-blocking)
            try {
                $this->history->insertRecord([
                    'user_id'          => Auth::id(),
                    'translation_type' => 'text',
                    'source_text'      => $request->input('text'),
                    'translated_text'  => $result,
                    'source_language'  => $sourceLang,
                    'target_language'  => $targetLang,
                    'created_at'       => now()->toIso8601String(),
                    'status'           => 'completed',
                ]);
            } catch (\Throwable $e) {
                Log::error('Failed to insert text translation history record', [
                    'exception'  => $e->getMessage(),
                    'user_id'    => Auth::id(),
                ]);
            }

            return response()->json(['translated' => $result]);

        } catch (TranslationException $e) {
            $message = $e->getMessage();

            if (str_contains($message, 'timed out')) {
                return response()->json(['error' => $message], 504);
            }

            return response()->json(['error' => $message], 500);
        }
    }

}