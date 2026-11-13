<?php

namespace Tests\Unit;

use App\Jobs\TranslateDocumentJob;
use App\Support\TranslationQueueMetadata as Metadata;
use App\Support\TranslationJobFilters;
use Illuminate\Database\Connection;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Query\Builder as Query;
use PHPUnit\Framework\TestCase;

class TranslationQueueMetadataTest extends TestCase
{
    private function payload(array $changes = []): string
    {
        $values = array_replace(['translationJobId' => 9, 'userId' => 4, 'originalName' => '日本語.txt',
            'originalStoragePath' => '4/originals/source.txt', 'ocrMode' => 'preview',
            "\0App\\Jobs\\TranslateDocumentJob\0jobUuid" => 'translation-uuid', 'chained' => []], $changes);
        $properties = '';
        foreach ($values as $key => $value) { $properties .= serialize($key).serialize($value); }
        $class = TranslateDocumentJob::class;
        $command = 'O:'.strlen($class).':"'.$class.'":'.count($values).':{'.$properties.'}';
        return json_encode(['uuid' => 'different-queue-uuid', 'data' => ['commandName' => $class, 'command' => $command]], JSON_THROW_ON_ERROR);
    }

    public function test_legacy_resolution_is_data_only_and_leaves_every_byte_unchanged(): void
    {
        $payload = $this->payload(); $original = $payload;
        $metadata = Metadata::extract($payload);
        $this->assertSame(9, $metadata['translation_job_id']);
        $this->assertSame('preview', $metadata['ocr_mode']);
        $this->assertSame('日本語.txt', $metadata['original_name']);
        $this->assertSame($original, $payload);
    }

    public function test_object_tokens_references_trailing_data_and_corrupt_lengths_are_rejected(): void
    {
        $payload = $this->payload(); $envelope = json_decode($payload, true);
        $envelope['data']['command'] .= 'N;';
        $this->assertNull(Metadata::extract(json_encode($envelope)));
        $this->assertNull(Metadata::extract($this->payload(['chained' => [new \stdClass]])));
        $this->assertNull(Metadata::extract(str_replace('s:7:', 's:99999:', $payload)));
        $this->assertNull(Metadata::extract(str_repeat('x', 1048577)));
    }

    public function test_field_like_text_inside_filename_cannot_override_id(): void
    {
        $metadata = Metadata::extract($this->payload(['originalName' => 's:16:"translationJobId";i:999;.txt']));
        $this->assertSame(9, $metadata['translation_job_id']);
    }

    public function test_plain_metadata_is_read_without_parsing_the_command(): void
    {
        $envelope = json_decode($this->payload(), true);
        $metadata = Metadata::extract($this->payload());
        $envelope['translation_job_id'] = $metadata['translation_job_id'];
        unset($metadata['translation_job_id']);
        $envelope['translation_job_metadata'] = $metadata;
        $envelope['data']['command'] = 'encrypted-or-unsupported-data';
        $this->assertSame(9, Metadata::extract(json_encode($envelope))['translation_job_id']);
    }

    public function test_manifest_requires_all_identity_fields_hash_and_original_and_is_stable(): void
    {
        $payload = $this->payload();
        $job = ['id' => 9, 'user_id' => 4, 'original_name' => '日本語.txt',
            'original_storage_path' => '4/originals/source.txt', 'storage_exists' => true];
        $failed = [['failed_job_id' => 1, 'payload' => $payload, 'payload_sha256' => hash('sha256', $payload)]];
        $first = Metadata::manifest($failed, [$job]);
        $this->assertTrue($first[0]['valid']);
        $this->assertSame($first, Metadata::manifest($failed, [$job]));
        $job['user_id'] = 99;
        $this->assertFalse(Metadata::manifest($failed, [$job])[0]['valid']);
        $failed[0]['payload_sha256'] = str_repeat('0', 64);
        $this->assertFalse(Metadata::manifest($failed, [$job])[0]['checks']['payload_hash']);
    }

    public function test_empty_filters_add_no_where_clause_and_status_search_do(): void
    {
        $connection = new Connection(fn () => throw new \RuntimeException('No DB allowed'));
        $model = $this->getMockBuilder(\App\Models\TranslationJob::class)->onlyMethods(['newQueryWithoutRelationships'])->getMock();
        $model->method('newQueryWithoutRelationships')->willReturn((new Builder(new Query($connection)))->setModel($model));
        $query = (new Builder(new Query($connection)))->setModel($model);
        TranslationJobFilters::apply($query, ['status' => '', 'q' => '']);
        $this->assertSame([], $query->getQuery()->wheres);
        TranslationJobFilters::apply($query, ['status' => 'failed', 'q' => 'source']);
        $this->assertCount(2, $query->getQuery()->wheres);
        $this->assertSame(['failed', '%source%', '%source%'], $query->getQuery()->getBindings());
    }

    public function test_reviewed_incident_manifest_contains_sixteen_unique_verified_matches(): void
    {
        if (!is_file(dirname(__DIR__, 2).'/docs/reliability/J1-incident-manifest.json')) {
            $this->markTestSkipped('Private incident evidence is verified locally and excluded from public CI.');
        }
        $rows = json_decode(file_get_contents(dirname(__DIR__, 2).'/docs/reliability/J1-incident-manifest.json'), true, 32, JSON_THROW_ON_ERROR);
        $this->assertCount(16, $rows);
        $this->assertCount(16, array_unique(array_column($rows, 'translation_job_id')));
        $this->assertSame([], array_filter($rows, fn ($row) => !$row['valid']));
        $this->assertCount(4, array_filter($rows, fn ($row) => $row['engine_job_uuid'] === null));
    }
}
