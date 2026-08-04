<?php

namespace App\Support;

/**
 * Fixed flag-reason taxonomy for admin review flags.
 *
 * Stored as a string column; any 'other' category should be accompanied by
 * a free-text note. The same reason list is used for text translations and
 * individual document blocks.
 */
class FlagReason
{
    public const MISTRANSLATION = 'mistranslation';
    public const MISSING_CONTENT = 'missing_content';
    public const FORMATTING_BROKEN = 'formatting_broken';
    public const HALLUCINATION = 'hallucination';
    public const TERMINOLOGY_ERROR = 'terminology_error';
    public const OTHER = 'other';

    public const ALL = [
        self::MISTRANSLATION,
        self::MISSING_CONTENT,
        self::FORMATTING_BROKEN,
        self::HALLUCINATION,
        self::TERMINOLOGY_ERROR,
        self::OTHER,
    ];
}
