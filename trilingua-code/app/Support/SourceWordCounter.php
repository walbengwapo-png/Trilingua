<?php

namespace App\Support;

use InvalidArgumentException;

class SourceWordCounter
{
    public const METHOD = 'source-words-unicode-v1';

    public static function count(string $source): int
    {
        $matched = preg_match_all('/[\p{L}\p{N}][\p{L}\p{M}\p{N}]*(?:[\x{0027}\x{2019}\x{002D}\x{2010}\x{2011}][\p{L}\p{N}][\p{L}\p{M}\p{N}]*)*/u', $source, $matches);
        if ($matched === false) {
            throw new InvalidArgumentException('Source is not valid Unicode.');
        }

        return count(array_filter($matches[0], fn (string $token): bool => preg_match('/\p{L}/u', $token) === 1));
    }

    public static function measure(?string $source): array
    {
        $count = null;
        if ($source !== null) {
            try {
                $count = self::count($source);
            } catch (InvalidArgumentException) {
                // Unavailable source is different from an observed empty source.
            }
        }

        return [
            'schema_version' => 1, 'method' => self::METHOD,
            'provenance' => $count === null ? 'unknown' : 'derived',
            'count' => $count, 'known_words' => $count ?? 0,
            'completeness' => $count === null ? 'missing' : 'complete',
            'known_blocks' => $count === null ? 0 : 1, 'total_blocks' => 1,
            'extraction_coverage' => 'not_applicable',
        ];
    }

    public static function fromBlocks(array $blocks): array
    {
        $known = 0;
        $words = 0;
        foreach ($blocks as $block) {
            $measurement = self::measure(is_string($block['source_text'] ?? null) ? $block['source_text'] : null);
            if ($measurement['count'] !== null) {
                $known++;
                $words += $measurement['count'];
            }
        }
        $complete = $blocks !== [] && $known === count($blocks);

        return [
            'schema_version' => 1, 'method' => self::METHOD,
            'provenance' => $known > 0 ? 'derived' : 'unknown',
            'count' => $complete ? $words : null, 'known_words' => $words,
            'completeness' => $complete ? 'complete' : ($known > 0 ? 'partial' : 'missing'),
            'known_blocks' => $known, 'total_blocks' => count($blocks),
            // Complete lexical counting of supplied blocks does not certify extraction.
            'extraction_coverage' => 'unknown',
        ];
    }
}
