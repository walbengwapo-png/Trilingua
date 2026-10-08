# TriLingua on Laravel Cloud

This repository contains two HTTP applications. Keep the existing Laravel/Python separation and the existing Supabase database/storage. No local PC process is needed once both applications are deployed. A successful build alone does not verify translations or production operation.

**Cloud document protocol prepared on 2026-10-09:** both applications retain Cloud's 60-second HTTP ceiling. With `PYTHON_DOCUMENT_JOBS=true` on Laravel and `DOCUMENT_JOBS_ENABLED=true` on Python, Laravel submits a durable document job and polls using requests capped at 45 seconds. The engine processes the document outside the HTTP request, using the existing Supabase database and private `trailingua` bucket. The 1,200-second setting is the total processing budget. This implementation has passed local tests; production deployment and end-to-end acceptance remain required.

## Cost and required settings

Laravel Cloud Starter is $5/month with $5 in monthly usage credit; additional compute, storage and traffic are metered. It is not a $5 fixed-price server. Check the Cloud cost estimate and spending limit before enabling resources. Two applications and a continuously running database queue worker consume compute independently.

The user authorizes included credits only. The saved organization spending limit is **$5 with Stop compute at the limit**. Usage was approximately $0.01 when verified; refresh before starting compute. The current Starter subscription fee is separate from usage credit. Cloud permits in-flight work to finish and can exceed a limit slightly, so this control is not an absolute no-charge guarantee. Do not purchase credits, raise the limit, upgrade resources or add managed resources under this authorization.

For the current database queue, turn **Scale-to-Zero off on the Laravel application**. Otherwise, a long translation job may be interrupted when the sleep timer expires. Keep the Python application awake during the initial validation as well. Changing to Cloud managed queues is a separate architecture change and requires revalidating dispatch/reconciliation; do not accept an automatic `QUEUE_CONNECTION=cloud` override for this release.

## Laravel application

Connect `walbengwapo-png/Trilingua`, branch `main`, application root `trilingua-code`. Cloud currently selects PHP 8.5 and Node 24; use one replica and one queue worker. Disable Octane for this release. Copy the names from `.env.cloud.example` into Cloud settings and supply real values using secrets. Do not upload the local `.env` or commit filled templates.

Keep the existing Supabase database rather than attaching a new empty database. Obtain its connection details from Supabase's Connect dialog. Use a direct connection or session pooler for persistent workers; use TLS. If a transaction pooler is needed, the existing PostgreSQL config emulates prepared statements. The application uses its own Laravel user accounts, not Supabase Auth. Keep the translations bucket private and the service-role key server-side.

Use `SESSION_DRIVER=database` and `CACHE_STORE=database` so sessions and maintenance locks survive redeploys. The existing migrations create the sessions/cache/jobs tables. `FALLBACK_STORAGE_ENABLED=false` is required here because container-local files are temporary. Supabase remains the durable upload/output store; storage failures must fail visibly.

Build commands:

```sh
composer install --no-dev --no-interaction --prefer-dist --optimize-autoloader
npm ci --no-audit --no-fund
npm run build
php artisan deployment:validate-production
php artisan optimize
```

Deploy commands (take and verify a database backup before the first rollout):

```sh
php artisan migrate --force
php artisan deployment:validate-production --check-migrations
```

Migration `2026_10_08_161834_create_python_document_jobs_table` creates the internal engine queue, PostgreSQL lease functions and `translation_jobs.engine_job_uuid`. Apply it before enabling Python's durable worker. RLS and revoked anonymous/authenticated grants keep this queue server-only; the Python service-role secret grants access. The previous provider-usage migration also remains part of the rollout. Never run `migrate:fresh`, a seed or a rollback against the existing database.

Both migrations were applied to the existing Supabase database on 2026-10-09 after backup/restore verification. All 35 migrations are applied. Existing counts remain 1 user, 15 history records and 59 storage objects. The service-role queue/table RPC returned 200; anonymous requests returned 401. Cloud compute has not been deployed, and the browser-control connection is currently unavailable. The user confirmed correcting the shared token; live service authentication still needs verification.

