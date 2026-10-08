<?php

namespace Tests\Feature;

use PHPUnit\Framework\Attributes\DataProvider;
use Tests\TestCase;

class ProductionConfigurationTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();
        // Configuration checks do not connect to these synthetic services.
        config([
            'app.env' => 'production',
            'app.debug' => false,
            'app.url' => 'https://app.example.com',
            'database.default' => 'pgsql',
            'database.connections.pgsql.sslmode' => 'require',
            'session.driver' => 'database',
            'session.secure' => true,
            'session.http_only' => true,
            'cache.default' => 'database',
            'queue.default' => 'database',
            'translation.python_service.url' => 'https://engine.example.com',
            'translation.python_service.token' => str_repeat('a', 32),
            'supabase.url' => 'https://test.supabase.co',
            'storage.fallback.enabled' => false,
        ]);
    }

    public function test_valid_configuration_passes_without_contacting_services(): void
    {
        $this->artisan('deployment:validate-production')->assertSuccessful();
    }

    #[DataProvider('unsafeSettings')]
    public function test_unsafe_configuration_is_rejected(string $key, mixed $value): void
    {
        config([$key => $value]);
        $this->artisan('deployment:validate-production')->assertFailed();
    }

    public static function unsafeSettings(): array
    {
        return [
            ['app.env', 'local'],
            ['app.debug', true],
            ['app.key', ''],
            ['app.url', 'http://app.example.com'],
            ['database.default', 'sqlite'],
            ['database.connections.pgsql.sslmode', 'prefer'],
            ['session.driver', 'file'],
            ['session.secure', false],
            ['session.http_only', false],
            ['cache.default', 'file'],
            ['queue.default', 'cloud'],
            ['translation.python_service.url', 'http://127.0.0.1:5000'],
            ['translation.python_service.url', 'https://localhost'],
            ['translation.python_service.token', 'short'],
            ['supabase.service_role_key', ''],
            ['storage.fallback.enabled', true],
        ];
    }
}
