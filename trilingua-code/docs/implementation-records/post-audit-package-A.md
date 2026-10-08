# Post-audit Package A — authoritative job acceptance

This package was implemented before the B–G continuation. The original
failure was ambiguity after document dispatch: a failed queue call could mean
the work was definitely absent, or that the enqueue succeeded but its result
could not be read. Treating both as rejected could refund quota and delete an
input that a worker would still process; treating both as accepted could leave
an unreceivable job. `DispatchOutcome` and `DispatchOutcomeClassifier` express
accepted, rejected and unknown from authoritative row/queue/failed-job
read-back. Intake, admin Retry, worker compensation and reconciliation share
that boundary. An unknown outcome retains quota/input and returns a stable job
reference; a proven rejection can compensate the attempt. Admin Retry removes
the failed-job recovery handle only within the committed acceptance boundary.

The deployment validator checks the effective timeout ladder and the database
queue prerequisites: same DB connection as `translation_jobs` and
`after_commit=false`. `DispatchOutcomeClassificationTest` has 13 branch and
rollback tests (34 assertions in the earlier focused run). The current full
Laravel suite passed 407 tests/1,644 assertions, and the isolated testing
configuration passed `deployment:validate-timeouts`. A two-worker PostgreSQL
run with real queue read-back ambiguity and process interruption remains a
release gate. No existing production database was migrated during this
continuation. Rollback must keep the state/queue transaction and compensation
logic together; changing only one side can reintroduce data loss or duplicate
work.

