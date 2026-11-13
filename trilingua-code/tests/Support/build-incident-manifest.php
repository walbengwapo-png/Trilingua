<?php
// Data-only snapshot validation. No Laravel boot, database connection, or payload execution.
require dirname(__DIR__, 2).'/vendor/autoload.php';
$snapshot = json_decode(file_get_contents($argv[1]), true, 64, JSON_THROW_ON_ERROR);
$rows = \App\Support\TranslationQueueMetadata::manifest($snapshot['failed'], $snapshot['translations']);
$bytes = json_encode($rows, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR)."\n";
if (isset($argv[2])) { file_put_contents($argv[2], $bytes); }
printf("%d/%d valid unique matches; manifest SHA256 %s\n", count(array_filter($rows, fn ($r) => $r['valid'])),
    count($rows), hash('sha256', $bytes));
exit(count($rows) === 16 && count(array_filter($rows, fn ($r) => $r['valid'])) === 16 ? 0 : 1);
