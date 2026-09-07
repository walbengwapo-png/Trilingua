<?php

return [
    /*
    |--------------------------------------------------------------------------
    | Durable Storage Backends
    |--------------------------------------------------------------------------
    |
    | Transliteration output must survive a queue worker crash or region outage,
    | so translated files are uploaded to a PRIMARY backend (Supabase Storage)
    | with retries, and if that permanently fails, to a DURABLE FALLBACK backend.
    |
    | The fallback must be an encrypted, backed-up persistent store — a second
    | private object-storage backend or an encrypted shared persistent volume —
    | never container-local or worker-local temp space. Local disk is only used
    | as in-transit scratch between the queue worker and the backend.
    |
    */
    'primaries' => ['supabase'],

    'fallback' => [
        // Enables the durable fallback backend. Keep disabled until the
        // infrastructure (encrypted volume / second bucket) actually exists.
        'enabled' => env('FALLBACK_STORAGE_ENABLED', false),
        'driver'  => env('FALLBACK_STORAGE_DRIVER', 'local'),
        // Absolute path of the encrypted persistent volume the fallback writes to.
        'path'    => env('FALLBACK_STORAGE_PATH', storage_path('app/private/translations')),
        'url'     => env('FALLBACK_STORAGE_URL'),
    ],
];