<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Python AI Engine Configuration
    |--------------------------------------------------------------------------
    |
    | Laravel should NEVER know about AI providers, prompts, chunking, etc.
    | These settings only control how Laravel communicates with the Python AI Engine.
    |
    */
    
    'python_service' => [
        'url' => env('PYTHON_SERVICE_URL', 'http://127.0.0.1:5000'),
        'timeout' => env('PYTHON_SERVICE_TIMEOUT', 600),
        // Shared secret the Laravel client presents as X-Service-Token so the
        // python service can reject non-app callers. Deploy both sides together.
        'token' => env('PYTHON_SERVICE_TOKEN'),
    ],
    
    /*
    |--------------------------------------------------------------------------
    | Upload Protection
    |--------------------------------------------------------------------------
    |
    | Per-user per-day document upload limits (count + total bytes) and file
    | content-sniffing. These gate abusive usage of the python engine.
    |
    */
    'upload' => [
        'max_daily_files' => (int) env('TRANSLATION_MAX_DAILY_FILES', 25),
        'max_daily_bytes' => (int) env('TRANSLATION_MAX_DAILY_BYTES', 262144000),
    ],
    
    /*
    |--------------------------------------------------------------------------
    | Supported Languages
    |--------------------------------------------------------------------------
    |
    | The languages supported for translation. These must match the languages
    | supported by the Python AI Engine.
    |
    */
    'languages' => ['English', 'Cebuano', 'Filipino'],
    
    /*
    |--------------------------------------------------------------------------
    | Supported Document Formats
    |--------------------------------------------------------------------------
    |
    | File extensions that can be uploaded for document translation.
    |
    */
    'supported_formats' => ['docx', 'pdf', 'txt', 'md', 'rtf', 'odt', 'csv', 'pptx', 'xlsx'],
    
    /*
    |--------------------------------------------------------------------------
    | Extension Map
    |--------------------------------------------------------------------------
    |
    | Maps input extensions to output extensions for document translation.
    | Some formats (RTF, ODT) are converted to DOCX for output.
    |
    */
    'extension_map' => [
        'docx' => 'docx',
        'pdf'  => 'pdf',
        'txt'  => 'txt',
        'md'   => 'md',
        'csv'  => 'csv',
        'rtf'  => 'docx',
        'odt'  => 'docx',
        'pptx' => 'pptx',
        'xlsx' => 'xlsx',
    ],
];