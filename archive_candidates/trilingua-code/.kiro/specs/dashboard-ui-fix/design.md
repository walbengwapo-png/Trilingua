# Dashboard UI Fix — Bugfix Design

## Overview

Four authenticated pages in the TriLingua Laravel application render hardcoded/mock data and
incorrect layouts instead of real user data and the intended mockup designs. The fix involves:

1. **DashboardController** — a new controller that computes real stats (total documents,
   translations this month, words translated) from the authenticated session's
   `translation_history` rows via `HistoryService`, and passes the five most-recent records
   to the view.
2. **Dashboard blade** — welcome greeting with the real user name, three live stat cards,
   a Recent Translations table (up to 5 rows), and a Quick Actions panel.
3. **New Translation blade/JS** — 5 000-character limit with a live `0/5000` counter and
   speaker icon buttons on both panels.
4. **My Documents blade** — search bar, Language/Status filter dropdowns, grid/list toggle,
   tab filters (All / Recent / Shared / Archived) with real counts, and a progress bar on
   each card.
5. **Saved Translations (History) blade** — cards grouped by language pair, match-percentage
   badge, per-card action icons (copy / download / share / bookmark), and a page header with
   count badge, search, group-by, and sort controls.
6. **CSS** — all four view stylesheets updated to match the clean white/light-gray design
   with blue sidebar and card layouts.
7. **Data scoping** — all Supabase queries are scoped to `session_id = eq.{sessionId}` using
   the existing `HistoryService` pattern; no schema changes are required.

The fix is purely additive on the PHP/Blade/CSS side. All existing translation, download,
re-download, and modal flows are preserved unchanged.

---

## Glossary

- **Bug_Condition (C)**: Any page render where the view receives hardcoded/mock data instead
  of data derived from the authenticated user's `translation_history` records, or where a
  required UI element (counter, speaker icon, filter, progress bar, grouping, badge, action
  icon) is absent.
- **Property (P)**: The desired post-fix behavior — every page renders only real user data
  and every required UI element is present and functional.
- **Preservation**: All existing server-side translation, document upload, re-download,
  view-text-modal, swap, copy, save, and auth flows must continue to work exactly as before.
- **HistoryService**: `App\Services\HistoryService` — the existing Guzzle-based service that
  queries `translation_history` via the Supabase REST API.
- **DashboardController**: New `App\Http\Controllers\DashboardController` that replaces the
  current inline route closure (or stub) for `GET /dashboard`.
- **session_id**: Laravel's `session()->getId()` — the current scoping key used by all
  existing controllers to filter `translation_history` rows.
- **translation_type**: Column in `translation_history`; value is `'document'` (default) or
  `'text'`.
- **word_count**: Derived at render time by splitting `source_text` on whitespace; not stored
  in the DB.
- **match_percentage**: Derived at render time as a display-only value; computed from
  `translated_text` length vs `source_text` length for text records, or fixed at 100 % for
  completed document records.

---

## Bug Details

### Bug Condition

The bug manifests on every page load of Dashboard, New Translation, My Documents, and Saved
Translations. The controllers/views either pass hardcoded literals to the template or omit
required UI elements entirely.

**Formal Specification:**

```
FUNCTION isBugCondition(pageResponse)
  INPUT:  pageResponse — the rendered HTML of a protected page
  OUTPUT: boolean

  RETURN (
    pageContainsHardcodedStats(pageResponse)          -- "24", "12", "45,280"
    OR pageGreetingLacksRealName(pageResponse)
    OR recentTranslationsAreHardcoded(pageResponse)   -- "Mother Tongue-Based", "Comparative Study"
    OR quickActionsPanelMissing(pageResponse)
    OR charCounterShowsWrongLimit(pageResponse)        -- shows "8000" instead of "5000"
    OR speakerIconsMissing(pageResponse)
    OR searchAndFilterBarMissing(pageResponse)         -- My Documents
    OR tabFiltersWithCountsMissing(pageResponse)       -- My Documents
    OR progressBarMissingOnCards(pageResponse)         -- My Documents
    OR historyNotGroupedByLanguagePair(pageResponse)   -- Saved Translations
    OR matchBadgeMissing(pageResponse)                 -- Saved Translations
    OR perCardActionIconsMissing(pageResponse)         -- Saved Translations
    OR historyPageHeaderMissing(pageResponse)          -- Saved Translations
  )
END FUNCTION
```

