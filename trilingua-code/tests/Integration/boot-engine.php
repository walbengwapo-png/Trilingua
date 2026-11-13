<?php

require dirname(__DIR__).'/bootstrap-engine.php';
$app = require dirname(__DIR__, 2).'/bootstrap/app.php';
$app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$connection = $app['config']->get('database.default');
\Tests\Support\EngineTestEnvironment::checkResolved(['environment' => $app->environment(),
    ...$app['config']->get('database.connections.'.$connection, [])]);
if (\Illuminate\Support\Facades\DB::selectOne('select current_database() as name')->name !== 'trilingua_engine_test') {
    throw new RuntimeException('Connected database identity differs from the guarded test database.');
}
return $app;
