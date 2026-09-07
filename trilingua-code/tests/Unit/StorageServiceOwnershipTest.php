<?php

namespace Tests\Unit;

use App\Services\StorageService;
use GuzzleHttp\Client;
use Tests\TestCase;

class StorageServiceOwnershipTest extends TestCase
{
    public function test_durable_fallback_copy_does_not_delete_the_callers_source_file(): void
    {
        $root = storage_path('app/testing/fallback-'.uniqid('', true));
        $source = storage_path('app/testing/source-'.uniqid('', true).'.txt');
        $logicalPath = '7/translations/result.txt';

        if (! is_dir(dirname($source))) {
            mkdir(dirname($source), 0755, true);
        }
        file_put_contents($source, 'translation payload');
        config(['storage.fallback.path' => $root]);

        $storage = new StorageService(new Client());
        $storage->storeLocal($logicalPath, $source);

        $destination = $root.DIRECTORY_SEPARATOR.'7'.DIRECTORY_SEPARATOR.'translations'.DIRECTORY_SEPARATOR.'result.txt';
        $this->assertFileExists($source, 'StorageService must not delete files owned by its caller.');
        $this->assertFileExists($destination);
        $this->assertSame('translation payload', file_get_contents($destination));

        @unlink($source);
        @unlink($destination);
        @rmdir(dirname($destination));
        @rmdir(dirname(dirname($destination)));
        @rmdir($root);
    }
}
