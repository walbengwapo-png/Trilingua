<?php

require __DIR__.'/vendor/autoload.php';

$app = require_once __DIR__.'/bootstrap/app.php';
$app->make('Illuminate\Contracts\Console\Kernel')->bootstrap();

use Illuminate\Support\Facades\DB;

// Check the schema (PostgreSQL)
$columns = DB::select("
    SELECT column_name, data_type, column_default, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'users'
    AND column_name IN ('theme', 'language')
    ORDER BY ordinal_position
");

echo "Checking theme and language columns:\n";
echo "=====================================\n\n";

foreach ($columns as $column) {
    echo "Column: {$column->column_name}\n";
    echo "  Type: {$column->data_type}\n";
    echo "  Default: {$column->column_default}\n";
    echo "  Nullable: {$column->is_nullable}\n\n";
}

echo "Migration verification complete!\n";