### Examples

| Page | Buggy input | Current (defective) output | Expected output |
|---|---|---|---|
| Dashboard | Authenticated user with 3 document records | Stat card shows "24 Total Documents" | Stat card shows "3 Total Documents" |
| Dashboard | User with name "Maria Santos" | Greeting shows no name | "Welcome back, Maria Santos" |
| Dashboard | User with 0 records this month | "12 Translations This Month" | "0 Translations This Month" |
| New Translation | User opens page | Counter shows "0/8000" | Counter shows "0/5000" |
| New Translation | User opens page | No speaker icons visible | Speaker icon on source and target panels |
| My Documents | User with 5 documents | No search bar, no tabs, no progress bar | Search bar, tab filters with counts, progress bar on each card |
| Saved Translations | User with 4 text records | Flat table, no grouping, no badges | Cards grouped by language pair, match % badge, copy/download/share/bookmark icons |

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- `POST /translate` (text and document modes) must continue to send requests to the backend,
  return translated results, and enable Copy/Save buttons — no changes to `TranslationController`.
- Document file validation (type, size), upload to Supabase Storage, and signed-URL return
  must remain unchanged.
- The swap button must continue to swap language selects and clear the output panel.
- `POST /history/redownload/{id}` must continue to generate a new signed URL and redirect.
- The "View" modal on Saved Translations must continue to open with source/translated text.
- Unauthenticated users must continue to be redirected to the login page.
- Logout must continue to invalidate the session and redirect.
- The empty-state message on My Documents must continue to appear when there are no documents.
- The app layout (sidebar, header with user name, logout button) must remain unchanged.

**Scope:**
All inputs that do NOT involve the four affected page renders are completely unaffected.
This includes all POST endpoints, the Settings page, the auth pages, and all JS fetch calls
that are already working.

---

## Hypothesized Root Cause

1. **No DashboardController exists** — the `GET /dashboard` route likely renders the view
   directly or via a minimal closure without querying `HistoryService`. The blade template
   contains hardcoded literals instead of Blade variables.

2. **Character limit not updated in JS** — `MAX_CHARS` in `translation.blade.php` is set to
   `8000` and the `maxlength` attribute on the textarea is also `8000`. The design requires
   `5000`. The counter label therefore always shows `x/8000`.

3. **Speaker icon buttons never added** — the translation blade has no `<button>` elements
   with speaker/TTS icons in either panel header or footer.

4. **My Documents blade has no filter/tab/progress-bar markup** — `DocumentsController`
   already fetches real document records, but the blade template renders no search input,
   no tab filter row, and no `<div class="progress-bar">` inside each card.

5. **History blade renders a flat table** — `HistoryController` already fetches real records,
   but the blade groups nothing and renders a plain `<table>` with no match badge, no action
   icons, and no page header controls.

6. **CSS files lack the required component classes** — the new UI elements (tab filters,
   progress bars, match badges, action icon rows, Quick Actions panel, speaker buttons) have
   no corresponding CSS rules.

---

## Correctness Properties

Property 1: Bug Condition — Real Data Rendered on All Four Pages

_For any_ authenticated session where `isBugCondition` returns true (i.e., the page currently
renders hardcoded data or is missing required UI elements), the fixed controllers and blade
templates SHALL render only data derived from that session's `translation_history` records and
SHALL include every required UI element (counter, speaker icons, filters, progress bars,
grouping, badges, action icons, Quick Actions panel).

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14**

