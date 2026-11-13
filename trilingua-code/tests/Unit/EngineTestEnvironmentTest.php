<?php

namespace Tests\Unit;

use PHPUnit\Framework\TestCase;
use Tests\Support\EngineTestEnvironment as Guard;

class EngineTestEnvironmentTest extends TestCase
{
    private function safe(): array
    {
        return ['APP_ENV' => 'testing', 'DB_CONNECTION' => 'pgsql', 'DB_HOST' => '127.0.0.1',
            'DB_DATABASE' => 'trilingua_engine_test'];
    }

    public function test_only_the_named_loopback_database_passes(): void
    {
        Guard::check($this->safe(), dirname(__DIR__, 2));
        Guard::checkResolved(['environment' => 'testing', 'driver' => 'pgsql', 'host' => '127.0.0.1',
            'database' => 'trilingua_engine_test']);
        $this->addToAssertionCount(2);
    }

    public function test_remote_alternate_database_live_keys_and_override_urls_are_rejected(): void
    {
        foreach ([['DB_HOST', 'database.example.com'], ['DB_HOST', '127.1'], ['DB_DATABASE', 'postgres'],
            ['DB_DATABASE', 'trilingua_test'], ['DB_CONNECTION', 'sqlite'], ['APP_ENV', 'production'],
            ['DB_URL', 'pgsql://localhost/trilingua_engine_test'], ['APP_CONFIG_CACHE', '/cached/config.php'],
            ['OLLAMA_API_KEY', 'unapproved-key'], ['SUPABASE_URL', 'https://live.example.com']] as [$key, $value]) {
            try {
                Guard::check(array_replace($this->safe(), [$key => $value]), dirname(__DIR__, 2));
                $this->fail('Unsafe configuration was accepted: '.$key);
            } catch (\RuntimeException $error) {
                $this->assertStringNotContainsString($value, $error->getMessage());
            }
        }
    }

    public function test_resolved_configuration_cannot_override_the_preboot_guard(): void
    {
        $this->expectException(\RuntimeException::class);
        Guard::checkResolved(['environment' => 'testing', 'driver' => 'pgsql', 'host' => 'db.example.com',
            'database' => 'trilingua_engine_test']);
    }

    public function test_cached_or_unreviewed_environment_files_are_rejected_before_boot(): void
    {
        $root = sys_get_temp_dir().'/trilingua-guard-'.bin2hex(random_bytes(6));
        mkdir($root.'/bootstrap/cache', 0700, true);
        try {
            foreach (['.env', '.env.testing', 'bootstrap/cache/config.php'] as $file) {
                file_put_contents($root.'/'.$file, 'test fixture');
                try {
                    Guard::check($this->safe(), $root);
                    $this->fail('Unreviewed configuration was accepted');
                } catch (\RuntimeException $error) {
                    $this->assertStringContainsString($file, $error->getMessage());
                } finally { unlink($root.'/'.$file); }
            }
        } finally { rmdir($root.'/bootstrap/cache'); rmdir($root.'/bootstrap'); rmdir($root); }
    }
}