Configure one custom background process on the App cluster:

```sh
php artisan queue:work database --queue=default --sleep=3 --tries=3 --timeout=1500
```

Enable Cloud's Scheduler toggle for the existing reconciliation and storage cleanup tasks. The timeout ordering must remain `1200 < 1300 < 1500 < 1800 < 2100` seconds. Set the Cloud graceful shutdown limit long enough for in-flight work or drain the queue before redeploying. The validation command checks configuration and schema; it does not inspect the actual Cloud worker/sleep settings.

Use the Cloud-generated HTTPS URL for `APP_URL`. Keep one stable `APP_KEY` across releases. Configure Google's redirect URI as `<APP_URL>/auth/google/callback` if Google sign-in is enabled. Supply working SMTP credentials for password-reset emails. Set PHP `upload_max_filesize` and `post_max_size` to cover the advertised 50 MiB upload limit, and verify Cloud's ingress/request limits with representative documents.

## Python application

The Python root is `trilingua-code/Model`, with runtime dependencies in `requirements.txt`. No local model download or provider warm-up is required. The pinned `pymupdf-fonts` package provides Noto fonts for PDF punctuation and Philippine peso symbols when Windows fonts are unavailable.

A Cloud FastAPI application named `trilingua-python` has been created in Singapore, but remains undeployed. Cloud reads `.python-version` from this root and installs runtime dependencies during the build. The build command is `python -m pip check`; no deploy command is required. Enable durable document jobs only after the shared schema migration and private-bucket check succeed.

Start command:

```sh
uvicorn server:app --host :: --port $PORT --workers 1
```

Keep one replica and drain document work before a redeploy; increasing Uvicorn's shutdown timeout does not override a platform termination limit. Text translation and document regeneration still use synchronous HTTP calls and retain the 60-second ceiling. Small live calls must be tested; long text/regeneration calls are not made reliable by the document queue.

Use `.env.cloud.example` in this root as the environment template. Set `APP_ENV=production` and the **same random `PYTHON_SERVICE_TOKEN`** on both applications (at least 32 characters). Put this application's HTTPS URL into Laravel's `PYTHON_SERVICE_URL`. Set the Python health check to `/health`.

Supply `OLLAMA_API_KEY` only to Python. On 2026-10-09 the supplied key authenticated as Free, and one minimal request to each selected model returned HTTP 200 with completed output. This verifies key/model access, not translation quality or remaining free allowance. The chosen profile uses `gpt-oss:20b` for translation, `gemma4:31b` for blind review, and both fallbacks set to `none`. Different model families do not prove accuracy or independence. Use `https://ollama.com/api/chat`, one Uvicorn worker, `TRANSLATION_MAX_CONCURRENT=1`, `DOCUMENT_MAX_CONCURRENT=1`, `GPTOSS_TRANSLATION_SLOTS=1` and `OLLAMA_ANALYSIS_MAX_ATTEMPTS=1`. Terminal authentication/quota errors prohibit retries/fallback. Do not automatically restart to clear a quota stop.

