@extends('layouts.app')

@section('title', 'My Documents')

@section('styles')
    @vite(['resources/css/views/my-documents.css'])
@endsection

@section('content')
<div class="docs-stack">

    {{-- ── Page header ──────────────────────────────────────────────────── --}}
    <div class="docs-header">
        <div class="docs-header-left">
            <h2 class="docs-title">
                My Documents
                @if (!$error && count($documents) > 0)
                    <span class="docs-count">{{ count($documents) }}</span>
                @endif
            </h2>
        </div>
        <a href="{{ route('translate') }}" class="btn primary docs-upload-btn">Upload Now</a>
    </div>

    {{-- ── Error state ──────────────────────────────────────────────────── --}}
    @if ($error)
        <p class="docs-empty">Unable to load documents. Please try again later.</p>

    {{-- ── Empty state ──────────────────────────────────────────────────── --}}
    @elseif (empty($documents))
        <div class="docs-empty-box">
            <p class="docs-empty">You have no documents yet.</p>
            <a href="{{ route('translate') }}" class="btn primary" style="margin-top:12px">Translate your first document</a>
        </div>

    {{-- ── Document grid ────────────────────────────────────────────────── --}}
    @else
        @php
            // Compute tab counts from $documents
            $allCount      = count($documents);
            $recentCount   = count(array_filter($documents, fn($d) =>
                \Carbon\Carbon::parse($d['created_at'])->isCurrentMonth()));
            $sharedCount   = 0;   // not yet tracked in DB — show 0
            $archivedCount = 0;   // not yet tracked in DB — show 0

            // Separate originals (no parent) from translations (have parent)
            $originals = array_values(array_filter($documents, fn($d) => empty($d['parent_document_id'])));
            $translations = array_values(array_filter($documents, fn($d) => !empty($d['parent_document_id'])));

            // Group translations by parent_document_id
            $translationsByParent = [];
            foreach ($translations as $t) {
                $pid = $t['parent_document_id'];
                $translationsByParent[$pid][] = $t;
            }
        @endphp

        {{-- ── Toolbar: search, filters, view toggle ──────────────────── --}}
        <div class="docs-toolbar">
            <input type="search"
                   id="docs-search"
                   class="docs-search"
                   placeholder="Search documents…"
                   aria-label="Search documents">

            <select id="docs-lang-filter" class="docs-filter-select" aria-label="Filter by language">
                <option value="">All Languages</option>
                <option value="English">English</option>
                <option value="Cebuano">Cebuano</option>
                <option value="Filipino">Filipino</option>
            </select>

            <select id="docs-status-filter" class="docs-filter-select" aria-label="Filter by status">
                <option value="">All Status</option>
                <option value="original">Originals Only</option>
                <option value="translated">Translations Only</option>
            </select>

            <div class="docs-view-toggle" role="group" aria-label="View mode">
                <button id="docs-grid-btn" class="docs-view-btn docs-view-btn--active" aria-label="Grid view" aria-pressed="true">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <rect x="1" y="1" width="6" height="6" rx="1" fill="currentColor"/>
                        <rect x="9" y="1" width="6" height="6" rx="1" fill="currentColor"/>
                        <rect x="1" y="9" width="6" height="6" rx="1" fill="currentColor"/>
                        <rect x="9" y="9" width="6" height="6" rx="1" fill="currentColor"/>
                    </svg>
                </button>
                <button id="docs-list-btn" class="docs-view-btn" aria-label="List view" aria-pressed="false">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <rect x="1" y="2" width="14" height="2" rx="1" fill="currentColor"/>
                        <rect x="1" y="7" width="14" height="2" rx="1" fill="currentColor"/>
                        <rect x="1" y="12" width="14" height="2" rx="1" fill="currentColor"/>
                    </svg>
                </button>
            </div>
        </div>

        {{-- ── Tab filters ──────────────────────────────────────────────── --}}
        <div class="docs-tabs" role="tablist" aria-label="Document filters">
            <button class="tab-btn active" data-tab="all" role="tab" aria-selected="true">
                All <span class="tab-count">{{ $allCount }}</span>
            </button>
            <button class="tab-btn" data-tab="recent" role="tab" aria-selected="false">
                Recent <span class="tab-count">{{ $recentCount }}</span>
            </button>
            <button class="tab-btn" data-tab="shared" role="tab" aria-selected="false">
                Shared <span class="tab-count">{{ $sharedCount }}</span>
            </button>
            <button class="tab-btn" data-tab="archived" role="tab" aria-selected="false">
                Archived <span class="tab-count">{{ $archivedCount }}</span>
            </button>
        </div>

        <div class="docs-grid" id="docs-grid">
            @foreach ($documents as $doc)
                @php
                    $isTranslated = !empty($doc['original_filename']) && !empty($doc['translated_filename']);
                    $isOriginal   = empty($doc['parent_document_id']);
                    $hasParent    = !empty($doc['parent_document_id']);
                    // Get child translations for this record
                    $childTranslations = $translationsByParent[$doc['id']] ?? [];
                    $translationCount  = count($childTranslations);

                    // Determine the display name and language badge
                    $displayName  = $doc['translated_filename'] ?? $doc['original_filename'] ?? 'Untitled';
                    $langLabel    = $doc['source_language'] ?? '—';
                    // Pick a colour for the language badge based on language
                    $langColors   = [
                        'Cebuano'  => 'badge--cebuano',
                        'Filipino' => 'badge--filipino',
                        'Tagalog'  => 'badge--tagalog',
                        'English'  => 'badge--english',
                    ];
                    $langClass    = $langColors[$langLabel] ?? 'badge--default';
                    $date         = \Carbon\Carbon::parse($doc['created_at'])->format('M j, Y');
                    $isCurrentMonth = \Carbon\Carbon::parse($doc['created_at'])->isCurrentMonth();
                @endphp

                <div class="doc-card"
                     data-title="{{ strtolower($displayName) }}"
                     data-lang="{{ $langLabel }}"
                     data-status="{{ $isOriginal ? 'original' : 'translated' }}"
                     data-recent="{{ $isCurrentMonth ? 'true' : 'false' }}">
                    {{-- Coloured top accent bar (matches language badge colour) --}}
                    <div class="doc-card__accent doc-card__accent--{{ strtolower($langLabel) }}"></div>

                    <div class="doc-card__body">
                        {{-- Language badge + word count row --}}
                        <div class="doc-card__meta-row">
                            <span class="lang-badge {{ $langClass }}">{{ $langLabel }}</span>
                            @if ($isOriginal && $translationCount > 0)
                                <span class="doc-card__translation-count">{{ $translationCount }} translation{{ $translationCount > 1 ? 's' : '' }}</span>
                            @endif
                        </div>

                        {{-- Document title --}}
                        <h3 class="doc-card__title" title="{{ $displayName }}">{{ $displayName }}</h3>

                        {{-- Original / Translated badge --}}
                        <div class="doc-card__type-row">
                            @if ($hasParent)
                                <span class="type-pill type-pill--translated">Translated</span>
                                <span class="doc-card__from-label">
                                    from: <span class="doc-card__from-name" title="{{ $doc['original_filename'] }}">{{ \Illuminate\Support\Str::limit($doc['original_filename'], 40) }}</span>
                                </span>
                            @elseif ($isOriginal)
                                <span class="type-pill type-pill--original">Original</span>
                                @if ($translationCount > 0)
                                    <span class="doc-card__from-label">
                                        {{ $translationCount }} translation{{ $translationCount > 1 ? 's' : '' }} generated
                                    </span>
                                @endif
                            @endif
                        </div>

                        {{-- Target language tags --}}
                        <div class="doc-card__targets">
                            <span class="doc-card__targets-label">Target:</span>
                            <span class="target-tag">{{ $doc['target_language'] ?? '—' }}</span>
                        </div>

                        {{-- Translation progress bar --}}
                        <div class="doc-card__progress">
                            <div class="doc-card__progress-bar"
                                 style="width: {{ $isTranslated ? 100 : 0 }}%"
                                 role="progressbar"
                                 aria-valuenow="{{ $isTranslated ? 100 : 0 }}"
                                 aria-valuemin="0"
                                 aria-valuemax="100"></div>
                        </div>
                        <span class="doc-card__progress-label">{{ $isTranslated ? '100%' : '0%' }} Complete</span>

                        {{-- Translations sub-list (for original documents) --}}
                        @if ($isOriginal && $translationCount > 0)
                        <div class="doc-card__translations">
                            <h4 class="doc-card__translations-title">Translations</h4>
                            @foreach ($childTranslations as $child)
                                <div class="doc-card__translation-row">
                                    <span class="doc-card__translation-name" title="{{ $child['translated_filename'] }}">{{ \Illuminate\Support\Str::limit($child['translated_filename'], 35) }}</span>
                                    <span class="doc-card__translation-lang">{{ $child['target_language'] ?? '—' }}</span>
                                    <button class="doc-action-link doc-card__translation-download"
                                            data-id="{{ $child['id'] }}"
                                            data-filename="{{ $child['translated_filename'] ?? '' }}">
                                        Download
                                    </button>
                                </div>
                            @endforeach
                        </div>
                        @endif
                    </div>

                    {{-- Footer: date + action --}}
                    <div class="doc-card__footer">
                        <span class="doc-card__date">{{ $date }}</span>
                        <div class="doc-card__actions">
                            @if ($hasParent)
                                {{-- Translation: download translated + view original --}}
                                <button class="doc-action-link redownload-btn"
                                        data-id="{{ $doc['id'] }}"
                                        data-filename="{{ $doc['translated_filename'] ?? $doc['original_filename'] }}">
                                    Download
                                </button>
                                @if (!empty($doc['original_storage_path']))
                                <button class="doc-action-link redownload-original-btn"
                                        data-id="{{ $doc['id'] }}"
                                        title="View original document">
                                    Original
                                </button>
                                @endif
                            @else
                                {{-- Original: open translated (if available) + view original --}}
                                <button class="doc-action-link redownload-btn"
                                        data-id="{{ $doc['id'] }}"
                                        data-filename="{{ $doc['translated_filename'] ?? $doc['original_filename'] }}">
                                    Open
                                </button>
                                @if (!empty($doc['original_storage_path']))
                                <button class="doc-action-link redownload-original-btn"
                                        data-id="{{ $doc['id'] }}"
                                        title="Download original document">
                                    Original
                                </button>
                                @endif
                            @endif
                            <button class="doc-card__more" aria-label="More options">&#8943;</button>
                        </div>
                    </div>
                </div>
            @endforeach
        </div>
    @endif

    <div id="redownload-error" class="error-message" style="display:none"></div>