Property 2: Preservation — All Existing Functional Flows Unchanged

_For any_ input that does NOT involve the four affected page renders (i.e., all POST
endpoints, re-download, view-modal, swap, copy, save, auth, settings), the fixed code SHALL
produce exactly the same behavior as the original code, preserving all existing translation,
storage, and authentication functionality.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**

---

## Fix Implementation

### 1. DashboardController

**File:** `app/Http/Controllers/DashboardController.php` *(new file)*

**Responsibility:** Fetch all `translation_history` rows for the current session via
`HistoryService::getHistory()`, compute the three stat values in PHP, slice the five most
recent records, and pass everything to the `dashboard` view.

**Specific Changes:**

```
FUNCTION computeStats(records)
  totalDocs        := COUNT records WHERE translation_type = 'document'
  currentMonthStr  := date('Y-m')
  translationsThisMonth := COUNT records WHERE created_at STARTS WITH currentMonthStr
  wordsTranslated  := SUM over text records of wordCount(source_text)
                      + SUM over document records of estimatedWordCount(original_filename)
  RETURN { totalDocs, translationsThisMonth, wordsTranslated }
END FUNCTION
```

- `wordCount(text)` = `str_word_count($text)` (PHP built-in).
- Document records have no stored word count; use a fixed estimate of **250 words per
  document** as a reasonable default (clearly documented in code comments).
- `recentRecords` = first 5 elements of the already-descending `getHistory()` result.
- On `HistoryService` exception: pass `$stats = ['totalDocs'=>0, 'translationsThisMonth'=>0,
  'wordsTranslated'=>0]`, `$recentRecords = []`, `$error = true`.

**Route change:** Register `DashboardController@index` for `GET /dashboard` in
`routes/web.php`, replacing any existing closure.

---

### 2. Dashboard Blade (`resources/views/dashboard.blade.php`)

**Specific Changes:**

- Replace hardcoded greeting with `Welcome back, {{ auth()->user()->name ?? 'User' }}`.
- Replace hardcoded stat values with `{{ $stats['totalDocs'] }}`,
  `{{ $stats['translationsThisMonth'] }}`, `{{ number_format($stats['wordsTranslated']) }}`.
- Replace hardcoded table rows with a `@forelse ($recentRecords as $record)` loop (up to 5
  rows) showing: document name or truncated source text, source → target language, formatted
  date, status pill ("Completed" for documents, "Text" for text records), and a confidence
  column (fixed "—" for now since confidence is not stored).
- Add a Quick Actions panel below the stat cards with three `<a>` links:
  "New Translation" → `route('translate')`, "Upload Document" → `route('translate')`,
  "Browse Corpus" → `#` (placeholder).
- Add `@if ($error)` banner above the cards.

---

### 3. New Translation Blade (`resources/views/translation.blade.php`)

**Specific Changes:**

- Change `maxlength="8000"` on `<textarea id="source-text">` to `maxlength="5000"`.
- Change `MAX_CHARS = 8000` in the inline JS to `MAX_CHARS = 5000`.
- Change `WARN_THRESHOLD = 7500` to `WARN_THRESHOLD = 4500`.
- Change the initial counter text from `0/8000` to `0/5000` (the JS `updateCounter()` call
  already sets this on load; the `<span>` initial text just needs updating).
- Add a speaker `<button>` in the source panel footer (before `#attach-btn`):
  ```html
  <button id="speak-source-btn" type="button" aria-label="Read source text aloud">
    <!-- speaker SVG icon -->
  </button>
  ```
- Add a speaker `<button>` in the output panel footer (before `#copy-btn`):
  ```html
  <button id="speak-output-btn" type="button" aria-label="Read translation aloud">
    <!-- speaker SVG icon -->
  </button>
  ```
