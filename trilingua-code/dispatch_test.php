<?php

use App\Jobs\TranslateDocumentJob;
use Illuminate\Support\Facades\Log;

require __DIR__ . '/vendor/autoload.php';

$app = require_once __DIR__ . '/bootstrap/app.php';

$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

// Create a persistent copy of the fixture file (like the controller does)
$persistId = (string) Illuminate\Support\Str::uuid();
$persistentDir = storage_path('app/uploads/' . $persistId);
$persistentPath = $persistentDir . DIRECTORY_SEPARATOR . 'translated_input.txt';

if (!is_dir($persistentDir)) {
    mkdir($persistentDir, 0755, true);
}
copy(__DIR__ . '/translated_input.txt', $persistentPath);

// Instantiate the job exactly as the controller does
$job = new TranslateDocumentJob(
    'translated_input.txt',
    '.txt',
    filesize($persistentPath),
    'English',
    'Cebuano',
    'auto',
    $persistentPath,
    1,
    null,
    'fast'
);

$jobId = $job->uuid();
Log::info('CONTROLLER uuid=' . $jobId);

// Dispatch through the real queue (database)
dispatch($job);

echo "Dispatched job with UUID: {$jobId}\n";
echo "Persistent path: {$persistentPath}\n";