<?php

declare(strict_types=1);

/**
 * Standalone pre-boot test-environment guard.
 *
 * Runs BEFORE any Artisan/Laravel boot ("…"); a cached production config can
 * otherwise leak into the test process and cause destructive operations against
 * a live database. This guard is deliberately dependency-free (no Composer
 * autoload, no Laravel bootstrap) so it cannot be betrayed by a poisoned config.
 *
 * Fail-closed: exits non-zero unless the effective test environment is
 * unambiguously isolated (APP_ENV=testing, SQLite in-memory) AND no cached
 * production config is present.
 *
 * Usage:  php tests/assert-safe-test-env.php
 */

$appDir = realpath(dirname(__DIR__));
chdir($appDir);

$errors = [];

/* --------------------------------------------------------------------------
 | 1. Reject cached production configuration (the documented incident vector)
 | -------------------------------------------------------------------------- */
$cachedConfig = $appDir . DIRECTORY_SEPARATOR . 'bootstrap/cache/config.php';
if (is_file($cachedConfig)) {
    $errors[] = '[BLOCKER] bootstrap/cache/config.php exists (possible cached production config).';
}

/* --------------------------------------------------------------------------
 | 2. Read the effective test environment WITHOUT booting Laravel.
 |    Sources, low -> high: .env.testing  ->  phpunit.xml <php><env>  ->  process env
 |
 |    When APP_ENV=testing, Laravel loads .env.testing, NOT .env, so the
 |    (possibly production) .env must not be consulted here.
 | -------------------------------------------------------------------------- */
function readDotEnv(string $path): array
{
    $values = [];
    if (!is_file($path)) {
        return $values;
    }
    foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $line = trim($line);
        if ($line === '' || str_starts_with($line, '#') || !str_contains($line, '=')) {
            continue;
        }
        if (preg_match('/^([A-Z0-9_]+)=(.*)$/', $line, $m) === 1) {
            $values[$m[1]] = trim($m[2], " \t\"'");
        }
    }
    return $values;
}

function readPhpunitEnv(string $path): array
{
    $values = [];
    if (!is_file($path)) {
        return $values;
    }
    $xml = @simplexml_load_file($path);
    if ($xml === false || !isset($xml->php)) {
        return $values;
    }
    foreach ($xml->php->env as $env) {
        $name = (string) $env['name'];
        $value = (string) $env['value'];
        $force = strtolower((string) $env['force']) === 'true';
        if ($name !== '' && ($force || !array_key_exists($name, $values))) {
            $values[$name] = $value;
        }
    }
    return $values;
}

$testing = readDotEnv($appDir . '/.env.testing');
$phpunit = readPhpunitEnv($appDir . '/phpunit.xml');
$env = array_merge($testing, $phpunit);

// Highest precedence: real process environment.
foreach (['APP_ENV', 'DB_CONNECTION', 'DB_DATABASE', 'DB_HOST', 'DB_PORT', 'DB_URL', 'DB_DATABASE2'] as $key) {
    $v = getenv($key);
    if ($v !== false && $v !== '') {
        if (str_starts_with((string) $v, '(')) {
            continue; // Windows pseudo-vars like (trim) are not real values
        }
        $env[$key] = $v;
    }
}

/* --------------------------------------------------------------------------
 | 3. Validate the effective environment
 | -------------------------------------------------------------------------- */
$appEnv = $env['APP_ENV'] ?? null;
if ($appEnv === null || $appEnv === '') {
    $errors[] = '[BLOCKER] APP_ENV is not set. Tests require "testing".';
} elseif (strtolower((string) $appEnv) !== 'testing') {
    $errors[] = sprintf('[BLOCKER] APP_ENV is "%s"; tests require "testing".', $appEnv);
}

$dbConnection = $env['DB_CONNECTION'] ?? null;
if ($dbConnection === null || $dbConnection === '') {
    $errors[] = '[BLOCKER] DB_CONNECTION is not set. Tests require "sqlite".';
} elseif (strtolower((string) $dbConnection) !== 'sqlite') {
    $errors[] = sprintf('[BLOCKER] DB_CONNECTION is "%s"; tests require "sqlite".', $dbConnection);
}

$dbDatabase = $env['DB_DATABASE'] ?? null;
if ($dbDatabase === null || $dbDatabase === '') {
    $errors[] = '[BLOCKER] DB_DATABASE is not set. Tests require ":memory:".';
} elseif ($dbDatabase !== ':memory:') {
    $errors[] = sprintf('[BLOCKER] DB_DATABASE is "%s"; tests require ":memory:".', $dbDatabase);
}

// Reject any production host reference (also covers a stale .env value that
// slipped through env resolution). Pattern deliberately /supabase\.co|pooler/i.
$hostish = array_filter(
    [$env['DB_HOST'] ?? null, $env['DB_URL'] ?? null, $env['DB_DATABASE2'] ?? null],
    fn ($v) => is_string($v) && $v !== ''
);
foreach ($hostish as $value) {
    if (preg_match('/supabase\.co|pooler/i', $value)) {
        $errors[] = '[BLOCKER] Production database reference detected (pattern /supabase\.co|pooler/i). Refusing to run tests against a production database.';
    }
}

/* --------------------------------------------------------------------------
 | 4. Report and exit
 | -------------------------------------------------------------------------- */
if ($errors !== []) {
    fwrite(STDERR, implode("\n", $errors) . "\n");
    fwrite(STDERR, "Test run aborted. Fix the environment, then re-run; contact the project owner if this persists.\n");
    exit(1);
}

fwrite(STDOUT, "assert-safe-test-env: OK (APP_ENV=testing, DB_CONNECTION=sqlite, DB_DATABASE=:memory:, no cached config).\n");
exit(0);