- Add minimal JS for the speaker buttons using the Web Speech API
  (`window.speechSynthesis`). If the API is unavailable, the button is hidden. This does
  not affect the existing translate/copy/save flow.

---

### 4. My Documents Blade (`resources/views/my-documents.blade.php`)

**Specific Changes:**

The `DocumentsController` already passes `$documents` (real data). The blade needs new
markup only.

- **Search bar** — `<input type="search" id="docs-search" placeholder="Search documents…">`
  above the grid; client-side JS filters visible cards by title text.
- **Filter dropdowns** — `<select id="docs-lang-filter">` (All Languages / English / Cebuano
  / Filipino) and `<select id="docs-status-filter">` (All Status / Translated / Original);
  client-side JS filters cards.
- **Grid/list toggle** — two icon buttons that add/remove a `.docs-list-view` class on
  `.docs-grid`.
- **Tab filters** — computed in the blade from `$documents`:
  ```php
  $allCount    = count($documents);
  $recentCount = count(array_filter($documents, fn($d) =>
      \Carbon\Carbon::parse($d['created_at'])->isCurrentMonth()));
  $sharedCount = 0;   // not yet tracked in DB — show 0
  $archivedCount = 0; // not yet tracked in DB — show 0
  ```
  Rendered as `<button class="tab-btn active" data-tab="all">All <span>{{ $allCount }}</span></button>` etc.
  Client-side JS switches the active tab and filters cards.
- **Progress bar** — added inside each `.doc-card__body`:
  ```html
  <div class="doc-card__progress">
    <div class="doc-card__progress-bar" style="width: {{ $isTranslated ? 100 : 0 }}%"></div>
  </div>
  <span class="doc-card__progress-label">{{ $isTranslated ? '100%' : '0%' }} Complete</span>
  ```

---

### 5. Saved Translations Blade (`resources/views/history.blade.php`)

**Specific Changes:**

The `HistoryController` already passes `$records` (real data). The blade needs restructuring.

- **Page header** — replace the plain `<h2>` with a header row containing:
  - Title + count badge: `Saved Translations <span class="count-badge">{{ count($records) }}</span>`
  - Search input: `<input type="search" id="history-search" placeholder="Search translations…">`
  - Group-by select: `<select id="history-group">` with options "Group by Language Pair" / "No Grouping"
  - Sort select: `<select id="history-sort">` with options "Newest First" / "Oldest First" / "Language A–Z"
- **Grouping** — in the blade, group records by `source_language . ' → ' . target_language`
  using PHP's `array_reduce` or a `@php` block before the loop:
  ```php
  $grouped = [];
  foreach ($records as $r) {
      $key = ($r['source_language'] ?? '?') . ' → ' . ($r['target_language'] ?? '?');
      $grouped[$key][] = $r;
  }
  ```
  Render each group as a `<section class="history-group">` with a heading
  `<h3 class="history-group__title">Cebuano → Tagalog <span class="count-badge">2</span></h3>`
  followed by a card grid.
- **Card layout** — replace the `<table>` rows with `<div class="history-card">` elements
  containing:
  - Match badge: `<span class="match-badge">{{ $matchPct }}%</span>` where
    `$matchPct = $isDoc ? 100 : min(100, (int)(mb_strlen($r['translated_text'] ?? '') / max(1, mb_strlen($r['source_text'] ?? '')) * 100))`
  - Content preview (truncated source text or filename)
  - Date
  - Action icon row: copy, download (re-download for docs / save-as-txt for text), share
    (copies URL to clipboard), bookmark (visual toggle only — no DB persistence needed for
    this fix).
- The existing re-download JS and view-text-modal JS are preserved; the new action icons
  reuse the same `data-id` / `data-source` / `data-translated` attributes.

---

### 6. CSS Updates

