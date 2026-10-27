<?php

use App\Jobs\TranslateDocumentJob;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

require __DIR__ . '/vendor/autoload.php';

$app = require_once __DIR__ . '/bootstrap/app.php';

$kernel = $app->make(Illuminate\Contracts\Console\Kernel::class);
$kernel->bootstrap();

// Create a NON-EXISTENT persistent path to deliberately trigger the
// "Uploaded file not found" failure path in the job.
$persistId = (string) Str::uuid();
$persistentDir = storage_path('app/uploads/' . $persistId);
$persistentPath = $persistentDir . DIRECTORY_SEPARATOR . 'missing_file.txt';

// Do NOT create the directory or file - intentionally missing

// Instantiate the job exactly as the controller does
$job = new TranslateDocumentJob(
    'missing_file.txt',
    '.txt',
    0,
    'English',
    'Cebuano',
    'auto',
    $persistentPath,
    1,
    null,
    'fast'
);

$jobId = $job->uuid();
Log::info('CONTROLLER uuid=' . $jobId . ' (FAILURE TEST - missing file)');

// Dispatch through the real queue (database)
dispatch($job);

echo "Dispatched job with UUID: {$jobId}\n";
echo "Persistent path (NON-EXISTENT): {$persistentPath}\n";