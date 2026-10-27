<?php

require __DIR__ . '/vendor/autoload.php';

$app = require_once __DIR__ . '/bootstrap/app.php';

$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

$supabaseUrl    = config('services.supabase.url');
$serviceRoleKey = config('services.supabase.service_role_key');
$configuredBucket = config('services.supabase.bucket');

echo "Configured SUPABASE_BUCKET: {$configuredBucket}\n";
echo "Supabase URL: {$supabaseUrl}\n\n";

$client = new \GuzzleHttp\Client([
    'verify' => false, // Diagnostic only - bypass SSL cert for bucket listing
]);

try {
    $response = $client->get(rtrim($supabaseUrl, '/') . '/storage/v1/bucket', [
        'headers' => [
            'Authorization' => 'Bearer ' . $serviceRoleKey,
        ],
    ]);

    $statusCode = $response->getStatusCode();
    $body = (string) $response->getBody();

    echo "HTTP Status: {$statusCode}\n";
    echo "Raw response:\n{$body}\n\n";

    $buckets = json_decode($body, true);
    if (is_array($buckets)) {
        echo "Bucket names found:\n";
        foreach ($buckets as $bucket) {
            echo "  - {$bucket['name']}\n";
        }

        $names = array_column($buckets, 'name');
        if (in_array($configuredBucket, $names)) {
            echo "\nMATCH: Configured bucket '{$configuredBucket}' EXISTS in Supabase.\n";
        } else {
            echo "\nMISMATCH: Configured bucket '{$configuredBucket}' does NOT exist in Supabase.\n";
            echo "Available buckets: " . implode(', ', $names) . "\n";
        }
    } else {
        echo "Could not parse bucket list.\n";
    }
} catch (\Throwable $e) {
    echo "ERROR: " . $e->getMessage() . "\n";
}