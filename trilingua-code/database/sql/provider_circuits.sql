CREATE TABLE public.provider_circuits (
    scope text PRIMARY KEY,
    state text NOT NULL DEFAULT 'closed' CHECK (state IN ('closed','open','half_open','manual')),
    incident_id uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid(),
    version bigint NOT NULL DEFAULT 1,
    original_error jsonb,
    opened_at timestamptz,
    cooldown_until timestamptz,
    auto_probes integer NOT NULL DEFAULT 0 CHECK (auto_probes BETWEEN 0 AND 2),
    probe_lease uuid,
    probe_until timestamptz,
    manual_probe boolean NOT NULL DEFAULT false,
    probe_actor text,
    probe_evidence_id uuid,
    validated_at timestamptz,
    validated_models jsonb,
    release_actor text,
    released_at timestamptz
);
ALTER TABLE public.provider_circuits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.provider_circuits FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.provider_circuits TO service_role;
INSERT INTO public.provider_circuits(scope) VALUES ('ollama');
-- Preserve all job errors. Existing ambiguous 429s seed ONE explicit manual incident.
UPDATE public.provider_circuits SET state='manual', opened_at=now(),
    original_error='{"category":"legacy_cause_unknown","message":"Legacy cause unknown / manual stop"}'::jsonb
WHERE scope='ollama' AND EXISTS (
    SELECT 1 FROM public.python_document_jobs WHERE error_status=429 AND NOT provider_stop_released
);

