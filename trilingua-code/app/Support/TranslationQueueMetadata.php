<?php

namespace App\Support;

use App\Jobs\TranslateDocumentJob;
use App\Models\TranslationJob;
use InvalidArgumentException;

/** Reads a bounded scalar serialization grammar. It NEVER constructs payload objects. */
final class TranslationQueueMetadata
{
    public static function forJob(TranslateDocumentJob $job): array
    {
        return [
            'translation_job_id' => $job->translationJobId,
            'translation_attempt' => $job->expectedAttempt ?? 1,
            'translation_job_metadata' => [
                'user_id' => $job->userId, 'original_name' => $job->originalName,
                'original_storage_path' => $job->originalStoragePath, 'ocr_mode' => $job->ocrMode ?? 'strict',
            ],
        ];
    }

    public static function extract(string $payload): ?array
    {
        try {
            if (strlen($payload) > 1048576) {
                return null;
            }
            $envelope = json_decode($payload, true, 32, JSON_THROW_ON_ERROR);
            if (!is_array($envelope) || ($envelope['data']['commandName'] ?? null) !== TranslateDocumentJob::class) {
                return null;
            }
            if (isset($envelope['translation_job_id'], $envelope['translation_job_metadata'])) {
                $metadata = $envelope['translation_job_metadata'];
                $metadata['translation_job_id'] = $envelope['translation_job_id'];
                $metadata['expected_attempt'] = $envelope['translation_attempt'] ?? null;
            } else {
                $command = $envelope['data']['command'] ?? null;
                if (!is_string($command) || strlen($command) > 262144) {
                    return null;
                }
                $reader = new self($command);
                $properties = $reader->objectProperties();
                $metadata = [
                    'translation_job_id' => $properties['translationJobId'] ?? null,
                    'user_id' => $properties['userId'] ?? null,
                    'original_name' => $properties['originalName'] ?? null,
                    'original_storage_path' => $properties['originalStoragePath'] ?? null,
                    'ocr_mode' => $properties['ocrMode'] ?? null,
                    'expected_attempt' => $properties['expectedAttempt'] ?? null,
                ];
            }
            if (!is_int($metadata['translation_job_id'] ?? null) || $metadata['translation_job_id'] < 1
                || !is_int($metadata['user_id'] ?? null) || $metadata['user_id'] < 1
                || !is_string($metadata['original_name'] ?? null)
                || !is_string($metadata['original_storage_path'] ?? null)
                || !in_array($metadata['ocr_mode'] ?? null, ['strict', 'preview'], true)) {
                return null;
            }
            return $metadata;
        } catch (\Throwable) {
            return null;
        }
    }

    public static function matches(array $metadata, array $job): bool
    {
        return $metadata['translation_job_id'] === (int) $job['id']
            && $metadata['user_id'] === (int) $job['user_id']
            && $metadata['original_name'] === $job['original_name']
            && $metadata['original_storage_path'] === $job['original_storage_path'];
    }

    public static function resolve(string $payload): ?TranslationJob
    {
        $metadata = self::extract($payload);
        if ($metadata === null) {
            return null;
        }
        $job = TranslationJob::find($metadata['translation_job_id']);
        return $job && self::matches($metadata, $job->getAttributes()) ? $job : null;
    }

