# Phase 08 — Gate 0: Baseline and safe staging

**Date:** 2026-09-29
**Branch:** `walben`  **HEAD:** `cbbfc90` — `fix(auth): restrict auth routes and reconcile stale jobs`

## 1. Working-tree inventory (reference manifest — nothing staged, committed, stashed or reset)

Tracked changes: **91** (88 modified, 3 deleted). Untracked entries: **82**.

Deliberately **not** bundled into a baseline commit, per instruction. The inventory below is the
rollback reference: every subsequent edit in this plan is identifiable by its own diff.

### 3 deleted tracked paths

- `trilingua-code/.env.demo`
- `trilingua-code/check_buckets.php`
- `trilingua-code/pass.txt`

### 88 modified tracked paths, by area

| Area | Files |
| --- | --- |
| Laravel app | `app/Console/Commands/ReconcileTranslations.php`, `app/Http/Controllers/{Admin/DocumentReviewController,Admin/JobController,Admin/ReviewController,DocumentsController,HistoryController,TranslationController}.php`, `app/Jobs/TranslateDocumentJob.php`, `app/Models/{TranslationBlock,TranslationHistory,TranslationJob}.php`, `app/Services/{Admin/ReviewService,BlockService,HistoryService,StorageService}.php`, `app/Services/Translation/DTO/{TranslationRequest,TranslationResponse}.php`, `bootstrap/app.php` |
| Laravel config/infra | `config/queue.php`, `config/translation.php`, `composer.json`, `package.json`, `package-lock.json`, `vite.config.js`, `start-all.bat`, `start-demo.ps1`, `stop-demo.ps1` |
| Migrations/seeders | `database/migrations/2026_09_06_000003_seed_default_admin_user.php`, `database/seeders/DatabaseSeeder.php` |
| Laravel views/css/js | `resources/css/views/{admin,dashboard-common,translation}.css`, `resources/js/review-document.js`, `resources/views/{admin/dashboard,admin/jobs,admin/queue,admin/review-document,admin/review-text,bookmarks,dashboard,history,history-detail,profile,translation}.blade.php`, `resources/views/components/quality-badge.blade.php`, `routes/web.php` |
| Laravel tests | `tests/Feature/Admin/{AdminWriteHttpTest,DocumentReviewWriteActionsTest,ReviewBlocksPersistenceTest,ReviewRoutesTest}.php`, `tests/Feature/{AuthCssRenderingTest,TranslationControllerTest}.php`, `tests/Unit/TranslateDocumentJobTest.php` |
| Python service | `Model/server.py`, `Model/config/environment.py`, `Model/document/{chunker,document_analyzer,reconstructor,regenerator}.py`, `Model/document_translator_v3.py`, `Model/dto/responses.py`, `Model/pipeline/{coherence_polish,document_context,document_pipeline,translation_pipeline}.py`, `Model/prompts/translation.py`, `Model/providers/{base,future_deepseek,future_gemini,future_openai,gptoss,mistral}.py`, `Model/ai/{base,fallback_provider,mistral_provider,ollama_provider}.py`, `Model/validators/ai_quality_reviewer.py` |
| Python tests | `Model/tests/{mock_providers,test_analysis_resilience,test_cache_namespace,test_docx_inplace_parallel,test_properties,test_regression}.py` |
| Docs / assets | `SETUP.md`, `TRILINGUA_COMPLETE_GUIDE.md`, `DEMO.md`, `docs/ARCHITECTURAL_DESIGN.md`, `trilingua-code/.env.example`, `translated_in.docx`, `translated_input.pdf`, `Model/translated_input.docx` |

## 2. Runtime environment

| Item | Value |
| --- | --- |
| PHP | 8.2.31 (NTS, x64) |
| Required extensions present | `pdo_pgsql`, `pdo_sqlite`, `pgsql`, `mbstring`, `gd`, `zip`, `curl` |
| Framework | Laravel 12, PHP `^8.2` |
| Production DB driver available | **pdo_pgsql present** — PostgreSQL is reachable from this host |
| Test DB | `phpunit.xml` pins `sqlite` / `:memory:` (unchanged) |

