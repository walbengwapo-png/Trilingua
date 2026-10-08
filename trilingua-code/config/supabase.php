<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Supabase Configuration
    |--------------------------------------------------------------------------
    |
    | Read from environment via .env. Always access these values through
    | config() — never env() — so they remain available when the
    | configuration is cached (config:cache) in demo/production.
    |
    */

    'url' => env('SUPABASE_URL'),

    'anon_key' => env('SUPABASE_ANON_KEY'),

    'service_role_key' => env('SUPABASE_SERVICE_ROLE_KEY'),

    'bucket' => env('SUPABASE_BUCKET', 'translations'),

];
