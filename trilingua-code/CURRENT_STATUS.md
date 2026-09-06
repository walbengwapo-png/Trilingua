# TriLingua — Current Status

**Updated:** 6 September 2026

**Canonical working copy:** `C:\Users\walbe\OneDrive\Documents\GitHub\Trilingua\trilingua-code`

**Branch:** `codex/trilingua-publish-safe-20260906`
**Baseline commit:** `5172c2f` — *Publish-safe TriLingua migration*

**Current implementation:** the latest local commit, *feat: improve translation quality and review workflow*

## Working-copy and migration status

- The GitHub-bound OneDrive checkout is the active implementation copy. The older `C:\dev\Trilingua` worktree is retained as a recovery copy and has not been overwritten.
- The migration baseline and the completed UX/review/translation-quality pass are committed locally on the branch above.
- Applied locally:
  - `2026_09_06_000003_add_preferences_to_users_table`
  - `2026_09_06_000004_create_document_versions_table`
- No changes have been pushed to GitHub.
- The Laravel web server, queue worker, and Python translation-pipeline server are currently stopped, as requested.

## Implemented in the current pass

### Clearer translation and review state

- A shared presentation layer now distinguishes **Original**, **Translation output**, **Reviewed final**, and text translations.
- Status is presented as a composite lifecycle state, for example: **Translation complete · Review pending**.
- Quality scores now include an understandable risk label: **Low risk**, **Needs review**, or **High risk**.
- Review lists can filter documents by detected issue type.

### Safer, more useful workflow

- Text and document reviews support verification notes and require a reason when flagging a translation.
- Review actions return durable audit feedback instead of silently treating an action as complete.
- Document versions are immutable snapshots; the current version is tracked and historical versions can be selected for preview/download.
- Review screens provide side-by-side source/output context, per-block comments, keyboard shortcuts, and action summaries.

### Personal settings and polished UI states

- User preferences now persist source language, target language, translation mode, timezone, date format, notification choices, and reduced-motion preference.
- `balanced` is the default translation mode, with `fast` and `thorough` available.
- Dates respect the user’s saved timezone and use relative text with an exact timestamp available on hover.
- The admin/member label comes from the account’s actual role.
- Shared empty, loading/error, success, retry, and focus-visible states are available across the interface.
- Notification and translation requests now handle non-JSON and retryable failures safely, without injecting server text as HTML.

### Translation pipeline completion work

- Text translations now carry the selected **fast**, **balanced**, or **thorough** mode through Laravel into the Python service, instead of dropping it at the API boundary.
- Balanced and thorough text translations run a quality check after deterministic safeguards; only flagged output is retranslated with the reviewer’s issue summary.
- Translation prompts now explicitly preserve protected tokens and line breaks, and include natural Cebuano/Filipino guidance for grammar, verb/aspect, formality, and pronouns.
- The selected provider now fails over to the configured secondary provider only after its own retries are exhausted; GPT-OSS defaults to Mistral as its fallback and vice versa.
- The translation screen now accepts every document format supported by the backend, including PowerPoint and Excel, and its 50 MB size check matches the server limit.
- Manila timestamps display the unambiguous **PHT** abbreviation rather than the misleading PHP time-zone label **PST**.

## Files currently changed

The pending change set spans Laravel controllers, models, services, Blade templates, CSS, reusable support classes, and two migrations. New primary implementation files include:

- `app/Models/DocumentVersion.php`
- `app/Support/ApiError.php`
- `app/Support/TranslationPresentation.php`
- `app/Support/UserPreferences.php`
- `database/migrations/2026_09_06_000003_add_preferences_to_users_table.php`
- `database/migrations/2026_09_06_000004_create_document_versions_table.php`
- `resources/views/components/async-state.blade.php`
- `resources/views/components/feedback.blade.php`

## Verification completed

- Database migration status: all migrations, including the two new ones, are applied locally.
- Laravel focused coverage: **82 tests passed, 302 assertions**, covering settings, translation preferences, review writes, review routes, presentation states, and dashboard data-provider metadata.
- Python focused coverage: **19 tests passed**, covering fallback behavior, prompt/coherence behavior, cache namespaces, cache language separation, echo handling, and paragraph preservation.
- PHP and Python syntax checks passed; Blade view caching and the production front-end build completed successfully.

## Remaining work before commit

1. Add deeper end-to-end coverage for document-version selection and the live Python text-mode quality-repair path when test doubles for the external providers are available.
2. Push the verified commit only after explicit user authorization.

## Known verification caveat

The repository’s broad Laravel suite had pre-existing failures caused by migration/branch contract drift. Those failures must be separated from any newly introduced regression during final validation; they are not currently treated as evidence that this UX work is complete.
