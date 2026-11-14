# Targeted document repair deployment

Base: production b6d28fee. Branch: codex/document-hotfix-2026-11-14.
Keep one global translation slot and preserve all application data and existing
provider credentials. This repair does not restore the reverted full release.

Changes: checked Unicode fallback fonts, stable render-plan secret support,
preflight signing validation before provider work, bounded status/result GET
retries, explicit reconciliation without a new translation, and concise user
errors with full operator logs. Strict saved-PDF validation remains enabled.

Deployment:

1. Publish this branch and pass document-hotfix.yml. Confirm production's
   PyMuPDF version; this patch changes no runtime dependency versions.
2. Inspect signing configuration without printing secrets. Reuse any valid
   existing render-plan key. If genuinely absent, generate one production
   render-plan key outside the repository using tools.ocr_trust keygen.
   Store its stable JSON as the protected OCR_PLAN_KEY_JSON deployment secret,
   or securely mount the key and set an absolute OCR_PLAN_KEY_FILE. Never
   generate a new key on every startup. Keep acceptance keys separate.
3. Drain active work, then deploy this branch to Laravel and Python. Keep
   database migrations and current compute/concurrency settings unchanged.
4. Verify both service health endpoints and authenticated pages. Run one
   bounded real-provider FOMO PDF canary through the normal interface. Check
   symbols visually and by extraction, history, original/result downloads and
   saved-plan regeneration after restart. Report any held source regions.
5. Do not bulk-replay failed jobs. The operator command
   php artisan translations:resume-result JOB_ID only consumes an already
   completed retained result from jobs with the new uncertainty state.

Current access blocker (2026-11-14): GitHub connector writes return HTTP 403
Resource not accessible by integration; Git Credential Manager has no usable
stored GitHub credential in this session. Browser-control tools are unavailable
and no Laravel Cloud CLI token/configuration is present. No production
configuration, deployment, translation job or document was changed in this
Windows continuation. The earlier Linux commit/bundle lives in the unavailable
Linux workspace; these equivalent changes were completed in the restored
Windows hotfix worktree. A new local commit identifies this Windows copy.

Verified in the restored Windows session: 141 focused Python tests passed
with PyMuPDF 1.28.2; 14 PHP tests passed with 53 assertions under PHP 8.2.31.
PHP tests used an explicit testing/SQLite-memory environment, the existing
vendor runtime and test-local provider/package manifests. The PHP filesystem
readability check prevented the default bootstrap path, so a temporary native
PHP runner loaded the same test environment and bootstrap explicitly. The
isolation guard remained enabled. No production database tests were run.
The retained FOMO native reconstruction passes all 66 fragments across three
pages with zero content findings; source block 10 remains held as before.
This is offline reconstruction, not a new provider translation or deployed
end-to-end verification.
