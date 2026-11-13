<?php

namespace App\Exceptions;

use RuntimeException;

class TranslationException extends RuntimeException
{
    public function __construct(string $message = '', int $code = 0, ?\Throwable $previous = null,
        public readonly ?array $errorDetails = null)
    {
        parent::__construct($message, $code, $previous);
    }
}