**`resources/css/views/dashboard.css`** — add:
- `.welcome-greeting` — large greeting text style.
- `.stat-card__icon` — icon container inside stat cards.
- `.quick-actions` — flex row of action link cards.
- `.quick-action-card` — individual action card with hover state.
- `.recent-table__status--completed` / `--text` — status pill colours.

**`resources/css/views/translation.css`** — add:
- `.speak-btn` — speaker button style (matches existing `.translation-swap` pattern).
- `.speak-btn svg` — icon sizing.

**`resources/css/views/my-documents.css`** — add:
- `.docs-toolbar` — flex row for search + filters + toggle.
- `.docs-search` — search input style.
- `.docs-filter-select` — filter dropdown style.
- `.docs-view-toggle` — grid/list toggle button group.
- `.docs-tabs` — tab filter row.
- `.tab-btn` / `.tab-btn.active` — tab button styles.
- `.doc-card__progress` / `.doc-card__progress-bar` — progress bar track and fill.
- `.doc-card__progress-label` — small percentage label.
- `.docs-list-view .doc-card` — list-view card override (horizontal layout).

**`resources/css/views/history.css`** — add:
- `.history-page-header` — flex row for title + controls.
- `.count-badge` — pill badge for counts.
- `.history-search` / `.history-select` — search and sort/group controls.
- `.history-group` — group section wrapper.
- `.history-group__title` — group heading style.
- `.history-cards` — card grid inside a group.
- `.history-card` — individual card (replaces table row).
- `.match-badge` — percentage badge (blue pill).
- `.history-card__actions` — icon row at card bottom.
- `.history-card__action-btn` — individual icon button.

All new CSS uses the existing CSS custom properties (`--card-bg`, `--primary`, `--border`,
`--muted`, `--text`, `--bg`, `--radius`) so dark-mode support is automatic.

---

### 7. Data Scoping Strategy

**Current approach (unchanged):** All `translation_history` queries are scoped by
`session_id = eq.{session()->getId()}` via `HistoryService::getHistory()`. This is the
existing pattern used by `DocumentsController` and `HistoryController`.

**Why `session_id` and not `user_id`:** The current schema stores `session_id` (not a
`user_id` foreign key). The Laravel auth system (`auth()->user()`) provides the user's name
for display, but the data ownership key remains `session_id`. This means:

- A user who logs in from a new browser gets a new session and sees no history — this is a
  known limitation of the current architecture, not introduced by this fix.
- No schema migration is required for this fix.
- All four controllers (`DashboardController`, `DocumentsController`, `HistoryController`,
  `TranslationController`) use `session()->getId()` consistently.

**DashboardController scoping:**
```php
$sessionId = session()->getId();
$records   = $this->history->getHistory($sessionId);  // existing HistoryService method
```

The `getHistory()` method already applies `'session_id' => "eq.{$sessionId}"` as a Supabase
query parameter, so no new Supabase queries or service methods are needed for the dashboard
stats — the controller derives all three stat values from the already-fetched `$records`
array in PHP.

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that
demonstrate the bug on unfixed code, then verify the fix works correctly and preserves
existing behavior.

### Exploratory Bug Condition Checking

**Goal:** Surface counterexamples that demonstrate the bug BEFORE implementing the fix.
Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan:** Write feature/integration tests that authenticate a session, seed known
`translation_history` rows via `HistoryService` (or directly via Supabase test fixtures),
then assert on the rendered HTML. Run these tests on the UNFIXED code to observe failures.

**Test Cases:**

1. **Dashboard stat cards show hardcoded values** — seed 3 document records for a session,
   GET `/dashboard`, assert the response contains "3" not "24" for Total Documents.
   (Will fail on unfixed code.)
2. **Dashboard greeting lacks real name** — authenticate as "Maria Santos", GET `/dashboard`,
   assert response contains "Maria Santos". (Will fail on unfixed code.)
3. **New Translation counter shows wrong limit** — GET `/translate`, assert response contains
   "0/5000" not "0/8000". (Will fail on unfixed code.)
