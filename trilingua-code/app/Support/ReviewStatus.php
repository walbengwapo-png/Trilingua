<?php

namespace App\Support;

/**
 * Valid review statuses for translation_history and translation_blocks.
 *
 * Stored as string columns (matching the existing text-typed enums such as
 * translation_history.translation_type) with application-level validation.
 */
class ReviewStatus
{
    public const PENDING = 'pending';
    public const VERIFIED = 'verified';
    public const EDITED = 'edited';
    public const FLAGGED = 'flagged';

    public const ALL = [
        self::PENDING,
        self::VERIFIED,
        self::EDITED,
        self::FLAGGED,
    ];

    /**
     * Statuses that count as "completed review" for analytics.
     */
    public const COMPLETED = [
        self::VERIFIED,
        self::EDITED,
        self::FLAGGED,
    ];
}
