# Post-audit Package E — quality availability and spacing evidence

## E-A: quality signal

**Problem.** `AIQualityReviewer` treated an AI provider exception as score
`100`, which falsely looked like a strong quality result. Batch fallback could
issue one AI call per block after a provider outage. A missing or nonfinite
provider score could also appear valid.

**Implementation.** `QualityReview.score` is nullable and `available` records
whether a review score exists (including a decisive deterministic pre-check).
Exception, non-dict, missing-score and
nonfinite-score paths return an unavailable review, preserve deterministic
issues, and do not create a high score. Batch outage uses deterministic checks
without a per-block provider request storm. Critical deterministic issues
still trigger retry. `DocumentContext`, translation retry formatting, and
`Model/server.py` propagate nullable scores; the text API includes
`quality_review_available` and an availability warning. PHP's existing
nullable score DTO and database columns retain null. User and admin score
displays now say “Unavailable” for null and use neutral styling; zero remains a
real score. All numeric color categories are neutral triage signals because
they are automated and uncalibrated, not human-verified accuracy.

**Checks.** Focused Python analysis tests covered batch and single provider
failure and malformed scores. The deterministic suite is recorded in the
release report. Laravel's full suite and Blade compilation cover the changed
views. No schema migration or data repair is needed. Historical non-null 100
scores cannot be reclassified without original provider evidence; do not
silently rewrite them.

## E-B: spacing contract

Both `ChunkSplitter` and `Chunk_Splitter` normalize `0  0` to `0 0` and
collapse repeated interior spaces in a multi-chunk sentence sample. This
matches the documented normalized-spacing contract and the current regression
tests. It does **not** prove that normalization preserves layout in a
representative rendered DOCX. No LibreOffice/Office renderer was available in
this environment, so the earlier per-chunk-preservation intent versus current
normalization remains a product/evidence decision. No spacing semantics were
changed here.

## Rollback and remaining gate

The availability change is response-compatible for nullable score consumers,
but an older Python consumer that unconditionally formats a score would need a
guard. Revert the Python review/serialization and score UI together if needed.
Before release, render and compare a layout-sensitive file and have a human
judge whether normalized spaces alter meaning or layout. Choose a different
spacing contract only from that evidence.
