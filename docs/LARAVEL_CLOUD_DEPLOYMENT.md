# TriLingua on Laravel Cloud

This repository contains two HTTP applications. Keep the existing Laravel/Python separation and the existing Supabase database/storage. No local PC process is needed once both applications are deployed. A successful build alone does not verify translations or production operation.

## Cost and required settings

Laravel Cloud Starter is $5/month with $5 in monthly usage credit; additional compute, storage and traffic are metered. It is not a $5 fixed-price server. Check the Cloud cost estimate and spending limit before enabling resources. Two applications and a continuously running database queue worker consume compute independently.

For the current database queue, turn **Scale-to-Zero off on the Laravel application**. Otherwise, a long translation job may be interrupted when the sleep timer expires. Keep the Python application awake during the initial validation as well. Changing to Cloud managed queues is a separate architecture change and requires revalidating dispatch/reconciliation; do not accept an automatic `QUEUE_CONNECTION=cloud` override for this release.

## Laravel application

Connect `walbengwapo-png/Trilingua`, branch `main`, application root `trilingua-code`. Use PHP 8.3 or newer compatible with `composer.lock`, Node 22, one replica, one queue worker. Disable Octane for this release. Copy the names from `.env.cloud.example` into Cloud settings and supply real values using secrets. Do not upload the local `.env` or commit filled templates.

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

Configure one custom background process on the App cluster:

```sh
php artisan queue:work database --queue=default --sleep=3 --tries=3 --timeout=1500
```

Enable Cloud's Scheduler toggle for the existing reconciliation and storage cleanup tasks. The timeout ordering must remain `1200 < 1300 < 1500 < 1800 < 2100` seconds. Set the Cloud graceful shutdown limit long enough for in-flight work or drain the queue before redeploying. The validation command checks configuration and schema; it does not inspect the actual Cloud worker/sleep settings.

Use the Cloud-generated HTTPS URL for `APP_URL`. Keep one stable `APP_KEY` across releases. Configure Google's redirect URI as `<APP_URL>/auth/google/callback` if Google sign-in is enabled. Supply working SMTP credentials for password-reset emails. Set PHP `upload_max_filesize` and `post_max_size` to cover the advertised 50 MiB upload limit, and verify Cloud's ingress/request limits with representative documents.

## Python application

Create a second Cloud application from the same repository and branch, root `trilingua-code/Model`. Cloud supports FastAPI and reads `requirements.txt` plus `.python-version` from this root. Runtime dependencies are installed during the build; no model download or provider warm-up is required.

Start command:

```sh
uvicorn server:app --host :: --port $PORT --workers 1 --timeout-graceful-shutdown 1300
```

Use `.env.cloud.example` in this root as the environment template. Set `APP_ENV=production` and the **same random `PYTHON_SERVICE_TOKEN`** on both applications (at least 32 characters). Put this application's HTTPS URL into Laravel's `PYTHON_SERVICE_URL`. Set the Python health check to `/health`.

Supply the Ollama and Gemini keys only to the Python app. The Ollama endpoint must be `https://ollama.com/api/chat`, not localhost; confirm the selected models are available on your own accounts before translating. Keep one Uvicorn worker and one translation slot initially: terminal Ollama authentication/quota errors are latched per process and prohibit retries/fallback until a deliberate restart. Do not automatically restart the service merely to clear a quota stop.

The optional NLLB route needs separately installed model dependencies and substantially more memory; it is not part of this small hosted configuration. The unit pipeline remains disabled pending its release gates. Tune compute size only after measuring peak memory on representative DOCX/PDF/PPTX/XLSX files; a low-cost instance is not proof that every 50 MiB upload will fit.

## First deployment acceptance

Before routing real users, verify all of these against the deployed applications:

1. `/up` and Python `/health` return successfully; Python startup consumes no provider calls. A translation endpoint without `X-Service-Token` is rejected.
2. Login and CSRF-protected forms work over HTTPS; session cookies remain secure; login survives a redeploy.
3. Run one text translation and one representative document job within a confirmed provider budget. Confirm history, user ownership, private storage, download, and admin review/regeneration. Automated quality scores are not human-verified accuracy.
4. Confirm the database queue worker runs, jobs finish after the browser is closed, schedules run, and output survives a redeploy with the PC off.
5. Test provider/storage interruption and PostgreSQL queue races in a staging database; do not run destructive tests against the existing database.
6. Verify password-reset mail and Google login if configured, measure memory/latency, and obtain bilingual meaning/layout review before claiming translation quality.

Current local tests use SQLite and mocks. Live Cloud, PostgreSQL queue races, Supabase permissions, provider access, ingress timeouts and human translation quality require the checks above.

Dependency limit: `npm audit` still reports the moderate [sprintf-js advisory](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) through Mammoth's CLI-only `argparse` dependency. The app imports `mammoth/mammoth.browser`, which does not include that CLI path. Do not expose Mammoth's CLI to attacker-controlled format strings. `ponytail:` retain the browser preview; update or replace this dependency when a compatible upstream fix exists. Avoid `npm audit fix --force`, which currently proposes downgrading Mammoth to an obsolete release.

## Sources checked on 2026-10-08

- [Cloud pricing](https://laravel.com/cloud/docs/pricing)
- [Monorepo applications](https://laravel.com/cloud/docs/monorepos)
- [Laravel production deployment](https://laravel.com/cloud/docs/deploy-guides/laravel)
- [Python production deployment](https://laravel.com/cloud/docs/deploy-guides/python)
- [Background workers](https://laravel.com/cloud/docs/workers) and [Scale-to-Zero](https://laravel.com/cloud/docs/compute)
- [Supabase database connections](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase private buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals)
