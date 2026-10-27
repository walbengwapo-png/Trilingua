# Post-audit Package G — integrated acceptance record

## Local automated gate

Environment: Windows, PHP 8.2.31, isolated Laravel test SQLite `:memory:`.
The safe-environment guard reported `APP_ENV=testing`, SQLite memory DB, and
no cached config. No configured production database was migrated or repaired.

| Check | Result |
| --- | --- |
| `php tests/assert-safe-test-env.php` | Pass |
| `php artisan test` | 407 passed, 1,644 assertions, no skips |
| `php artisan deployment:validate-timeouts` with isolated testing env/database queue | Pass; 1200 < 1300 < 1500 < 1800 < 2100 seconds, same DB connection, `after_commit=false` |
| `npm run build` | Pass, with preview-library chunk-size warnings |
| `php artisan view:cache` | Pass |
| Python deterministic command below | 352 passed, 35 deselected in 58.41s |

The earlier CSS test skip was stale: `AuthCssRenderingTest` asserted a manifest
entry for `resources/css/guest.css`, while the actual build uses
`resources/css/layouts/guest.css` and `resources/css/views/welcome.css`. The
test now checks the real asset entries and passed with the compiled manifest.
The Python run initially hit a Hypothesis `FlakyFailure`: the first DOCX
font-color property example took 1.48 seconds against a 200ms timing deadline,
then passed in 53ms. Similar timing-only failures occurred for paragraph and
table properties. The five DOCX file-round-trip properties verify output
correctness, not speed; their Hypothesis deadlines were removed without
reducing their 100 examples or assertions. The complete deterministic suite
then passed.

Python command:

```text
python -m pytest Model/tests -m "not slow and not golden and not font_regression" --ignore=Model/tests/test_concurrency_benchmark.py --ignore=Model/tests/test_reference_gemini_workflow.py -q
```

## Browser and operational evidence

An isolated browser server used a fresh disposable SQLite DB and test user.
Member sign-in, dashboard, translation page, CSS delivery, and 390px no-overflow
were observed. The first browser attempt used array sessions and returned 419;
file sessions corrected that test setup. This browser pass did not execute a
real translation, admin workflow, keyboard scan, screen reader, or network
interruption scenario.

PostgreSQL, Docker, a live Supabase storage backend, and Office/LibreOffice
renderers were unavailable locally. No two-worker queue race, real storage
signer/read/delete, process-crash recovery, real-provider translation, target
application openability, human meaning/layout review, or representative
large-document load/memory/concurrency measurements were run. Existing
untracked benchmark output was deliberately left untouched.

## Release decision and required next gates

**Release blocked / production readiness unverified.** To close it, run the
isolated PostgreSQL database-queue two-worker matrix from the handoff; validate
actual Supabase and local storage paths; walk guest/member/admin and mobile,
keyboard, screen-reader, network-dropout flows; open representative outputs in
target applications; measure large documents and concurrent uploads; and
human-score meaning/layout against thresholds agreed before judging. Do not
call automated green status proof of these conditions. Operational rollback
must preserve the Package B published-text schema and Package C cleanup
outbox until queued work and stored object references are reconciled.
