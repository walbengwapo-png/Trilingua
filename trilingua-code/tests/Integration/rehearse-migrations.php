<?php

use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

require __DIR__.'/boot-engine.php';
function ensure(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
    echo 'PASS '.$message.PHP_EOL;
}
$migrations = [
    '2026_11_12_000001_add_translation_error_details.php',
    '2026_11_12_000002_create_provider_circuits.php',
    '2026_11_12_000003_fence_translation_retries.php',
    '2026_11_13_000004_create_translation_admissions.php',
];
ensure(Artisan::call('migrate', ['--force' => true]) === 0, 'All forward migrations apply on PostgreSQL');
foreach (array_reverse($migrations) as $migration) {
    ensure(Artisan::call('migrate:rollback', ['--force' => true, '--step' => 1,
        '--path' => 'database/migrations/'.$migration]) === 0, 'Rollback '.$migration);
}
ensure(!Schema::hasColumn('translation_jobs', 'error_details') && !Schema::hasTable('provider_circuits')
    && !Schema::hasColumn('translation_jobs', 'ocr_mode') && !Schema::hasTable('translation_admissions'),
    'Reverse migration order removes only additions');
for ($i=0; $i<12; $i++) {
    DB::table('python_document_jobs')->insert(['id' => (string) \Illuminate\Support\Str::uuid(),
        'fingerprint' => hash('sha256', 'legacy-'.$i), 'filename' => 'synthetic.txt', 'input_path' => 'fixture/'.$i,
        'options' => '{}', 'status' => 'failed', 'error_status' => 429, 'error' => 'Synthetic historical failure']);
}
$legacyBefore = DB::table('python_document_jobs')->orderBy('id')->get()->toJson();
foreach (array_slice($migrations,0,2) as $migration) {
    ensure(Artisan::call('migrate', ['--force' => true, '--path' => 'database/migrations/'.$migration]) === 0,
        'Reapply '.$migration);
}
ensure(DB::table('provider_circuits')->where('scope','ollama')->value('state') === 'manual', 'Legacy unknown cause seeds a manual stop');
$legacyAfter = DB::table('python_document_jobs')->orderBy('id')->get()->map(function ($row) {
    unset($row->error_details,$row->request_context); return $row;
})->toJson();
ensure($legacyBefore === $legacyAfter, 'Seeding preserves all twelve historical errors and timestamps');
$owner = DB::table('users')->insertGetId(['name' => 'Synthetic migration owner', 'email' => 'migration@example.invalid',
    'password' => 'not-a-login', 'created_at' => now(), 'updated_at' => now()]);
$job = (string) \Illuminate\Support\Str::uuid();
$history = ['user_id' => $owner, 'job_id' => $job, 'translation_type' => 'text', 'source_language' => 'English',
    'target_language' => 'Filipino', 'source_text' => 'Synthetic source', 'translated_text' => 'Synthetic result'];
$first = DB::table('translation_history')->insertGetId($history);
$duplicate = DB::table('translation_history')->insertGetId($history);
try {
    Artisan::call('migrate', ['--force' => true, '--path' => 'database/migrations/'.$migrations[2]]);
    throw new RuntimeException('Unique index accepted duplicate history');
} catch (\Illuminate\Database\QueryException $error) {
    ensure((string) $error->getCode() === '23505', 'Deliberate duplicate rejects the unique-index migration');
}
ensure(DB::table('translation_history')->whereIn('id',[$first,$duplicate])->count() === 2,
    'Failed unique-index migration preserves both source rows');
ensure(!Schema::hasColumn('translation_jobs','ocr_mode'), 'Failed migration rolls back its earlier column addition');
DB::table('translation_history')->where('id',$duplicate)->delete();
ensure(Artisan::call('migrate', ['--force' => true, '--path' => 'database/migrations/'.$migrations[2]]) === 0,
    'Unique-index migration reapplies after removing only the synthetic duplicate');
DB::table('translation_history')->insert(array_replace($history,['job_id'=>null]));
DB::table('translation_history')->insert(array_replace($history,['job_id'=>null]));
ensure(DB::table('translation_history')->where('user_id',$owner)->whereNull('job_id')->count() === 2,
    'Partial history index allows multiple null job IDs');

ensure(Artisan::call('migrate', ['--force' => true, '--path' => 'database/migrations/'.$migrations[3]]) === 0,
    'User admission migration reapplies');
DB::table('translation_admissions')->insert(['user_id' => $owner, 'owner' => (string) \Illuminate\Support\Str::uuid(), 'phase' => 'uncertain']);
try {
    (require database_path('migrations/'.$migrations[3]))->down();
    throw new RuntimeException('Admission rollback accepted an outstanding owner');
} catch (RuntimeException $error) {
    ensure($error->getMessage() === 'Drain/reconcile translation admissions before rollback.',
        'Rollback refuses an outstanding admission');
}
ensure(Schema::hasTable('translation_admissions') && DB::table('translation_admissions')->whereNotNull('owner')->count() === 1,
    'Refused rollback preserves admission evidence');
DB::table('translation_admissions')->where('user_id', $owner)->update(['owner' => null]);
