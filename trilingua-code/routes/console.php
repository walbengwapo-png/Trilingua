<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

// Translation workers can crash or be terminated while a document is in
// flight. Reconcile durable job state regularly so users and administrators
// see a recoverable failure instead of an indefinitely spinning translation.
Schedule::command('translations:reconcile --fail')
    ->everyFiveMinutes()
    ->withoutOverlapping();
