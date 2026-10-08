# Production preparation evidence - 2026-10-08

Prepared the current `C:\dev\Trilingua` source for Laravel Cloud in an isolated checkout. Included the newer local F15/F16 provider safety and accounting fixes. Preserved the original working folder: SHA-256 checks matched all 522 source files captured before the work. Generated translations, runtime caches, credentials and unrelated experiments were excluded from the release snapshot.

| Check | Result |
| --- | --- |
| Laravel suite, isolated SQLite in memory | 501 passed, 1,870 assertions |
| Deterministic Python suite, fresh virtual environment | 412 passed, 35 deselected |
| Frontend production build | Passed after dependency updates |
| Production configuration and `artisan optimize`, synthetic settings | Passed before and after configuration caching; no live service calls |
| Timeout ladder and database dispatch settings | Passed |
| Cloud forwarded HTTPS/client-address regression | Passed |
| Composer audit | No advisories |
| Python audit and dependency consistency | No known vulnerabilities; no broken requirements |
| npm audit | No high/critical findings; one moderate advisory affects three packages in Mammoth's CLI chain |
| Secret-pattern scan of new unpublished text blobs | 408 scanned, no matches before the final production changes; final tree scanned again before push |
| PPTX dependency update smoke | Title and chart axes rendered as in the original build; full chart/layout fidelity is not established |

Python live-provider/load modules and slow/golden/font tests were excluded deliberately. PHPUnit reports existing metadata deprecations; Starlette reports an HTTPX test-client deprecation. Structural property assertions remain intact; only hardware-sensitive timing checks were adjusted for document I/O and intentionally large generated inputs. Deployment code passed Pint; legacy code was not reformatted.

The JavaScript updates fix the chart-library XSS dependency, UUID advisory, shell-quoting injection, and source-map advisory. A concrete shell-quoting exploit is now rejected. PHP's CommonMark parser and Python's Pillow were upgraded to patched versions. Mammoth's remaining moderate advisory has no compatible upstream fix; the application uses its separate browser build. See the [deployment guide](LARAVEL_CLOUD_DEPLOYMENT.md) for that limit.

GitHub's Linux runner exposed premature input deletion after dispatch errors. Cleanup now runs only for confirmed rejection on upload and re-translation. Regression tests verify actual file bytes across runtime/database failures and accepted/unresolved/rejected outcomes; an empty directory no longer counts as preserved input.

No production database migration, provider translation, Cloud deployment, live Supabase storage operation or human quality review was performed. Before serving users, configure both Cloud applications, back up the existing database, and complete the deployed acceptance checks in the [Laravel Cloud guide](LARAVEL_CLOUD_DEPLOYMENT.md). Starter is $5 plus metered usage; the current database queue needs awake compute.