    /** Stable, data-only report: repeated dry runs produce identical bytes. */
    public static function manifest(array $failed, array $translations): array
    {
        $jobs = array_column($translations, null, 'id');
        $seen = [];
        $rows = [];
        usort($failed, fn ($a, $b) => $a['failed_job_id'] <=> $b['failed_job_id']);
        foreach ($failed as $row) {
            $metadata = self::extract($row['payload']);
            $job = $metadata ? ($jobs[$metadata['translation_job_id']] ?? null) : null;
            $hash = hash('sha256', $row['payload']);
            $checks = [
                'user_id' => $job && $metadata['user_id'] === (int) $job['user_id'],
                'original_name' => $job && $metadata['original_name'] === $job['original_name'],
                'original_storage_path' => $job && $metadata['original_storage_path'] === $job['original_storage_path'],
                'payload_hash' => hash_equals($row['payload_sha256'] ?? $hash, $hash),
                'original_exists' => $job && ($job['storage_exists'] ?? false) === true,
                'unique_translation' => $job && !isset($seen[$job['id']]),
            ];
            if ($job) {
                $seen[$job['id']] = true;
            }
            $rows[] = ['failed_job_id' => $row['failed_job_id'], 'translation_job_id' => $job['id'] ?? null,
                'user_id' => $job['user_id'] ?? null, 'original_name' => $job['original_name'] ?? null,
                'original_storage_path' => $job['original_storage_path'] ?? null,
                'ocr_mode' => $metadata['ocr_mode'] ?? null, 'engine_job_uuid' => $job['engine_job_uuid'] ?? null,
                'payload_sha256' => $hash, 'checks' => $checks, 'valid' => !in_array(false, $checks, true)];
        }
        return $rows;
    }

    private int $offset = 0;
    private function __construct(private readonly string $input) {}

    private function take(string $literal): void
    {
        if (substr($this->input, $this->offset, strlen($literal)) !== $literal) {
            throw new InvalidArgumentException('Invalid serialized data');
        }
        $this->offset += strlen($literal);
    }

    private function integer(string $terminator): int
    {
        $end = strpos($this->input, $terminator, $this->offset);
        $raw = $end === false ? '' : substr($this->input, $this->offset, $end - $this->offset);
        if (!preg_match('/^-?(0|[1-9][0-9]{0,17})$/D', $raw)) {
            throw new InvalidArgumentException('Invalid integer');
        }
        $this->offset = $end + strlen($terminator);
        return (int) $raw;
    }

    private function stringValue(): string
    {
        $this->take('s:');
        $length = $this->integer(':');
        if ($length < 0 || $length > 262144) {
            throw new InvalidArgumentException('Invalid length');
        }
        $this->take('"');
        $value = substr($this->input, $this->offset, $length);
        $this->offset += $length;
        $this->take('";');
        return $value;
    }

    private function value(int $depth = 0): mixed
    {
        if ($depth > 8) {
            throw new InvalidArgumentException('Nested data limit');
        }
        $type = $this->input[$this->offset] ?? '';
        if ($type === 's') { return $this->stringValue(); }
        if ($type === 'N') { $this->take('N;'); return null; }
        if ($type === 'i') { $this->take('i:'); return $this->integer(';'); }
        if ($type === 'b') {
            $this->take('b:'); $value = $this->integer(';');
            if (!in_array($value, [0, 1], true)) { throw new InvalidArgumentException('Invalid bool'); }
            return (bool) $value;
        }
        if ($type === 'a') {
            $this->take('a:'); $count = $this->integer(':'); $this->take('{');
            if ($count < 0 || $count > 256) { throw new InvalidArgumentException('Array limit'); }
            $values = [];
            for ($i = 0; $i < $count; $i++) {
                $key = $this->value($depth + 1);
                if ((!is_string($key) && !is_int($key)) || array_key_exists($key, $values)) {
                    throw new InvalidArgumentException('Invalid array key');
                }
                $values[$key] = $this->value($depth + 1);
            }
            $this->take('}'); return $values;
        }
        // No O/C/E/R/r tokens: no nested objects, custom serializers, enums or references.
        throw new InvalidArgumentException('Unsupported data token');
    }

    private function objectProperties(): array
    {
        $class = TranslateDocumentJob::class;
        $this->take('O:'.strlen($class).':"'.$class.'":');
        $count = $this->integer(':'); $this->take('{');
        if ($count < 0 || $count > 128) { throw new InvalidArgumentException('Property limit'); }
        $values = [];
        for ($i = 0; $i < $count; $i++) {
            $key = $this->stringValue();
            $key = substr($key, (strrpos($key, "\0") ?: -1) + 1);
            if (array_key_exists($key, $values)) { throw new InvalidArgumentException('Duplicate property'); }
            $values[$key] = $this->value();
        }
        $this->take('}');
        if ($this->offset !== strlen($this->input)) { throw new InvalidArgumentException('Trailing data'); }
        return $values;
    }
}
