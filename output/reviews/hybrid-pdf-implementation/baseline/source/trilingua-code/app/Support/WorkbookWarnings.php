<?php

namespace App\Support;

use DOMDocument;
use DOMXPath;
use ZipArchive;

final class WorkbookWarnings
{
    public static function inspect(string $path): array
    {
        $zip = new ZipArchive;
        if ($zip->open($path) !== true) {
            return [];
        }
        $shapes = false;
        $extensions = false;
        $oversized = false;
        try {
            for ($i = 0; $i < $zip->numFiles; $i++) {
                $name = $zip->getNameIndex($i);
                if (! str_starts_with($name, 'xl/') || ! str_ends_with($name, '.xml')) {
                    continue;
                }
                // Bound inspection of compressed XML; uncertain content also gets a warning.
                if (($zip->statIndex($i)['size'] ?? 0) > 5 * 1024 * 1024) {
                    $oversized = true;
                    continue;
                }
                $xml = new DOMDocument;
                $previous = libxml_use_internal_errors(true);
                try {
                    $loaded = $xml->loadXML($zip->getFromIndex($i), LIBXML_NONET);
                } finally {
                    libxml_clear_errors();
                    libxml_use_internal_errors($previous);
                }
                if (! $loaded) {
                    continue;
                }
                $xpath = new DOMXPath($xml);
                $shapes = $shapes || $xpath->query('//*[local-name()="sp" and namespace-uri()="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"]')->length > 0;
                $extensions = $extensions || $xpath->query('//*[local-name()="extLst"]')->length > 0;
            }
        } finally {
            $zip->close();
        }
        $warnings = [];
        if ($shapes) {
            $warnings[] = 'This workbook contains drawing shapes that will be removed during processing. Keep the original workbook.';
        }
        if ($extensions) {
            $warnings[] = 'This workbook contains extension data that may be removed during processing, including advanced validation or formatting. Keep the original workbook.';
        }
        if ($oversized) {
            $warnings[] = 'Some workbook content could not be inspected within the preview limit. Unsupported features may be removed; keep the original workbook.';
        }

        return $warnings;
    }
}
