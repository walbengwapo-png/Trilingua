<?php

namespace Tests\Unit;

use App\Services\StorageService;
use GuzzleHttp\Client;
use GuzzleHttp\Handler\MockHandler;
use GuzzleHttp\HandlerStack;
use GuzzleHttp\Psr7\Response;
use Tests\TestCase;

class StoragePresenceTest extends TestCase
{
    public function test_supabase_presence_distinguishes_missing_from_unverifiable(): void
    {
        config([
            'services.supabase.url' => 'https://storage.example.test',
            'services.supabase.bucket' => 'test',
            'services.supabase.service_role_key' => 'test-key',
        ]);

        $handler = HandlerStack::create(new MockHandler([
            new Response(404, [], '{"code":"NoSuchKey"}'),
            new Response(404, [], '{"code":"NoSuchBucket"}'),
            new Response(403),
            new Response(200),
        ]));
        $client = new Client(['handler' => $handler]);
        $storage = new StorageService($client);

        $this->assertSame(StorageService::PRESENCE_MISSING, $storage->exists('supabase', 'gone.pdf'));
        $this->assertSame(StorageService::PRESENCE_UNKNOWN, $storage->exists('supabase', 'bucket-missing.pdf'));
        $this->assertSame(StorageService::PRESENCE_UNKNOWN, $storage->exists('supabase', 'private.pdf'));
        $this->assertSame(StorageService::PRESENCE_PRESENT, $storage->exists('supabase', 'present.pdf'));
    }
}
