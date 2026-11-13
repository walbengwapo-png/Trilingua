-- Additive: the original finish RPC remains callable by old workers.
CREATE OR REPLACE FUNCTION public.finish_python_document_job_v2(job_id uuid, lease_id uuid,
    result_path text DEFAULT NULL, error text DEFAULT NULL, error_status integer DEFAULT NULL,
    error_details jsonb DEFAULT NULL)
RETURNS boolean LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
    WITH finished AS (
        UPDATE public.python_document_jobs j
        SET status = CASE WHEN $3 IS NULL THEN 'failed' ELSE 'completed' END,
            result_path = $3, error = $4, error_status = $5, error_details = $6, updated_at = now()
        WHERE j.id = $1 AND j.lease_id = $2 AND j.status = 'processing'
          AND j.lease_until > now() AND j.deadline > now()
        RETURNING j.id
    ) SELECT EXISTS(SELECT 1 FROM finished);
$$;
REVOKE EXECUTE ON FUNCTION public.finish_python_document_job_v2(uuid, uuid, text, text, integer, jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_python_document_job_v2(uuid, uuid, text, text, integer, jsonb)
    TO service_role;