</div>

<script>
(function () {
    'use strict';

    var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    /* ── Helper: fetch JSON ──────────────────────────────────────────────── */
    function fetchJson(url, options) {
        return fetch(url, options).then(function (response) {
            return response.text().then(function (raw) {
                var data = null;
                try { data = JSON.parse(raw); } catch (e) {}
                if (!response.ok) {
                    throw new Error((data && data.error) || 'Request failed.');
                }
                return data;
            });
        });
    }

    /* ── Re-download / Open button ──────────────────────────────────────── */
    var errorEl = document.getElementById('redownload-error');

    function showError(msg) { errorEl.textContent = msg; errorEl.style.display = ''; }
    function clearError()   { errorEl.textContent = ''; errorEl.style.display = 'none'; }

    function handleRedownload(btn) {
        clearError();
        var id  = btn.getAttribute('data-id');
        var origText = btn.textContent;

        btn.disabled = true;
        btn.textContent = '...';

        fetchJson('/history/redownload/' + encodeURIComponent(id), {
            method: 'POST',
            headers: {
                'X-CSRF-TOKEN': csrfToken,
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        })
        .then(function (data) {
            if (data && data.download_url) {
                window.location.href = data.download_url;
            } else {
                showError('Unable to generate download link. Please try again later.');
            }
        })
        .catch(function (err) { showError(err.message || 'Network error. Please try again.'); })
        .finally(function () { btn.disabled = false; btn.textContent = origText; });
    }

    document.querySelectorAll('.redownload-btn').forEach(function (btn) {
        btn.addEventListener('click', function () { handleRedownload(btn); });
    });

    /* ── Download original button ──────────────────────────────────────── */
    document.querySelectorAll('.redownload-original-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            clearError();
            var id  = btn.getAttribute('data-id');
            var origText = btn.textContent;

            btn.disabled = true;
            btn.textContent = '...';

            fetchJson('/history/redownload-original/' + encodeURIComponent(id), {
                method: 'POST',
                headers: {
                    'X-CSRF-TOKEN': csrfToken,
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            })
            .then(function (data) {
                if (data && data.download_url) {
                    window.location.href = data.download_url;
                } else {
                    showError('Original document is not available.');
                }
            })
            .catch(function (err) { showError(err.message || 'Network error. Please try again.'); })
            .finally(function () { btn.disabled = false; btn.textContent = origText; });
        });
    });

    /* ── Translation row download buttons ─────────────────────────────── */
    document.querySelectorAll('.doc-card__translation-download').forEach(function (btn) {
        btn.addEventListener('click', function () {
            clearError();
            var id  = btn.getAttribute('data-id');

            fetchJson('/history/redownload/' + encodeURIComponent(id), {
                method: 'POST',
                headers: {
                    'X-CSRF-TOKEN': csrfToken,
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            })
            .then(function (data) {
                if (data && data.download_url) {
                    window.location.href = data.download_url;
                }
            })
            .catch(function (err) { showError(err.message || 'Network error.'); });
        });
    });

    /* ── Client-side filtering (search, dropdowns, tabs, view toggle) ─────── */
    var grid       = document.getElementById('docs-grid');
    var searchEl   = document.getElementById('docs-search');
    var langEl     = document.getElementById('docs-lang-filter');
    var statusEl   = document.getElementById('docs-status-filter');
    var gridBtn    = document.getElementById('docs-grid-btn');
    var listBtn    = document.getElementById('docs-list-btn');
    var tabBtns    = document.querySelectorAll('.tab-btn');

    // Only run filter logic when the grid exists (i.e. not in empty/error state)
    if (!grid) { return; }

    var cards = Array.from(grid.querySelectorAll('.doc-card'));

    // Current filter state
    var state = {
        search: '',
        lang:   '',
        status: '',
        tab:    'all'
    };

    function applyFilters() {
        cards.forEach(function (card) {
            var title   = card.getAttribute('data-title') || '';
            var lang    = card.getAttribute('data-lang')   || '';
            var status  = card.getAttribute('data-status') || '';
            var recent  = card.getAttribute('data-recent') === 'true';

            var matchSearch = !state.search || title.indexOf(state.search.toLowerCase()) !== -1;
            var matchLang   = !state.lang   || lang === state.lang;
            var matchStatus = !state.status || status === state.status;

            var matchTab = true;
            if (state.tab === 'recent')   { matchTab = recent; }
            if (state.tab === 'shared')   { matchTab = false; }   // 0 shared — hide all
            if (state.tab === 'archived') { matchTab = false; }   // 0 archived — hide all

            card.style.display = (matchSearch && matchLang && matchStatus && matchTab) ? '' : 'none';
        });
    }

    // Search input
    if (searchEl) {
        searchEl.addEventListener('input', function () {
            state.search = searchEl.value.trim();
            applyFilters();
        });
    }

    // Language filter
    if (langEl) {
        langEl.addEventListener('change', function () {
            state.lang = langEl.value;
            applyFilters();
        });
    }

    // Status filter
    if (statusEl) {
        statusEl.addEventListener('change', function () {
            state.status = statusEl.value;
            applyFilters();
        });
    }

    // Tab switching
    tabBtns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            tabBtns.forEach(function (b) {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            state.tab = btn.getAttribute('data-tab') || 'all';
            applyFilters();
        });
    });

    // Grid / list view toggle
    if (gridBtn && listBtn) {
        gridBtn.addEventListener('click', function () {
            grid.classList.remove('docs-list-view');
            gridBtn.classList.add('docs-view-btn--active');
            gridBtn.setAttribute('aria-pressed', 'true');
            listBtn.classList.remove('docs-view-btn--active');
            listBtn.setAttribute('aria-pressed', 'false');
        });

        listBtn.addEventListener('click', function () {
            grid.classList.add('docs-list-view');
            listBtn.classList.add('docs-view-btn--active');
            listBtn.setAttribute('aria-pressed', 'true');
            gridBtn.classList.remove('docs-view-btn--active');
            gridBtn.setAttribute('aria-pressed', 'false');
        });
    }
})();
</script>
@endsection