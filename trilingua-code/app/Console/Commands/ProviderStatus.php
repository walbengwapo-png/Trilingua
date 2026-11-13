<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class ProviderStatus extends Command
{
    protected $signature = 'provider:status';
    protected $description = 'Read the persisted Ollama incident without contacting the provider';

    public function handle(): int
    {
        $this->line(json_encode(DB::table('provider_circuits')->where('scope', 'ollama')->first(),
            JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));
        return self::SUCCESS;
    }
}
