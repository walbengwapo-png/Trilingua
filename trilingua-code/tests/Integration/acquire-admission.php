<?php

// Separate connection/process; pre-boot guard refuses every live/remote database.
$app = require __DIR__.'/boot-engine.php';
$app['config']->set('translation.admission_enabled', true);
fwrite(STDOUT, "READY\n");
fflush(STDOUT);
if (trim((string) fgets(STDIN)) !== 'GO') { exit(2); }
$lease = $app->make(\App\Services\TranslationAdmission::class)->acquire((int) ($argv[1] ?? 0));
fwrite(STDOUT, json_encode($lease, JSON_THROW_ON_ERROR)."\n");