### Effective runtime settings (read, not modified)

| Setting | Source | Effective |
| --- | --- | --- |
| Queue driver | `config/queue.php:16` | `database` |
| Queue connection | `config/queue.php:40` | `pgsql` (default) |
| `after_commit` | `config/queue.php:47` | `false` — required for queue-insert-inside-transaction atomicity |
| `retry_after` | `config/timeouts.php:36` | 1800 |
| Formats advertised | `config/translation.php:70` | 9: `docx pdf txt md rtf odt csv pptx xlsx` |
| Languages | `config/translation.php:45` | English, Cebuano, Filipino → **6 directed pairs** |
| Upload limit advertised | `config/translation.php:58` | 51200 KB (50 MB) — retained per pilot decision |
| Daily quota | `config/translation.php:32-33` | 25 files / 262,144,000 bytes |
| Active provider | `Model/server.py:87` | `gptoss` (GPT-OSS via Ollama), fallback `gemini` |
| Storage backends | `app/Services/StorageService.php:12-13` | `supabase` (primary), `local` (fallback) |

## 3. Baseline check results

| Check | Command | Result |
| --- | --- | --- |
| Test-env guard | `php tests/assert-safe-test-env.php` | **PASS** — `APP_ENV=testing`, `DB_CONNECTION=sqlite`, `DB_DATABASE=:memory:`, no cached config |
| PHP suite | `php artisan test --compact` | **407 passed**, 1644 assertions, 50.50 s, 0 failed |
| Timeout ladder | `php artisan deployment:validate-timeouts` | **PASS** — ladder safe; queue atomicity holds (`driver=database`, `connection=pgsql`, `after_commit=false`) |
| Python suite | `pytest tests -q --ignore=… --ignore=… -m "not slow and not golden and not font_regression" -p no:cacheprovider` | **2 failed, 350 passed, 35 deselected**, 82.40 s |

### Pre-existing Python failures (not caused by this plan)

Both are `hypothesis.errors.DeadlineExceeded`, i.e. the default 200 ms per-example deadline,
on this machine — **not logic failures**:

| Test | Reported time | Falsifying example |
| --- | --- | --- |
| `tests/test_properties.py::test_context_hint_truncation_triggered_for_long_hints` | 279.42 ms | long context hint |
| `tests/test_properties.py::test_table_structural_preservation` | > 200 ms | 9×10 table (90 cells) |

There is no `conftest.py` and no registered Hypothesis profile in `Model/`, so the 200 ms
library default applies. These are machine-speed-dependent harness failures. They are recorded
here so the Gate 7 full-suite run is compared against a known baseline rather than being read
as a regression. No product code is implicated and no test assertion was weakened to hide them.

## 4. Staging isolation and backup/restore

**Status: BLOCKED on isolated PostgreSQL and test storage access.** A new Supabase production project is not required.

A dedicated staging PostgreSQL database and a dedicated staging Supabase bucket are required
before Gates 4–6 live testing. Neither can be provisioned from this host without
credentials/accounts that are not present. `pdo_pgsql` is installed, so the moment an isolated
PostgreSQL connection string exists the matrix can run. A local database and a separate test
bucket can be used while retaining the existing Supabase production project.

**No production data is touched by this plan.** The first action that would modify any existing
data is gated behind a verified `pg_dump` → restore → `migrate` dry run. All database work
in Gates 1–4 is against SQLite `:memory:`
or a future isolated staging database.

## 5. Defects confirmed during inventory

1. **Ollama Cloud authentication is absent from the primary provider.**
   `Model/providers/gptoss.py` sends only `{"Content-Type": "application/json"}` at all three
   request sites (`:151`, `:545`, `:719`) and in the health check (`:740-741`). The default URL
   is `http://localhost:11434/api/chat` (`:72`) — a local Ollama, despite the class docstring
   claiming "Ollama Cloud" (`:3-5`). The chosen pilot primary provider therefore cannot
   authenticate. Minimal support is required before direct cloud deployment.
