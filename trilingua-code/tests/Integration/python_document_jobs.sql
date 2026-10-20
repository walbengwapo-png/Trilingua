-- Run only against a disposable local PostgreSQL database after Laravel migrations.
\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE
    first_job public.python_document_jobs;
    second_job public.python_document_jobs;
    new_id uuid := gen_random_uuid();
    claimed_count integer;
BEGIN
    IF current_database() <> 'trilingua_engine_test' THEN
        RAISE EXCEPTION 'Refusing to run queue mutation tests outside trilingua_engine_test';
    END IF;
    IF has_table_privilege('anon', 'public.python_document_jobs', 'SELECT') OR
       has_function_privilege('authenticated', 'public.claim_python_document_job()', 'EXECUTE') THEN
        RAISE EXCEPTION 'Anonymous/authenticated clients can access the internal queue';
    END IF;
    INSERT INTO public.python_document_jobs(id, fingerprint, filename, input_path, options)
    VALUES (gen_random_uuid(), 'one', 'source.txt', 'one/input', '{}'),
           (gen_random_uuid(), 'two', 'source.txt', 'two/input', '{}');
    SELECT * INTO first_job FROM public.claim_python_document_job();
    SELECT * INTO second_job FROM public.claim_python_document_job();
    IF first_job.id IS NULL OR second_job.id IS NULL OR first_job.id = second_job.id OR
       EXISTS(SELECT 1 FROM public.claim_python_document_job()) THEN
        RAISE EXCEPTION 'Queue claim did not reserve distinct jobs';
    END IF;
    IF public.finish_python_document_job(first_job.id, gen_random_uuid(), 'wrong/result') THEN
        RAISE EXCEPTION 'Wrong lease was allowed to complete';
    END IF;
    IF NOT public.renew_python_document_job(first_job.id, first_job.lease_id) THEN
        RAISE EXCEPTION 'Active lease could not renew';
    END IF;
    UPDATE public.python_document_jobs SET lease_until = now() - interval '1 second' WHERE id = first_job.id;
    IF public.renew_python_document_job(first_job.id, first_job.lease_id) OR
       public.finish_python_document_job(first_job.id, first_job.lease_id, 'late/result') THEN
        RAISE EXCEPTION 'Expired lease was revived or completed';
    END IF;
    PERFORM public.claim_python_document_job();
    IF NOT EXISTS(SELECT 1 FROM public.python_document_jobs WHERE id = first_job.id AND status = 'failed' AND error_status = 408) THEN
        RAISE EXCEPTION 'Dead worker was replayed instead of failed';
    END IF;
    IF NOT public.finish_python_document_job(second_job.id, second_job.lease_id, NULL, 'Provider stopped', 429) THEN
        RAISE EXCEPTION 'Terminal provider failure could not be stored';
    END IF;
    INSERT INTO public.python_document_jobs(id, fingerprint, filename, input_path, options)
    VALUES (new_id, 'three', 'source.txt', 'three/input', '{}');
    SELECT count(*) INTO claimed_count FROM public.claim_python_document_job();
    IF claimed_count <> 0 OR NOT EXISTS(SELECT 1 FROM public.python_document_jobs WHERE id = new_id AND status = 'failed' AND error_status = 429) THEN
        RAISE EXCEPTION 'Persisted provider stop did not block new work';
    END IF;
    RAISE NOTICE 'Queue assertions passed: restricted access, distinct claims, renewal, lease fencing, terminal expiry, persistent provider stop';
END;
$$;
ROLLBACK;
