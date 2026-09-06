<?php

namespace App\Support;

use Illuminate\Http\JsonResponse;
use Illuminate\Support\Str;

final class ApiError
{
    public static function response(string $code, string $message, int $status = 500, bool $retryable = false): JsonResponse
    {
        $reference = 'TL-' . strtoupper(Str::random(8));

        return response()->json([
            'error' => [
                'code' => $code,
                'message' => $message,
                'reference_id' => $reference,
                'retryable' => $retryable,
            ],
            // Kept during the UI transition so non-JS consumers can still use
            // a simple display string without receiving internal exception data.
            'message' => $message,
            'reference_id' => $reference,
            'retryable' => $retryable,
        ], $status);
    }
}
