-- READ ONLY. Run after additive migrations; this never acquires a probe or queue lease.
WITH expected(name) AS (VALUES
    ('claim_python_document_job'), ('renew_python_document_job'), ('finish_python_document_job'),
    ('finish_python_document_job_v2'), ('claim_python_document_job_v2'),
    ('acquire_provider_circuit_v1'), ('finish_provider_circuit_v1'), ('lease_provider_recovery_v1'),
    ('cancel_provider_probe_v1'), ('record_provider_probe_v1'),
    ('release_legacy_provider_markers_v1'), ('release_provider_incident_v2')
)
SELECT e.name, p.oid IS NOT NULL AS present,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    coalesce((SELECT bool_or(a.privilege_type='EXECUTE')
        FROM pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
        WHERE a.grantee=0),false) AS public_execute,
    pg_catalog.has_function_privilege('anon',p.oid,'EXECUTE') AS anon_execute,
    pg_catalog.has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_execute,
    pg_catalog.has_function_privilege('service_role',p.oid,'EXECUTE') AS service_execute
FROM expected e LEFT JOIN pg_catalog.pg_namespace n ON n.nspname='public'
LEFT JOIN pg_catalog.pg_proc p ON p.pronamespace=n.oid AND p.proname=e.name
ORDER BY e.name;

SELECT c.relname,c.relrowsecurity,r.rolname,
    pg_catalog.has_table_privilege(r.oid,c.oid,'SELECT') AS can_select,
    pg_catalog.has_table_privilege(r.oid,c.oid,'INSERT') AS can_insert,
    pg_catalog.has_table_privilege(r.oid,c.oid,'UPDATE') AS can_update,
    coalesce((SELECT bool_or(a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE'))
        FROM pg_catalog.aclexplode(coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) a
        WHERE a.grantee=0),false) AS public_dml
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN pg_catalog.pg_roles r
WHERE n.nspname='public' AND c.relname IN ('provider_circuits','python_document_jobs')
    AND r.rolname IN ('anon','authenticated','service_role') ORDER BY c.relname,r.rolname;
