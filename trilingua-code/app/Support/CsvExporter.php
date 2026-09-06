<?php

namespace App\Support;

use Symfony\Component\HttpFoundation\Response;

/**
 * Streams an array of associative rows as a CSV download.
 *
 * Keeps admin analytics exportable without pulling in any external package.
 * Header keys are humanized from snake_case to Title Case.
 */
class CsvExporter
{
    /**
     * Build a StreamingResponse that emits a CSV file.
     *
     * @param  string            $filename  Download filename (e.g. "review-trends.csv").
     * @param  array<int, array<string, mixed>>  $rows  Associative rows; the first
     *                                                  row's keys become the header.
     * @param  array<string, string>  $renames  Optional column display-name overrides.
     */
    public static function download(string $filename, array $rows, array $renames = []): Response
    {
        $headers = [];
        if ($rows !== []) {
            $headers = array_keys($rows[0]);
        }

        return response()->streamDownload(function () use ($rows, $headers, $renames) {
            $out = fopen('php://output', 'w');
            if ($out === false) {
                return;
            }

            // BOM so Excel opens UTF-8 (Cebuano/Filipino) characters correctly.
            fwrite($out, "\xEF\xBB\xBF");

            $headerLabels = [];
            foreach ($headers as $head) {
                $headerLabels[] = $renames[$head] ?? ucwords(str_replace('_', ' ', $head));
            }
            fputcsv($out, $headerLabels);

            foreach ($rows as $row) {
                $line = [];
                foreach ($headers as $head) {
                    $value = $row[$head] ?? '';
                    $line[] = is_array($value) ? json_encode($value, JSON_UNESCAPED_UNICODE) : (string) $value;
                }
                fputcsv($out, $line);
            }

            fclose($out);
        }, $filename, ['Content-Type' => 'text/csv; charset=UTF-8']);
    }
}