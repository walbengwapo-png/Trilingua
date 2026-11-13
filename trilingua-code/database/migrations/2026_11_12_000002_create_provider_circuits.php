<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        DB::unprepared(file_get_contents(database_path('sql/provider_circuits.sql')));
    }

    public function down(): void
    {
        // Drain workers first. Keep historical job errors intact.
        DB::unprepared('DROP FUNCTION IF EXISTS public.release_legacy_provider_markers_v1(uuid,bigint,uuid[]),
            public.release_provider_incident_v2(uuid,bigint,uuid,text,jsonb),public.record_provider_probe_v1(text,uuid,bigint,uuid,jsonb),
            public.claim_python_document_job_v2(), public.cancel_provider_probe_v1(text,uuid,bigint,uuid), public.lease_provider_recovery_v1(text,uuid,bigint,text),
            public.finish_provider_circuit_v1(text,uuid,bigint,uuid,jsonb,text), public.acquire_provider_circuit_v1(text)');
        DB::unprepared('DROP TABLE public.provider_circuits');
    }
};
