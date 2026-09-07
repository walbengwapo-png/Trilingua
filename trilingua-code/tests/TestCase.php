<?php

namespace Tests;

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    /**
     * Defense-in-depth safety check on top of tests/assert-safe-test-env.php.
     *
     * Runs after the application has booted and asserts the *resolved*
     * configuration is isolated. This is a second, independent layer: the
     * standalone guard blocks cached production config before any boot, and
     * here we verify the boot outcome itself.
     *
     * @throws \RuntimeException when the booted app is not isolated.
     */
    protected function setUp(): void
    {
        parent::setUp();

        $app = $this->app;

        if (!$app instanceof Application) {
            throw new \RuntimeException('Application did not boot before tests; refusing to continue.');
        }

        $problems = [];

        if (!$app->environment('testing')) {
            $problems[] = 'APP_ENV resolved to "' . $app->environment() . '" (expected "testing").';
        }

        $connection = (string) config('database.default');
        if ($connection !== 'sqlite') {
            $problems[] = 'DB_CONNECTION resolved to "' . $connection . '" (expected "sqlite").';
        }

        /** @var \Illuminate\Database\ConnectionInterface $sqlite */
        $sqlite = $app['db']->connection();
        $database = (string) $sqlite->getDatabaseName();
        if ($database !== ':memory:') {
            $problems[] = 'DB_DATABASE resolved to "' . $database . '" (expected ":memory:").';
        }

        try {
            $driver = $sqlite->getDriverName();
        } catch (\Throwable $e) {
            $driver = 'unknown';
        }
        if (strtolower($driver) !== 'sqlite') {
            $problems[] = 'Active connection driver is "' . $driver . '" (expected "sqlite").';
        }

        if ($problems !== []) {
            throw new \RuntimeException(
                "Test isolation guard failed. Resolved application configuration is unsafe:\n"
                . implode("\n", $problems)
            );
        }
    }
}