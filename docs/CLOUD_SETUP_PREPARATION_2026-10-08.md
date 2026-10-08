# TriLingua Cloud setup preparation — 2026-10-08

The user chose **preparation only; do not start paid compute**. No deployment was started, compute upgraded, live AI request made, or credential copied to Cloud in this work.

## Prepared and verified

- Used deployed `main` commit `63fbcbe2553baa61afeb595e41b5fbb54d0ca7ff` as the source baseline in an attached worktree, branch `codex/cloud-python-2026-10-08`. The original dirty `C:\dev\Trilingua` checkout was preserved.
- Created the undeployed Cloud application `trilingua-python` in Singapore, root `/trilingua-code/Model`, detected framework FastAPI, Python 3.11. No Python compute is running.
- Saved Python build command `python -m pip check`, start command `uvicorn server:app --host :: --port $PORT --workers 1`, and an HTTP timeout of 60 seconds. Push-to-deploy and the deploy hook are disabled. No deploy command is needed for this service.
- Saved Laravel's scheduler and one database queue process as pending changes: `php artisan queue:work database --queue=default --sleep=3 --timeout=1500 --tries=3`. Laravel's current 512 MiB size and sleep setting were retained.
- Restored `php artisan deployment:validate-production` in Laravel's saved build commands and `php artisan deployment:validate-production --check-migrations` after `migrate --force` in its saved deploy commands. The validator also calls the timeout checks. These and the worker/scheduler changes remain pending, not deployed.
- Prepared the Python environment template and saved its 19 non-secret settings in Cloud for GPT-OSS `gpt-oss:20b` translation and Gemma `gemma4:31b` blind review through Ollama Cloud. Both fallbacks are disabled; API key and shared service token remain absent from Cloud.
- Added bundled Noto PDF fonts and a regression that preserves curly quotes, em dash, ellipsis and `₱` when Windows fonts are unavailable. The PDF test file passed 18 tests, and all four Noto weight/style variants cover those glyphs.
- Passed 49 offline provider safety, accounting and analysis tests. `pip check` and `git diff --check` passed. These results do not establish live provider access or linguistic quality.
- Restored the existing Supabase project and verified it is healthy. Enabled RLS on all 18 application tables; anonymous reads of users/history were verified blocked. Laravel's existing `postgres` role bypasses RLS. Retained 1 user, 15 history rows and 59 storage objects. The security advisor now reports informational no-policy notices, consistent with Laravel owning database authorization.

## Blockers before any deployment

1. Choose the Python host and approve its cost. Cloud's HTTP timeout range is 5–60 seconds for both applications, whereas the current Python document call is synchronous and Laravel allows 1,200 seconds. Keeping Python on Cloud requires durable background work with polling; this change has not been implemented. Render documents a 100-minute HTTP limit and lists 2 GB/1 CPU at $25/month. That service was not created.
2. Approve credential entry and provide the Ollama key directly to the approved host's secret manager. Laravel needs the existing Supabase database/storage credentials, a stable existing Cloud `APP_KEY`, and the Python HTTPS URL. Both applications need the same random service token of at least 32 characters. No secrets belong in this repository.
3. Make the existing storage bucket `trailingua` private and verify signed downloads. It is currently public; no bucket permission was changed. The current Laravel implementation already generates signed URLs.
4. Take and verify a database backup before running the pending Laravel migration `2026_10_05_000001_add_provider_usage_to_translation_metrics`. It adds nullable usage metadata/counters; no Laravel migration, reset, seed or data deletion was performed here.
5. Complete the Laravel Cloud environment settings before using the saved production validator; it deliberately rejects missing/unsafe configuration. Disable Laravel sleep before serving long database-queue jobs, and drain work before redeploying.
6. Run deployed health, authentication, storage, text/document and queue acceptance checks. The live Laravel `/up` endpoint returned HTTP 500 before preparation; the site has not been made operational in this preparation-only scope. No actual Linux deployment/render, live AI translation, load test or human language review was performed.

See [the deployment guide](LARAVEL_CLOUD_DEPLOYMENT.md) for build commands, environment names and acceptance criteria. Different reviewer/translator model families do not establish unbiased or accurate output.

## Latest deployment constraint: free tiers only

The user subsequently requested a functional deployed version, then clarified that no cash or credit should be spent. No paid compute is authorized. The Ollama API key has not yet been supplied.

- Reducing Cloud compute to 512 MiB does not make it free. Cloud Starter is $5/month plus usage after its introductory period; active compute consumes usage credits.
- Render offers free web services, but they sleep after 15 idle minutes, share 750 running hours per workspace/month, and may restart or be suspended. There are no free dedicated worker or cron service types. PHP needs a Docker deployment; this repository does not yet contain that deployment. Queue processing and scheduling need an explicit tested approach within the free web service.
- Render free services block common SMTP ports 25, 465 and 587. The current SMTP template cannot be assumed to deliver password-reset emails there; an HTTPS mail transport and account access would need verification.
- Ollama Free includes limited starter usage and starter model access, with one concurrent request. Access to both selected models within the user's free allowance is unverified. No AI calls, credit purchases or upgrades were made.
- The Laravel environment example now names the existing bucket `trailingua`; no replacement bucket is needed. The existing bucket remains public until its privacy setting is changed and signed downloads are checked.

Moving both services to a free Render demo has been presented for the user's decision. It has not been approved or deployed, and the free tier is not evidence of reliable continuous production operation.

Current sources: [Cloud pricing](https://laravel.com/cloud/docs/pricing), [Cloud trial](https://laravel.com/cloud/docs/free-trial), [Render free limits](https://render.com/docs/free), [Ollama pricing and free usage](https://ollama.com/pricing).

Sources: [Cloud Python deployment](https://laravel.com/cloud/docs/deploy-guides/python), [Cloud pricing](https://laravel.com/cloud/docs/pricing), [Render request duration](https://render.com/docs/render-vs-heroku-comparison), [Render pricing](https://render.com/pricing), [private Supabase buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals), [PyMuPDF font assets](https://pymupdf.readthedocs.io/en/latest/font.html).
