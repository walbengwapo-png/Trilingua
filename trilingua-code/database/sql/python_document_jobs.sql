ALTER TABLE public.python_document_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.python_document_jobs FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.python_document_jobs TO service_role;

CREATE FUNCTION public.claim_python_document_job()
RETURNS SETOF public.python_document_jobs
LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    -- A dead worker may have spent AI credits: never automatically replay its work.
    UPDATE public.python_document_jobs
    SET status = 'failed', error_status = 408,
        error = 'Document worker stopped or exceeded its deadline. Explicit operator retry is required.', updated_at = now()
    WHERE (status = 'processing' AND (lease_until <= now() OR deadline <= now()))
       OR (status = 'queued' AND created_at < now() - interval '20 minutes');

    -- Keep terminal provider failures latched across Cloud process restarts.
    IF EXISTS (SELECT 1 FROM public.python_document_jobs
               WHERE error_status = 429 AND NOT provider_stop_released) THEN
        UPDATE public.python_document_jobs SET status = 'failed', error_status = 429,
            error = 'AI provider is stopped. An operator must resolve credentials or quota before retrying.', updated_at = now()
        WHERE status = 'queued';
        RETURN;
    END IF;

    RETURN QUERY
    UPDATE public.python_document_jobs j
    SET status = 'processing', lease_id = pg_catalog.gen_random_uuid(),
        lease_until = now() + interval '90 seconds', deadline = now() + interval '20 minutes', updated_at = now()
    WHERE j.id = (SELECT q.id FROM public.python_document_jobs q WHERE q.status = 'queued'
                  ORDER BY q.created_at FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING j.*;
END;
$$;

CREATE FUNCTION public.renew_python_document_job(job_id uuid, lease_id uuid)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
    WITH renewed AS (
        UPDATE public.python_document_jobs j
        SET lease_until = least(now() + interval '90 seconds', j.deadline), updated_at = now()
        WHERE j.id = $1 AND j.lease_id = $2 AND j.status = 'processing'
          AND j.lease_until > now() AND j.deadline > now()
        RETURNING j.id
    ) SELECT EXISTS(SELECT 1 FROM renewed);
$$;

CREATE FUNCTION public.finish_python_document_job(job_id uuid, lease_id uuid,
    result_path text DEFAULT NULL, error text DEFAULT NULL, error_status integer DEFAULT NULL)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
    WITH finished AS (
        UPDATE public.python_document_jobs j
        SET status = CASE WHEN $3 IS NULL THEN 'failed' ELSE 'completed' END,
            result_path = $3, error = $4, error_status = $5, updated_at = now()
        WHERE j.id = $1 AND j.lease_id = $2 AND j.status = 'processing'
          AND j.lease_until > now() AND j.deadline > now()
        RETURNING j.id
    ) SELECT EXISTS(SELECT 1 FROM finished);
$$;

REVOKE EXECUTE ON FUNCTION public.claim_python_document_job(),
    public.renew_python_document_job(uuid, uuid), public.finish_python_document_job(uuid, uuid, text, text, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_python_document_job(),
    public.renew_python_document_job(uuid, uuid), public.finish_python_document_job(uuid, uuid, text, text, integer)
    TO service_role;
