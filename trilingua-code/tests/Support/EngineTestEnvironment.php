<?php

namespace Tests\Support;

/** Dependency-free checks: call before application bootstrap or opening a connection. */
final class EngineTestEnvironment
{
    public static function check(array $environment, string $root): void
    {
        foreach (['bootstrap/cache/config.php', '.env', 'Model/.env'] as $file) {
            if (is_file($root.'/'.$file)) {
                throw new \RuntimeException('Engine tests refuse cached or unreviewed configuration: '.$file);
            }
        }
        // The tracked SQLite-only baseline fixture is safe; the engine profile overrides its DB settings.
        // Reject a changed fixture that could introduce a live endpoint before Dotenv can load it.
        if (is_file($root.'/.env.testing')) {
            $fixture = [];
            foreach (file($root.'/.env.testing', FILE_IGNORE_NEW_LINES) as $line) {
                $line = trim(ltrim($line, "\xEF\xBB\xBF"));
                if ($line === '' || str_starts_with($line, '#')) { continue; }
                if (!preg_match('/^([A-Z_0-9]+)=(.*)$/D', $line, $match)) {
                    throw new \RuntimeException('Unreviewed .env.testing syntax.');
                }
                $fixture[$match[1]] = trim($match[2], "\"'");
            }
            if (($fixture['APP_ENV'] ?? '') !== 'testing' || ($fixture['DB_CONNECTION'] ?? '') !== 'sqlite'
                || ($fixture['DB_DATABASE'] ?? '') !== ':memory:' || !empty($fixture['DB_HOST'])) {
                throw new \RuntimeException('Unreviewed .env.testing database configuration.');
            }
            self::checkServices($fixture);
        }
        if (($environment['APP_ENV'] ?? '') !== 'testing'
            || ($environment['DB_CONNECTION'] ?? '') !== 'pgsql'
            || ($environment['DB_DATABASE'] ?? '') !== 'trilingua_engine_test'
            || !in_array($environment['DB_HOST'] ?? '', ['127.0.0.1', 'localhost', '::1'], true)) {
            throw new \RuntimeException('Engine tests require testing / pgsql / loopback / trilingua_engine_test.');
        }
        self::checkServices($environment);
    }

    private static function checkServices(array $environment): void
    {
        foreach (['DB_URL', 'DATABASE_URL', 'DB_DATABASE2', 'APP_CONFIG_CACHE'] as $key) {
            if (!empty($environment[$key])) {
                throw new \RuntimeException('Engine tests refuse alternate connection/configuration: '.$key);
            }
        }
        foreach (['OLLAMA_API_KEY', 'GEMINI_API_KEY', 'SUPABASE_SERVICE_ROLE_KEY'] as $key) {
            if (!empty($environment[$key]) && !in_array($environment[$key], ['test-only-key', 'test-service-role-key'], true)) {
                throw new \RuntimeException('Engine tests refuse live provider credentials: '.$key);
            }
        }
        if (!empty($environment['SUPABASE_URL']) && $environment['SUPABASE_URL'] !== 'https://test.supabase.co') {
            throw new \RuntimeException('Engine tests refuse a live Supabase endpoint.');
        }
    }

    public static function checkResolved(array $configuration): void
    {
        if (($configuration['environment'] ?? '') !== 'testing' || ($configuration['driver'] ?? '') !== 'pgsql'
            || ($configuration['database'] ?? '') !== 'trilingua_engine_test'
            || !in_array($configuration['host'] ?? '', ['127.0.0.1', 'localhost', '::1'], true)
            || !empty($configuration['url'])) {
            throw new \RuntimeException('Resolved database configuration failed the engine test guard.');
        }
    }
}