4. **Speaker icons absent** — GET `/translate`, assert response contains `speak-source-btn`.
   (Will fail on unfixed code.)
5. **My Documents has no tab filters** — GET `/documents`, assert response contains
   `tab-btn`. (Will fail on unfixed code.)
6. **History not grouped** — GET `/history`, assert response contains `history-group`.
   (Will fail on unfixed code.)

**Expected Counterexamples:**
- Dashboard renders "24" regardless of seeded record count.
- `/translate` response contains "8000" not "5000".
- No elements with class `speak-source-btn`, `tab-btn`, `history-group`, `match-badge`
  exist in the respective page responses.

### Fix Checking

**Goal:** Verify that for all inputs where the bug condition holds, the fixed code produces
the expected behavior.

**Pseudocode:**
```
FOR ALL session WHERE isBugCondition(GET /dashboard | /translate | /documents | /history) DO
  response := GET fixedPage(session)
  ASSERT NOT isBugCondition(response)
  ASSERT containsRealData(response, session.records)
  ASSERT containsRequiredUIElements(response)
END FOR
```

### Preservation Checking

**Goal:** Verify that for all inputs where the bug condition does NOT hold (i.e., all
existing functional flows), the fixed code produces the same result as the original code.

**Pseudocode:**
```
FOR ALL request WHERE NOT isBugCondition(request) DO
  ASSERT originalHandler(request) = fixedHandler(request)
END FOR
```

**Testing Approach:** Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain.
- It catches edge cases that manual unit tests might miss.
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs.

**Test Plan:** Observe behavior on UNFIXED code first for POST /translate, re-download, and
modal flows, then write property-based tests capturing that behavior.

**Test Cases:**

1. **Text translation preservation** — POST `/translate` with valid text returns `translated`
   JSON; verify this continues after fix.
2. **Document translation preservation** — POST `/translate` with a valid file returns
   `download_url`; verify this continues after fix.
3. **Re-download preservation** — POST `/history/redownload/{id}` returns `download_url`;
   verify this continues after fix.
4. **Swap button preservation** — GET `/translate`, assert swap button markup is present and
   JS handler is unchanged.
5. **Auth redirect preservation** — unauthenticated GET `/dashboard` returns redirect to
   login; verify this continues after fix.
6. **Empty state preservation** — session with zero document records, GET `/documents`,
   assert empty-state message is present.

### Unit Tests

- `DashboardController::computeStats()` with an empty records array returns all zeros.
- `DashboardController::computeStats()` with mixed document/text records returns correct
  `totalDocs` (documents only), correct `translationsThisMonth` (current month only), and
  correct `wordsTranslated` (sum of `str_word_count` for text records + 250 per document).
- `DashboardController::computeStats()` with records from a previous month returns
  `translationsThisMonth = 0`.
- Match percentage calculation: `translated_text` length / `source_text` length × 100,
  capped at 100.

### Property-Based Tests

- For any array of `translation_history` records, `computeStats()` returns
  `totalDocs >= 0`, `translationsThisMonth >= 0`, `wordsTranslated >= 0`.
- For any array of records, `totalDocs <= count(records)` (documents are a subset).
- For any array of records, `translationsThisMonth <= count(records)`.
- For any `source_text` and `translated_text`, match percentage is in `[0, 100]`.

### Integration Tests

- Full page render of `/dashboard` with seeded records returns correct stat values and
  correct recent-translations rows (up to 5).
- Full page render of `/translate` contains `0/5000` counter and speaker button elements.
- Full page render of `/documents` with seeded records contains tab filter buttons with
  correct counts and progress bars on cards.
- Full page render of `/history` with seeded records contains grouped sections, match badges,
  and action icon buttons.
- POST `/translate` (text) still returns `{ "translated": "..." }` after the blade changes.
- POST `/history/redownload/{id}` still returns `{ "download_url": "..." }` after the
  controller changes.
