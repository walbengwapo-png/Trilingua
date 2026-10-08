# Post-audit Package D — client and text-state truthfulness

## Problem and affected paths

The synchronous text branch in `TranslationController::translate()` returned a
normal translation response even when `HistoryService::insertRecord()` failed.
The translation page then showed the result without saying that it would be
absent from Saved Translations and the admin review queue. A later notification
or metrics exception could also be confused with a history failure. The
document poller used a fixed two-second interval, did not explain network
dropouts, and previously inferred failure from elapsed time. Package C also
introduced a truthful completed-without-download state that the client had to
recognize.

## Implementation

- `app/Http/Controllers/TranslationController.php`: history insertion decides
  `saved`; notification and metrics errors are isolated after the row exists.
  A valid text result returns `saved:false` if history insertion failed and
  `saved:true` if it succeeded, even if later metrics fail.
- `resources/views/translation.blade.php` and
  `resources/css/views/translation.css`: a persistent, accessible warning near
  the output explains an unsaved translation and asks the user to copy or save
  it. The warning survives a failed subsequent submit. The document poller
  keeps its job ID in session storage, rejects stale responses by generation,
  never overlaps requests, backs off from 2 to 15 seconds, pauses when hidden,
  and resumes on refocus/revisit. A transient status/network error leaves the
  reference intact. Only a server terminal failure or real not-found clears it.
  A completed response without a verified download stays in the retry loop and
  never creates a broken link. Legacy `created`/`queued` states remain active.
  The long-wait link labels its actual `/documents` destination “My Documents.”
- No schema migration or existing data rewrite.

## Checks

- `php artisan test tests/Feature/TextTranslationPersistenceIntegrityTest.php`:
  2 passed, 12 assertions. This injects a history exception and a separate
  metrics exception to prove the `saved` boundary.
- Inline JavaScript parsed with Node `vm.Script` after substituting the Blade
  JSON expression; `npm run build` and
  `php artisan view:cache` passed in the integrated run.
- Isolated browser run used a fresh SQLite database, file sessions, and a test
  account. Login reached the member dashboard and the translation page. Built
  CSS loaded; at 390px the translation input and action stayed within the
  document width. The warning is hidden before a result and its copy is present.

## Limits and rollback

No live translation service was connected to the browser run, so actual
`saved:false`, network interruption, and completed-without-download transitions
have automated/static coverage but no end-to-end browser proof. Reverting the
client alone would hide backend partial-success truth; rollback D as a unit.