CREATE FUNCTION public.acquire_provider_circuit_v1(circuit_scope text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits; allowed boolean := false;
BEGIN
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope=$1 FOR UPDATE;
    IF c.state='closed' THEN
        allowed := true;
    ELSIF c.state IN ('open','half_open') AND NOT c.manual_probe
        AND coalesce(c.cooldown_until, '-infinity'::timestamptz)<=now()
        AND coalesce(c.probe_until, '-infinity'::timestamptz)<=now() THEN
        IF c.auto_probes>=2 THEN
            UPDATE public.provider_circuits SET state='manual', probe_lease=NULL, probe_until=NULL
                WHERE scope=$1 RETURNING * INTO c;
        ELSE
            UPDATE public.provider_circuits SET state='half_open', auto_probes=auto_probes+1,
                probe_lease=pg_catalog.gen_random_uuid(), probe_until=now()+interval '60 seconds'
                WHERE scope=$1 RETURNING * INTO c;
            allowed := true;
        END IF;
    END IF;
    RETURN pg_catalog.jsonb_build_object('allowed',allowed,'scope',c.scope,'incident_id',c.incident_id,
        'version',c.version,'probe_lease',CASE WHEN allowed THEN c.probe_lease END,
        'state',c.state,'original_error',c.original_error);
END;
$$;

CREATE FUNCTION public.finish_provider_circuit_v1(circuit_scope text, incident uuid, expected_version bigint,
    lease uuid, failure jsonb DEFAULT NULL, actor text DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits; hard boolean;
BEGIN
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope=$1 FOR UPDATE;
    IF c.incident_id IS DISTINCT FROM $2 OR c.version IS DISTINCT FROM $3 THEN RETURN false; END IF;
    IF c.state='closed' THEN
        IF $4 IS NOT NULL OR $5 IS NULL THEN RETURN false; END IF;
    ELSIF c.state<>'half_open' OR c.probe_lease IS DISTINCT FROM $4
        OR c.probe_until<=now() THEN RETURN false;
    END IF;
    IF $5 IS NULL THEN
        IF c.manual_probe THEN RETURN false; END IF; -- Manual probes require a separately approved release.
        UPDATE public.provider_circuits SET state='closed',version=version+1,
            probe_lease=NULL,probe_until=NULL,manual_probe=false,cooldown_until=NULL,
            release_actor=coalesce($6,'automatic probe'),released_at=now() WHERE scope=$1;
    ELSE
        hard := ($5->>'category') IN ('credentials','billing','quota_exhausted','permission');
        UPDATE public.provider_circuits SET
            state=CASE WHEN hard OR c.manual_probe OR c.auto_probes>=2 THEN 'manual' ELSE 'open' END,
            incident_id=CASE WHEN c.state='closed' THEN pg_catalog.gen_random_uuid() ELSE c.incident_id END,
            version=version+1,
            original_error=CASE WHEN c.state='closed' THEN $5 ELSE c.original_error END,
            opened_at=CASE WHEN c.state='closed' THEN now() ELSE c.opened_at END,
            cooldown_until=CASE WHEN hard OR c.manual_probe OR c.auto_probes>=2 THEN NULL ELSE now()+interval '30 seconds' END,
            auto_probes=CASE WHEN c.state='closed' THEN 0 ELSE c.auto_probes END,
            probe_lease=NULL,probe_until=NULL,manual_probe=false,
            release_actor=NULL,released_at=NULL WHERE scope=$1;
    END IF;
    RETURN true;
END;
$$;

CREATE FUNCTION public.lease_provider_recovery_v1(circuit_scope text, incident uuid, expected_version bigint, actor text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits;
BEGIN
    IF nullif(btrim($4),'') IS NULL THEN RAISE EXCEPTION 'Recovery actor required'; END IF;
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope=$1 FOR UPDATE;
    IF c.incident_id IS DISTINCT FROM $2 OR c.version IS DISTINCT FROM $3 OR c.state='closed'
        OR coalesce(c.probe_until,'-infinity'::timestamptz)>now() THEN
        RETURN pg_catalog.jsonb_build_object('allowed',false);
    END IF;
    UPDATE public.provider_circuits SET state='half_open',manual_probe=true,
        probe_evidence_id=NULL,validated_at=NULL,validated_models=NULL,
        probe_lease=pg_catalog.gen_random_uuid(),probe_until=now()+interval '60 seconds',probe_actor=$4
        WHERE scope=$1 RETURNING * INTO c;
    RETURN pg_catalog.jsonb_build_object('allowed',true,'scope',c.scope,'incident_id',c.incident_id,
        'version',c.version,'probe_lease',c.probe_lease,'actor',$4);
END;
$$;

CREATE FUNCTION public.record_provider_probe_v1(circuit_scope text, incident uuid, expected_version bigint,
    lease uuid, models jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits;
BEGIN
    IF pg_catalog.jsonb_typeof($5) IS DISTINCT FROM 'array' OR pg_catalog.jsonb_array_length($5)<>2 THEN
        RAISE EXCEPTION 'Two validated model probes required';
    END IF;
    IF (SELECT count(DISTINCT p->>'model') FROM pg_catalog.jsonb_array_elements($5) p
        WHERE p->>'valid'='true' AND p->>'purpose' IN ('translation','analysis'))<>2 THEN
        RAISE EXCEPTION 'Two distinct successful model probes required';
    END IF;
    UPDATE public.provider_circuits SET state='manual',version=version+1,
        probe_evidence_id=pg_catalog.gen_random_uuid(),validated_at=now(),validated_models=$5,
        probe_lease=NULL,probe_until=NULL,manual_probe=false
    WHERE scope=$1 AND incident_id=$2 AND version=$3 AND probe_lease=$4 AND probe_until>now()
        AND state='half_open' AND manual_probe RETURNING * INTO c;
    IF NOT FOUND THEN RAISE EXCEPTION 'Stale model probe'; END IF;
    RETURN pg_catalog.jsonb_build_object('incident_id',c.incident_id,'version',c.version,
        'probe_evidence_id',c.probe_evidence_id,'validated_at',c.validated_at,'models',c.validated_models);
END;
$$;

CREATE FUNCTION public.cancel_provider_probe_v1(circuit_scope text, incident uuid, expected_version bigint, lease uuid)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
    WITH cancelled AS (
        UPDATE public.provider_circuits SET state=CASE WHEN manual_probe THEN 'manual' ELSE 'open' END,
            auto_probes=greatest(0,auto_probes-CASE WHEN manual_probe THEN 0 ELSE 1 END),
            probe_lease=NULL,probe_until=NULL,manual_probe=false,version=version+1
        WHERE scope=$1 AND incident_id=$2 AND version=$3 AND probe_lease=$4 AND state='half_open'
        RETURNING scope
    ) SELECT EXISTS(SELECT 1 FROM cancelled);
$$;

-- Versioned queue claim uses explicit circuit state, never historical job errors.
CREATE FUNCTION public.claim_python_document_job_v2()
RETURNS SETOF public.python_document_jobs LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits;
BEGIN
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope='ollama';
    UPDATE public.python_document_jobs SET status='failed',error_status=408,
        error='Document lease expired. Operator review required.',
        error_details=pg_catalog.jsonb_build_object('category','lease_expired'),updated_at=now()
        WHERE (status='processing' AND (lease_until<=now() OR deadline<=now()))
        OR (status='queued' AND created_at<now()-interval '20 minutes');
    IF c.state='manual' OR (c.state='half_open' AND c.manual_probe) THEN
        UPDATE public.python_document_jobs SET status='failed',error_status=503,
            error='AI provider requires operator review. The original document is retained.',
            error_details=pg_catalog.jsonb_build_object('category','provider_blocked',
                'incident_id',c.incident_id,'version',c.version,'original_error',c.original_error),updated_at=now()
            WHERE status='queued';
        RETURN;
    END IF;
    IF c.state<>'closed' AND (coalesce(c.cooldown_until,'-infinity'::timestamptz)>now()
        OR coalesce(c.probe_until,'-infinity'::timestamptz)>now()) THEN RETURN; END IF;
    RETURN QUERY UPDATE public.python_document_jobs j SET status='processing',
        lease_id=pg_catalog.gen_random_uuid(),lease_until=now()+interval '90 seconds',
        deadline=now()+interval '20 minutes',updated_at=now()
        WHERE j.id=(SELECT q.id FROM public.python_document_jobs q WHERE q.status='queued'
            ORDER BY q.created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING j.*;
END;
$$;

CREATE FUNCTION public.release_legacy_provider_markers_v1(incident uuid, expected_version bigint, reviewed_ids uuid[])
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits; changed integer;
BEGIN
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope='ollama' FOR UPDATE;
    IF c.incident_id IS DISTINCT FROM $1 OR c.version IS DISTINCT FROM $2 OR c.state<>'closed' OR c.release_actor IS NULL
        OR c.release_actor='automatic probe' THEN
        RAISE EXCEPTION 'Named incident must first pass a manual recovery probe';
    END IF;
    IF cardinality($3)<>12 OR (SELECT count(DISTINCT x) FROM unnest($3) x)<>12
        OR (SELECT count(*) FROM public.python_document_jobs WHERE id=ANY($3) AND error_status=429)<>12 THEN
        RAISE EXCEPTION 'Expected twelve reviewed legacy 429 job IDs';
    END IF;
    UPDATE public.python_document_jobs SET provider_stop_released=true
        WHERE id=ANY($3) AND NOT provider_stop_released;
    GET DIAGNOSTICS changed=ROW_COUNT;
    RETURN changed;
END;
$$;

CREATE FUNCTION public.release_provider_incident_v2(incident uuid, expected_version bigint, evidence uuid,
    actor text, reviewed_rows jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c public.provider_circuits; matched integer; ids uuid[]; changed integer;
BEGIN
    IF nullif(btrim($4),'') IS NULL OR pg_catalog.jsonb_typeof($5) IS DISTINCT FROM 'array'
        OR pg_catalog.jsonb_array_length($5)<>12 THEN RAISE EXCEPTION 'Reviewed release manifest required'; END IF;
    SELECT * INTO STRICT c FROM public.provider_circuits WHERE scope='ollama' FOR UPDATE;
    IF c.incident_id IS DISTINCT FROM $1 OR c.version IS DISTINCT FROM $2
        OR c.probe_evidence_id IS NULL OR c.probe_evidence_id IS DISTINCT FROM $3
        OR c.validated_at IS NULL OR c.state<>'manual' THEN RAISE EXCEPTION 'Stale release manifest'; END IF;
    SELECT array_agg(m.id),count(DISTINCT m.id) INTO ids,matched
        FROM pg_catalog.jsonb_to_recordset($5) AS m(id uuid);
    IF matched<>12 THEN RAISE EXCEPTION 'Twelve unique reviewed rows required'; END IF;
    PERFORM j.id FROM public.python_document_jobs j WHERE j.id=ANY(ids) ORDER BY j.id FOR UPDATE;
    SELECT count(*) INTO matched FROM pg_catalog.jsonb_to_recordset($5) AS m(id uuid,created_at timestamptz,
        updated_at timestamptz,status text,error text,error_status integer,provider_stop_released boolean,row_sha256 text)
    JOIN public.python_document_jobs j ON j.id=m.id AND j.created_at=m.created_at AND j.updated_at=m.updated_at
        AND j.status=m.status AND j.error IS NOT DISTINCT FROM m.error AND j.error_status=m.error_status
        AND j.error_status=429 AND j.provider_stop_released=false AND m.provider_stop_released=false
        AND m.row_sha256=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.to_jsonb(j)::text,'UTF8')),'hex');
    IF matched<>12 THEN RAISE EXCEPTION 'A reviewed legacy row changed; release aborted'; END IF;
    UPDATE public.provider_circuits SET state='closed',version=version+1,release_actor=$4,released_at=now(),
        cooldown_until=NULL,probe_lease=NULL,probe_until=NULL,manual_probe=false WHERE scope='ollama'
        RETURNING * INTO c;
    changed := public.release_legacy_provider_markers_v1(c.incident_id,c.version,ids);
    IF changed<>12 THEN RAISE EXCEPTION 'Legacy release did not match twelve rows'; END IF;
    RETURN pg_catalog.jsonb_build_object('incident_id',c.incident_id,'version',c.version,'released_rows',changed);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.acquire_provider_circuit_v1(text),
    public.record_provider_probe_v1(text,uuid,bigint,uuid,jsonb),public.release_provider_incident_v2(uuid,bigint,uuid,text,jsonb),
    public.cancel_provider_probe_v1(text,uuid,bigint,uuid),
    public.finish_provider_circuit_v1(text,uuid,bigint,uuid,jsonb,text),
    public.lease_provider_recovery_v1(text,uuid,bigint,text), public.claim_python_document_job_v2(),
    public.release_legacy_provider_markers_v1(uuid,bigint,uuid[]) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.acquire_provider_circuit_v1(text),
    public.record_provider_probe_v1(text,uuid,bigint,uuid,jsonb),public.release_provider_incident_v2(uuid,bigint,uuid,text,jsonb),
    public.cancel_provider_probe_v1(text,uuid,bigint,uuid),
    public.finish_provider_circuit_v1(text,uuid,bigint,uuid,jsonb,text),
    public.lease_provider_recovery_v1(text,uuid,bigint,text), public.claim_python_document_job_v2(),
    public.release_legacy_provider_markers_v1(uuid,bigint,uuid[]) TO service_role;
