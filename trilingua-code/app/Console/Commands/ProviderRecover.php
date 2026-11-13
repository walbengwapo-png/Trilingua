<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;

class ProviderRecover extends Command
{
    protected $signature = 'provider:recover {incident} {version} {--actor=}
        {--probe : Explicitly generate one minimal response with each configured model}
        {--legacy-manifest= : Reviewed JSON array of twelve engine UUIDs}
        {--release-legacy : Deprecated; refuse the old ID-only release path}
        {--release-incident= : Approved JSON manifest including probe evidence and twelve row snapshots}
        {--approve-sha256= : Exact SHA256 of the reviewed release manifest}';
    protected $description = 'Dry-run by default; named-incident manual probe and reviewed legacy-marker release';

    public function handle(): int
    {
        $incident = (string) $this->argument('incident');
        $version = filter_var($this->argument('version'), FILTER_VALIDATE_INT);
        if (!\Illuminate\Support\Str::isUuid($incident) || !$version || !filled($this->option('actor'))) {
            $this->error('A valid incident UUID, version and actor are required.');
            return self::FAILURE;
        }
        if ($this->option('probe') && ($this->option('release-legacy') || $this->option('release-incident'))) {
            $this->error('Probe and legacy release are separate review steps.');
            return self::FAILURE;
        }
        if ($this->option('probe')) {
            $reply = Http::withHeaders(['X-Service-Token' => config('translation.python_service.token')])
                ->timeout(60)->connectTimeout(5)
                ->post(rtrim(config('translation.python_service.url'), '/').'/internal/provider/probe', [
                    'incident' => $incident, 'version' => $version, 'actor' => $this->option('actor'),
                ]);
            $this->line($reply->body());
            return $reply->successful() ? self::SUCCESS : self::FAILURE;
        }
        if ($this->option('release-legacy')) {
            $this->error('ID-only release is disabled. Review a full --release-incident manifest instead.');
            return self::FAILURE;
        }
        if ($path = $this->option('release-incident')) {
            $bytes = file_get_contents($path);
            $manifest = json_decode($bytes, true, 32, JSON_THROW_ON_ERROR);
            if (!hash_equals(hash('sha256', $bytes), (string) $this->option('approve-sha256'))
                || ($manifest['incident_id'] ?? null) !== $incident || ($manifest['version'] ?? null) !== $version
                || !\Illuminate\Support\Str::isUuid($manifest['probe_evidence_id'] ?? '')
                || count($manifest['legacy_rows'] ?? []) !== 12) {
                $this->error('Release manifest, incident/version or approval hash does not match.');
                return self::FAILURE;
            }
            $result = DB::selectOne('select public.release_provider_incident_v2(?::uuid,?::bigint,?::uuid,?,?::jsonb) as released',
                [$incident, $version, $manifest['probe_evidence_id'], $this->option('actor'),
                    json_encode($manifest['legacy_rows'], JSON_THROW_ON_ERROR)]);
            $this->line($result->released);
            return self::SUCCESS;
        }
        $this->line('DRY RUN: no state changed. Review provider:status; use --probe, then separately review --release-incident.');
        return self::SUCCESS;
    }
}