Python also needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_BUCKET=trailingua`. The existing bucket was made private on 2026-10-09; all 59 objects were retained, a signed download returned 200, and unsigned/anonymous reads were denied. Python verifies the private bucket and queue table at startup. Reuse the existing bucket; no Cloud bucket is needed.

## Durable document lifecycle

Laravel retains the same engine UUID through connection retries. `POST /translate/document/jobs` returns 202 after storing the input and queue row. Reusing the same UUID/payload does not translate again; a different payload with that UUID returns 409. Python claims rows using `FOR UPDATE SKIP LOCKED`, a 90-second lease, heartbeat every 20 seconds and a 20-minute processing deadline. Results are stored before completion is recorded. Laravel polls status, downloads the old JSON envelope, persists history/blocks/output, and then acknowledges the temporary engine files.

An expired worker is failed with 408 rather than replayed automatically, because it may already have consumed AI credits. A failed 429 document row blocks new engine claims across process restarts. Resolve the actual provider problem first; then explicitly mark the affected stop rows `provider_stop_released=true`, deliberately restart the stopped process if needed, and recover the Laravel job through its existing operator workflow. Recovery clears the engine UUID to create a fresh attempt. Never automatically clear stops or replay expired work.

Completed acknowledgement removes only temporary `engine-jobs/` input/result files. Failed or unacknowledged files remain for operator investigation/cleanup; monitor bucket quota. An AI call already in flight cannot be canceled merely by losing a lease. SQL state fencing prevents a stale worker from committing completion. Drain jobs before deployment rather than relying on Cloud's 30-second Python termination grace.

The optional NLLB route needs separately installed model dependencies and substantially more memory; it is not part of this small hosted configuration. The unit pipeline remains disabled pending its release gates. Tune compute size only after measuring peak memory on representative DOCX/PDF/PPTX/XLSX files; a low-cost instance is not proof that every 50 MiB upload will fit.

## First deployment acceptance

Before routing real users, verify all of these against the deployed applications:

1. `/up` and Python `/health` return successfully; Python startup consumes no provider calls. A translation endpoint without `X-Service-Token` is rejected.
2. Login and CSRF-protected forms work over HTTPS; session cookies remain secure; login survives a redeploy.
3. Run one text translation and one representative document job within a confirmed provider budget. Confirm history, user ownership, private storage, download, and admin review/regeneration. Automated quality scores are not human-verified accuracy.
4. Confirm the database queue worker runs, jobs finish after the browser is closed, schedules run, and output survives a redeploy with the PC off.
5. Test provider/storage interruption and PostgreSQL queue races in a staging database; do not run destructive tests against the existing database.
6. Verify password-reset mail and Google login if configured, measure memory/latency, and obtain bilingual meaning/layout review before claiming translation quality.

Verification on 2026-10-09: the Laravel full suite passed 504 tests, followed by 23 affected tests after additional changes. The Python offline CI profile passed 419 tests with outbound network disabled (35 intentionally excluded). A disposable PostgreSQL 17.11 database passed actual queue ACL, renewal, lease-fencing, expiration and provider-stop assertions. Two concurrent transactions claimed distinct jobs while the first row remained locked. The encrypted Supabase public-schema/data backup was restored locally and contained 1 user, 15 history records and 33 migrations. This backup excludes Storage file contents and other database schemas. Live Cloud integration, representative memory/ingress tests and human linguistic review remain unverified.

Dependency limit: `npm audit` still reports the moderate [sprintf-js advisory](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) through Mammoth's CLI-only `argparse` dependency. The app imports `mammoth/mammoth.browser`, which does not include that CLI path. Do not expose Mammoth's CLI to attacker-controlled format strings. `ponytail:` retain the browser preview; update or replace this dependency when a compatible upstream fix exists. Avoid `npm audit fix --force`, which currently proposes downgrading Mammoth to an obsolete release.

## Sources checked on 2026-10-08

- [Cloud pricing](https://laravel.com/cloud/docs/pricing)
- [Cloud spending limits](https://laravel.com/cloud/docs/spending-limits)
- [Monorepo applications](https://laravel.com/cloud/docs/monorepos)
- [Laravel production deployment](https://laravel.com/cloud/docs/deploy-guides/laravel)
- [Python production deployment](https://laravel.com/cloud/docs/deploy-guides/python)
- [Background workers](https://laravel.com/cloud/docs/workers) and [Scale-to-Zero](https://laravel.com/cloud/docs/compute)
- [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase private buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals)
- [Ollama authentication](https://docs.ollama.com/api/authentication) and [usage pricing](https://ollama.com/pricing)
- [PyMuPDF optional font assets](https://pymupdf.readthedocs.io/en/latest/font.html)
