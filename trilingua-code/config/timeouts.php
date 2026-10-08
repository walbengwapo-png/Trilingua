<?php

/*
|--------------------------------------------------------------------------
| Timeout ladder (single source of truth)
|--------------------------------------------------------------------------
|
| Every layer that limits how long a document translation may run must obey
| one strict ordering so a legitimately slow (but alive) job is never
| re-leased to a second worker, reconciled as dead, or pushed out of its own
| worker's window. Each value must strictly exceed the previous with margin:
|
|   python_service (1200)  <  job (1300)  <  worker (1500)  <
|     retry_after (1800)  <  reconcile/check-stale (2100)
|
|   - python_service : Total engine budget; Cloud document polls each use <=45s.
|   - job            : Illuminate job `$timeout` (CPU timeout for one attempt).
|   - worker         : queue:listen/queue:work `--timeout` (kill window).
|   - retry_after    : database queue lease; must exceed the worker timeout so a
|                      busy worker finishes BEFORE its job look available again.
|   - reconcile      : translations:reconcile --processing-timeout AND the
|                      advisory queue:check-stale --threshold. Must exceed
|                      retry_after so the reconciler only fails jobs whose lease
|                      would already have lapsed, never a healthy long call.
|   - waiting        : how long a created/queued job may wait before the
|                      reconciler flags it as never-started.
|
| deployment:validate-timeouts enforces these inequalities against the
| effective (post-.env) values at every startup.
*/

return [
    'python_service' => (int) env('PYTHON_SERVICE_TIMEOUT', 1200),
    'job' => (int) env('TRANSLATION_JOB_TIMEOUT', 1300),
    'worker' => (int) env('QUEUE_WORKER_TIMEOUT', 1500),
    'retry_after' => (int) env('DB_QUEUE_RETRY_AFTER', 1800),
    'reconcile_processing' => (int) env('RECONCILE_PROCESSING_TIMEOUT', 2100),
    'reconcile_waiting' => (int) env('RECONCILE_WAITING_TIMEOUT', 7200),
    'check_stale' => (int) env('QUEUE_CHECK_STALE_THRESHOLD', 2100),
];
