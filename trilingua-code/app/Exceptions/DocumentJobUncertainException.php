<?php

namespace App\Exceptions;

/** A failed status read is not evidence that the accepted engine job failed. */
class DocumentJobUncertainException extends TranslationException
{
    public function __construct(public readonly string $engineJobId, int $status = 503)
    {
        parent::__construct('Document status is temporarily unavailable. Operator reconciliation is required; do not submit it again. Reference: '.$engineJobId, $status);
    }
}