2. **Stale engine claim.** `resources/views/layouts/guest.blade.php:55` advertises
   *"Powered by NLLB-200 AI"* while the active provider is `gptoss` with a `gemini` fallback.
3. **Tunnel worker timeout violates the ladder.** `deploy-named-tunnel.ps1:144` runs
   `queue:work --timeout=900` against `config/timeouts.php:13-14`
   (`job 1300 < worker 1500`). The script also never runs `deployment:validate-timeouts`.
4. **Containment runbook error.** `security/containment-runbook.md:22` invokes
   `undeploy-named-tunnel.ps1` without `-Hostname`, which is Mandatory
   (`undeploy-named-tunnel.ps1:14-17`); the documented undeploy step would fail. Its process
   match (`:56`) covers `queue:work` only and would leave `queue:listen` workers running.

## 6. Gate 0 verdict

Baseline established and reproducible. Working tree preserved. Independent code work for
 Gates 1–3 may proceed; Gates 4–6 live testing and Gate 7 deployment are blocked on
 isolated PostgreSQL, test storage, and provider access.

### 6a. Addendum — live Supabase schema drift (read-only inspection, 2026-09-29)

With the owner's explicit permission, the configured Supabase database
(`trilingua-code/.env`, `DB_CONNECTION=pgsql`, Supabase pooler, `db=postgres`) was inspected
**read-only**. Only `SELECT` statements against `pg_catalog`/`information_schema` and row
counts were issued. Nothing was written, no migration was run, no secret was printed.

**Server:** PostgreSQL 17.6. **Data present:** `translation_history` 12 rows, `translation_jobs`
32 rows, `failed_jobs` 24 rows, `jobs` 0 rows.

**The hosted database is 7 migrations behind this branch.**

| | Repository | Hosted database |
| --- | --- | --- |
| Applied migrations | 33 files | **26 rows** |
| Not applied | — | the seven `2026_09_28_*` migrations |

Absent on the hosted database: the tables **`translation_quota`** and
**`storage_cleanup_outbox`**, and the columns
`translation_jobs.recovery_token`, `translation_jobs.translated_storage_path`,
`translation_jobs.translated_storage_backend`, `translation_history.published_text`,
`translation_history.priority` and `translation_blocks.published_text`.
(`translation_history.session_id` is correctly absent — the migration that replaced it with
`user_id` is applied.)

The seven pending migrations are **additive** (new nullable columns and two new tables; no
drops), but three of them write data during `up()`: `draft_revision = 1` for existing
`review_status = 'edited'` rows, the same-day quota ledger backfill, and the evidence-based
`published_text` block backfill. Running them is therefore a real change to production data,
not a schema-only operation.

**Consequence.** The current working tree cannot run against the hosted schema: intake fails
on the missing `translation_quota` table, the job state machine reads `recovery_token` and the
translated paths, the Gate 1 cleanup path writes to the missing `storage_cleanup_outbox`
table, and the admin publish path reads the missing `published_text` columns. Every
working-tree test passes only because PHPUnit runs on `sqlite :memory:` and builds the schema
from the migration files.

This is recorded, and not repaired, because the plan forbids a production migration before a
verified backup/restore and a migration dry run on a restored copy. It is the first item that
Gate 4 must resolve, and it is a release blocker independent of any code defect.

**Also noted:** `translation_history.created_at` is `timestamp with time zone` while
`translation_jobs.created_at` is `timestamp without time zone` (Laravel's `timestamps()` is
zoneless on PostgreSQL; the history table was created with `timestampsTz()` or altered).
Both are handled by Laravel, but date-window comparisons that span the two tables should be
reviewed during the Gate 4 matrix.

---

# Phase 08b — Gates 1–3: independent code work

Baseline PHP suite was **407 passed**. After Gates 1–3 the suite is **466 passed**
(1771 assertions), 0 failed. Nothing was staged, committed, stashed or reset.

## Gate 1 — storage references held by live jobs

**Defect.** `StorageCleanupService::hasLiveReference()` only consulted `translation_history`.
A `translation_jobs` row that had not yet produced a history row — or whose history row had
been deleted — did not protect its `original_storage_path` or `translated_storage_path`.
Reclaiming such an object destroyed the file a retry still needed.

**Fix.** `hasLiveReference()` now also asks `hasLiveJobReference()`, which treats a job as
live when it is `created|queued|processing`, or `failed` with `recoverable = true`. Both the
original and the translated path are checked, matched against the row's stored backend so a
local path cannot protect a Supabase object. The job's own release path
(`TranslateDocumentJob::releaseUnreferencedObject()`) now calls the shared predicate with its
own ID excluded, so a refused attempt can still release the object it just uploaded while a
*sibling* job's reference still blocks it.

The cleanup service is resolved from the container inside that rare path rather than injected
into `handle()`: adding a sixth parameter would have churned 14 direct call sites across six
pre-existing test files for no behavioural gain.

**Tests.** `tests/Feature/StorageCleanupJobReferenceTest.php`, 16 cases over a
created/queued/processing/failed-recoverable matrix, plus terminal jobs, unrecoverable
failures, backend mismatch, genuine orphans, self-exclusion, sibling references, history
deletion and the scheduled pass.

## Gate 2 — one service token, fail closed in production

**Defect.** Laravel read `PYTHON_SERVICE_TOKEN` and sent it as `X-Service-Token`
(`config/translation.php:19`, `TranslationManager.php:49-54`). The engine read
`MODEL_SERVICE_TOKEN` instead (`server.py:339-340`), so the two sides never agreed, and
`Model/config/environment.py` did not allow the `PYTHON_` prefix, so the engine could not
even load the variable from the shared `.env`. The dependency was also opt-in: an unset token
meant no authentication at all.

**Fix.** `PYTHON_SERVICE_TOKEN` is now the single canonical name on both sides.
`MODEL_SERVICE_TOKEN` survives only as a documented local fallback. The loader accepts the
exact `PYTHON_SERVICE_TOKEN` and `APP_ENV` keys and still refuses to override a real process environment
variable, so a platform-injected token outranks any stale file. When `APP_ENV=production` the
engine refuses to start without a non-empty token (`_enforce_startup_token_policy()`, wired
into the FastAPI lifespan), and the dependency returns 503 rather than falling open if
configuration is ever lost at runtime. Local, testing and unset environments keep their
existing opt-in behaviour.

**Tests.** `Model/tests/test_service_token_policy.py` (17 cases: loader precedence, canonical
vs legacy name, 401 for absent and wrong tokens, acceptance of the matching token,
fail-closed startup, a 503 defence-in-depth path, and an assertion that all four mutating
endpoints are actually wired to the dependency while `/health` stays open and ungated) and
`tests/Feature/PythonServiceTokenTest.php` (5 cases on the Laravel side).

## Gate 3a — statistics no longer stop at 200 rows

**Defect.** The dashboard, the profile page and the admin user page all derived their
statistics from a 200-row slice. Past 200 translations every lifetime total, word count,
language mix, quality average and period delta silently froze while still looking
plausible. On the admin page the "Total Translations" count (computed separately) kept
climbing beside the document and word totals that did not.

**Fix.** `TranslationStatsService::forUser()` and `::profileSummary()` aggregate in the
database over every row. Word counting is the one figure that could not be moved into SQL
without changing its meaning — `str_word_count()` returns 0 for scripts without word
separators — so stored `document_word_count` values are summed by the database and only the
rows that genuinely need `str_word_count()` (text rows and legacy document rows with no
stored count) are streamed through in 500-row batches. A text row never borrows a
`document_word_count`, matching the old branch structure exactly.

**Tests.** `tests/Feature/StatsAggregateParityTest.php` (12 cases) reproduces the previous
`totals()` and `deltas()` logic as an oracle and asserts the aggregates match it exactly on a
complete row set, alongside the previous `compute()`, `dailySeries()`, `languagePairMix()`,
`averageQuality()` and `qualityByPair()`. It also asserts the dataset exceeds the old cap and
that the totals reflect every row.

The word path was initially under-specified: the first fixture never put more than 200 rows
through it, so a cap reintroduced there passed. The fixture now drives 205 text rows and 60
legacy document rows through it. A deliberate mutation (truncating the word scan) was
confirmed to fail 3 of the 12 cases, proving the tests are not vacuous.

## Gate 3b — documents paginated, dead query removed, history links added

**Defect.** My Documents read the newest 200 rows and rendered them with no navigation, so a
user's older translations were unreachable with no indication that anything was missing. The
page also ran `getOriginalsWithTranslations()` — an eager-loading query with a per-row
`translation_count` subquery — and then discarded the result, because the view overwrote
`$originals` from its own data. History paginated at the service layer but the view rendered
no links, so only the first page was reachable.

**Fix.** `HistoryService::getDocumentsPaginated()` and `getDocumentLanguagePairs()` replace the
capped read; the discarded originals query is no longer called; both views render
`->onEachSide(1)->links()`. The My Documents header count now reports the true total via
`total()` instead of the number of rows on screen. The language-pair dropdown is now built by
the database, so pairs that only exist beyond the first page remain filterable.

**Tests.** `tests/Feature/DocumentsPaginationTest.php` (8 cases) covers first-page bounds,
reachability of the oldest document, the true-total count, conditional pagination markup,
document/text separation, pairs beyond page one, and the history page links.

Six pre-existing test files mocked the removed service methods and the old array shape; each
was updated to mock the paginated call while keeping its original assertion intact. No
assertion was weakened.

## Gate 3c — availability comes from the backend, not from exception text

**Defect.** Both redownload routes decided whether a file was permanently gone by searching the
thrown exception's message for the substring `not found`
(`HistoryController.php:325` and `:402`). Exception text is not an API, and the substring
matched both directions of error:

- A DNS, TLS or gateway outage whose message happened to contain "not found" (for example
  "Host not found") was answered with a permanent **404** and "This file is no longer
  available", telling the user to give up on a file that still existed.
- A genuine deletion reported as `NoSuchKey`, or hidden behind a 403 on the private bucket,
  was answered with a **500** and "Please try again later", so the user retried a deleted
  object indefinitely and was never offered the re-upload they needed.

`StorageService::generateSignedUrl()` still builds a human-readable "file not found in
storage" string, but it now only ever reaches a log line: no code branches on it.

**Second defect.** `DocumentsController::retranslate()` checked only that
`original_storage_path` was non-empty. A stored path is a string in the database, not
evidence that the object is still there, so a deleted original surfaced as an opaque **500**
out of `StorageService::read()` — the one status that can never succeed on retry — instead of
the re-upload instruction the controller already knew how to give for a blank path.

**Fix.** Both routes now ask the backend through `StorageService::exists()`, which returns
`present` only on proof, `missing` only on an authoritative 404, and `unknown` when an outage
prevents a verdict:

- `missing` → 404 (translated) or 422 with the re-upload message (re-translation).
- `unknown` → the signing attempt still proceeds, because the probe is not the operation; if
  it then fails the user gets a retryable error. For re-translation, `unknown` short-circuits
  with **503** and no re-upload advice, because an outage must never be reported as loss.
- A probe that itself throws is treated as `unknown`, not as evidence.

Ownership is still checked first, so the probe is never reachable for another user's record.

**Tests.** `tests/Feature/DownloadAvailabilityTest.php` (12 cases, both routes × six
scenarios) and `tests/Feature/RetranslateAvailabilityTest.php` (6 cases). The two decisive
cases are the swapped-error ones: an outage whose message says "not found" must not yield 404,
and a deletion whose message does not say "not found" must still yield 404.

Mutating the fix to compare against `PRESENCE_UNKNOWN` instead of `PRESENCE_MISSING` fails
**10 of the 12** cases, confirming they are not vacuous.

Eight pre-existing `StorageService` mocks across five test files only stubbed
`generateSignedUrl`/`read`. Each gained an `exists()` → `present` expectation; their original
assertions (ownership, expiry, quota accounting, race refunds) are unchanged.
