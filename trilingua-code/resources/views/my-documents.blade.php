@extends('layouts.app')

@section('title', 'My Documents')

@section('styles')
    @vite(['resources/css/views/my-documents.css'])

    {{-- Inline modal + dropdown styles (ensures they work without Vite recompilation) --}}
    <style>
    /* ════════════════════════════════════════════════════════════════════════
       Document Details / Rename / Delete Modals — Inline Styles
       ════════════════════════════════════════════════════════════════════════ */
    .detail-modal{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center}
    .detail-modal__overlay{position:absolute;inset:0;background:rgba(0,0,0,.5);backdrop-filter:blur(2px)}
    .detail-modal__dialog{position:relative;background:var(--card-bg,#fff);border-radius:16px;padding:32px;max-width:640px;width:92%;max-height:85vh;overflow-y:auto;box-shadow:0 24px 48px rgba(15,23,42,.18);animation:dmin .25s cubic-bezier(.34,1.56,.64,1) forwards}
    .detail-modal__dialog--small{max-width:420px;padding:24px}
    @keyframes dmin{from{opacity:0;transform:scale(.95) translateY(10px)}to{opacity:1;transform:scale(1) translateY(0)}}
    .detail-modal__close{position:absolute;top:16px;right:20px;background:none;border:none;font-size:1.5rem;cursor:pointer;color:var(--muted,#6b7280);width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;transition:background .15s,color .15s;z-index:1}
    .detail-modal__close:hover{background:var(--bg,#f1f5f9);color:var(--text,#111827)}
    .detail-modal__loading{display:flex;flex-direction:column;align-items:center;gap:12px;padding:40px 0;color:var(--muted,#6b7280);font-size:.875rem}
    .detail-modal__spinner{width:32px;height:32px;border:3px solid var(--border,#e5e7eb);border-top-color:var(--primary,#3b82f6);border-radius:50%;animation:dsp .7s linear infinite}
    @keyframes dsp{to{transform:rotate(360deg)}}
    .detail-modal__header{margin-bottom:20px}
    .detail-modal__type-badge{display:inline-block;padding:3px 10px;border-radius:99px;font-size:.72rem;font-weight:700;text-transform:uppercase;margin-bottom:8px}
    .detail-modal__type-badge--doc{background:#e0f0ff;color:#1a6fb5}
    .detail-modal__type-badge--text{background:#e8f5e9;color:#2e7d32}
    .detail-modal__title{font-size:1.15rem;font-weight:700;color:var(--text,#111827);margin:0 0 4px;word-break:break-word}
    .detail-modal__subtitle{font-size:.82rem;color:var(--muted,#6b7280);margin:0}
    .detail-modal__meta-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 20px;background:var(--bg,#f8f9fa);padding:16px;border-radius:10px;margin-bottom:20px}
    .detail-modal__meta-item{display:flex;flex-direction:column;gap:2px}
    .detail-modal__meta-label{font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--muted,#6b7280)}
    .detail-modal__meta-value{font-size:.88rem;font-weight:500;color:var(--text,#111827)}
    .detail-modal__section-title{font-size:.82rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--muted,#6b7280);margin:0 0 8px}
    .detail-modal__text-block{background:var(--input-bg,#f8f9fa);border:1px solid var(--border,#e5e7eb);border-radius:8px;padding:12px 14px;font-size:.88rem;line-height:1.55;color:var(--text,#111827);white-space:pre-wrap;word-break:break-word;max-height:180px;overflow-y:auto;margin-bottom:16px}
    .detail-modal__translations-list{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
    .detail-modal__translation-item{display:flex;align-items:center;gap:10px;padding:8px 12px;background:var(--input-bg,#f8f9fa);border:1px solid var(--border,#e5e7eb);border-radius:8px;font-size:.85rem}
    .detail-modal__translation-name{flex:1;font-weight:500;color:var(--text,#111827);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .detail-modal__translation-lang{font-size:.78rem;color:var(--muted,#6b7280);white-space:nowrap}
    .detail-modal__translation-date{font-size:.75rem;color:var(--muted,#6b7280);white-space:nowrap}
    .detail-modal__actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px;padding-top:16px;border-top:1px solid var(--border,#e5e7eb)}
    .detail-modal__action-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border:1px solid var(--border,#e5e7eb);border-radius:8px;background:var(--card-bg,#fff);color:var(--text,#111827);font-size:.82rem;font-weight:500;cursor:pointer;transition:background .15s,border-color .15s,color .15s}
    .detail-modal__action-btn:hover{background:var(--bg,#f1f5f9);border-color:var(--primary,#3b82f6);color:var(--primary,#3b82f6)}
    .detail-modal__action-btn:disabled{opacity:.5;cursor:not-allowed}
    .detail-modal__action-btn--primary{background:var(--primary,#3b82f6);color:#fff;border-color:var(--primary,#3b82f6)}
    .detail-modal__action-btn--primary:hover{background:#2563eb;color:#fff;border-color:#2563eb}
    .detail-modal__action-btn--danger{color:#ef4444;border-color:#fecaca}
    .detail-modal__action-btn--danger:hover{background:#fef2f2;border-color:#ef4444;color:#dc2626}
    .detail-modal__confirm-text{font-size:.9rem;color:var(--muted,#6b7280);margin:12px 0 20px;line-height:1.5}
    .detail-modal__confirm-actions{display:flex;justify-content:flex-end;gap:8px}
    .detail-modal__divider{height:1px;background:var(--border,#e5e7eb);margin:16px 0}
    .detail-modal__field{display:flex;flex-direction:column;gap:6px;margin:4px 0 20px}
    .detail-modal__input{padding:9px 12px;border:1px solid var(--border,#e5e7eb);border-radius:8px;background:var(--input-bg,#fff);color:var(--text,#111827);font-size:.9rem;outline:none;transition:border-color .15s,box-shadow .15s}
    .detail-modal__input:focus{border-color:var(--primary,#3b82f6);box-shadow:0 0 0 3px rgba(59,130,246,.12)}
    .detail-modal__error{font-size:.8rem;color:#dc2626;margin:-12px 0 16px}
    @media(max-width:640px){.detail-modal__dialog{padding:24px 20px;max-height:90vh}.detail-modal__meta-grid{grid-template-columns:1fr}.detail-modal__actions{flex-direction:column}.detail-modal__action-btn{justify-content:center}.detail-modal__translation-item{flex-wrap:wrap}}

    /* ── Three-dot dropdown menu ──────────────────────────────────────────── */
    .doc-more-menu{position:fixed;z-index:1001;min-width:160px;background:var(--card-bg,#fff);border:1px solid var(--border,#e5e7eb);border-radius:10px;box-shadow:0 12px 32px rgba(15,23,42,.16);padding:6px;display:flex;flex-direction:column;gap:2px;animation:dmin .18s cubic-bezier(.34,1.56,.64,1) forwards}
    .doc-more-menu__item{display:flex;align-items:center;gap:8px;width:100%;padding:8px 12px;border:none;background:none;border-radius:7px;font-size:.85rem;font-weight:500;color:var(--text,#111827);cursor:pointer;text-align:left;transition:background .12s,color .12s}
    .doc-more-menu__item:hover{background:var(--bg,#f1f5f9)}
    .doc-more-menu__item--danger{color:#ef4444}
    .doc-more-menu__item--danger:hover{background:#fef2f2}
    .doc-more-menu__item--priority{color:#b45309}
    .doc-more-menu__item--priority:hover{background:#fef3c7}
    </style>
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

            <select id="docs-lang-filter" class="docs-filter-select" aria-label="Filter by language pair">
                <option value="">All Language Pairs</option>
                @foreach ($langPairs as $pair)
                    <option value="{{ $pair }}">{{ $pair }}</option>
                @endforeach
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
                    $langPair     = ($doc['source_language'] ?? '') . ' → ' . ($doc['target_language'] ?? '');
                    // Pick a colour for the language badge based on language
                    $langColors   = [
                        'Cebuano'  => 'badge--cebuano',
                        'Filipino' => 'badge--filipino',
                        'English'  => 'badge--english',
                    ];
                    $langClass    = $langColors[$langLabel] ?? 'badge--default';
                    $date         = \Carbon\Carbon::parse($doc['created_at'])->format('M j, Y');
                    $isCurrentMonth = \Carbon\Carbon::parse($doc['created_at'])->isCurrentMonth();
                @endphp

                <div class="doc-card"
                     data-id="{{ $doc['id'] }}"
                     data-title="{{ strtolower($displayName) }}"
                     data-lang="{{ $langPair }}"
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
                            <button class="doc-card__more"
                                    aria-label="More options"
                                    data-id="{{ $doc['id'] }}"
                                    data-filename="{{ $displayName }}"
                                    data-is-original="{{ $isOriginal ? 'true' : 'false' }}"
                                    data-priority="{{ !empty($doc['is_priority']) ? '1' : '0' }}"
                                    data-review-status="{{ $doc['review_status'] ?? 'pending' }}">&#8943;</button>
                        </div>
                    </div>
                </div>
            @endforeach
        </div>
    @endif

    <div id="redownload-error" class="error-message" style="display:none"></div>

</div>

{{-- ═══════════════════════════════════════════════════════════════════════════ --}}
{{-- Three-dot dropdown menu                                                   --}}
{{-- ═══════════════════════════════════════════════════════════════════════════ --}}
<div id="doc-more-menu" class="doc-more-menu" style="display:none" role="menu" aria-label="Document actions">
    <button type="button" class="doc-more-menu__item" data-action="details" role="menuitem">Details</button>
    <button type="button" class="doc-more-menu__item" data-action="rename" role="menuitem">Rename</button>
    <button type="button" class="doc-more-menu__item doc-more-menu__item--priority" data-action="priority" role="menuitem">Request priority review</button>
    <button type="button" class="doc-more-menu__item doc-more-menu__item--danger" data-action="delete" role="menuitem">Delete</button>
</div>

{{-- ═══════════════════════════════════════════════════════════════════════════ --}}
{{-- Document Details Modal (mirrors Saved Translations)                       --}}
{{-- ═══════════════════════════════════════════════════════════════════════════ --}}
<div id="detail-modal" class="detail-modal" style="display:none">
    <div class="detail-modal__overlay"></div>
    <div class="detail-modal__dialog" role="dialog" aria-modal="true" aria-labelledby="detail-modal-title">
        <button class="detail-modal__close" id="detail-modal-close" aria-label="Close">&times;</button>

        <div id="detail-modal-loading" class="detail-modal__loading">
            <div class="detail-modal__spinner"></div>
            <p>Loading details…</p>
        </div>

        <div id="detail-modal-content" style="display:none">
            <div class="detail-modal__header">
                <div class="detail-modal__type-badge" id="detail-type-badge"></div>
                <h3 id="detail-modal-title" class="detail-modal__title"></h3>
                <p class="detail-modal__subtitle" id="detail-modal-subtitle"></p>
            </div>

            <div class="detail-modal__meta-grid" id="detail-meta-grid">
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Source Language</span>
                    <span class="detail-modal__meta-value" id="detail-source-lang"></span>
                </div>
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Target Language</span>
                    <span class="detail-modal__meta-value" id="detail-target-lang"></span>
                </div>
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Date & Time</span>
                    <span class="detail-modal__meta-value" id="detail-date"></span>
                </div>
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Translation Type</span>
                    <span class="detail-modal__meta-value" id="detail-type"></span>
                </div>
                <div class="detail-modal__meta-item" id="detail-filesize-wrap">
                    <span class="detail-modal__meta-label">File Size</span>
                    <span class="detail-modal__meta-value" id="detail-filesize"></span>
                </div>
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Status</span>
                    <span class="detail-modal__meta-value" id="detail-status"></span>
                </div>
                <div class="detail-modal__meta-item">
                    <span class="detail-modal__meta-label">Review Status</span>
                    <span class="detail-modal__meta-value" id="detail-review-status"></span>
                </div>
            </div>

            <div id="detail-translations-section" style="display:none">
                <h4 class="detail-modal__section-title">Translations</h4>
                <div id="detail-translations-list" class="detail-modal__translations-list"></div>
            </div>

            <div class="detail-modal__actions">
                <button class="detail-modal__action-btn detail-modal__action-btn--primary" id="detail-action-view">View / Download</button>
                <button class="detail-modal__action-btn" id="detail-action-original" style="display:none">Open Original</button>
                <button class="detail-modal__action-btn" id="detail-action-rename">Rename</button>
                <button class="detail-modal__action-btn detail-modal__action-btn--danger" id="detail-action-delete">Delete</button>
            </div>
        </div>
    </div>
</div>

{{-- Rename modal --}}
<div id="rename-modal" class="detail-modal" style="display:none">
    <div class="detail-modal__overlay"></div>
    <div class="detail-modal__dialog detail-modal__dialog--small" role="dialog" aria-modal="true" aria-labelledby="rename-modal-title">
        <h3 id="rename-modal-title" class="detail-modal__title">Rename Document</h3>
        <p class="detail-modal__confirm-text">Enter a new display name for this document. The file extension is preserved.</p>
        <div class="detail-modal__field">
            <input id="rename-input" type="text" class="detail-modal__input" autocomplete="off" maxlength="255">
        </div>
        <div id="rename-error" class="detail-modal__error" style="display:none"></div>
        <div class="detail-modal__confirm-actions">
            <button class="detail-modal__action-btn" id="rename-cancel">Cancel</button>
            <button class="detail-modal__action-btn detail-modal__action-btn--primary" id="rename-save">Save</button>
        </div>
    </div>
</div>

{{-- Delete confirmation modal --}}
<div id="delete-confirm" class="detail-modal" style="display:none">
    <div class="detail-modal__overlay"></div>
    <div class="detail-modal__dialog detail-modal__dialog--small" role="alertdialog" aria-modal="true" aria-labelledby="delete-confirm-title">
        <h3 id="delete-confirm-title" class="detail-modal__title">Delete Document?</h3>
        <p class="detail-modal__confirm-text">This will permanently delete this document and all of its translations and files. This action cannot be undone.</p>
        <div class="detail-modal__confirm-actions">
            <button class="detail-modal__action-btn" id="delete-confirm-cancel">Cancel</button>
            <button class="detail-modal__action-btn detail-modal__action-btn--danger" id="delete-confirm-ok">Delete</button>
        </div>
    </div>
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
                if (window.showErrorModal) showErrorModal('Download failed', 'Unable to generate download link. Please try again later.');
            }
        })
        .catch(function (err) { if (window.showErrorModal) showErrorModal('Download failed', err.message || 'Network error. Please try again.'); })
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
                    if (window.showErrorModal) showErrorModal('Download failed', 'Original document is not available.');
                }
            })
            .catch(function (err) { if (window.showErrorModal) showErrorModal('Download failed', err.message || 'Network error. Please try again.'); })
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
            .catch(function (err) { if (window.showErrorModal) showErrorModal('Download failed', err.message || 'Network error.'); });
        });
    });

    /* ── Client-side filtering (search, dropdowns, tabs, view toggle) ─────── */
    var grid       = document.getElementById('docs-grid');
    var searchEl   = document.getElementById('docs-search');
    var langEl     = document.getElementById('docs-lang-filter');
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
        tab:    'all'
    };

    function applyFilters() {
        cards.forEach(function (card) {
            var title   = card.getAttribute('data-title') || '';
            var lang    = card.getAttribute('data-lang')   || '';
            var recent  = card.getAttribute('data-recent') === 'true';

            var matchSearch = !state.search || title.indexOf(state.search.toLowerCase()) !== -1;
            var matchLang   = !state.lang   || lang === state.lang;

            var matchTab = true;
            if (state.tab === 'recent')   { matchTab = recent; }
            if (state.tab === 'shared')   { matchTab = false; }   // 0 shared — hide all
            if (state.tab === 'archived') { matchTab = false; }   // 0 archived — hide all

            card.style.display = (matchSearch && matchLang && matchTab) ? '' : 'none';
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

    // ══════════════════════════════════════════════════════════════════════
    // Helpers (modal)
    // ══════════════════════════════════════════════════════════════════════
    function escapeHtmlText(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatFileSize(bytes) {
        if (!bytes) return '—';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            var d = new Date(dateStr);
            return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) +
                   ' ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        } catch (e) { return dateStr; }
    }

    function openModal(modal) { if (!modal) return; modal.style.display = 'flex'; document.body.style.overflow = 'hidden'; }
    function closeModal(modal) { if (!modal) return; modal.style.display = 'none'; document.body.style.overflow = ''; }

    var authHeaders = { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' };

    // ══════════════════════════════════════════════════════════════════════
    // Three-dot dropdown menu
    // ══════════════════════════════════════════════════════════════════════
    var moreMenu      = document.getElementById('doc-more-menu');
    var currentAction = { id: null, filename: null, priority: false, review: 'pending' };

    function closeMoreMenu() { if (moreMenu) moreMenu.style.display = 'none'; }

    document.querySelectorAll('.doc-card__more').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (moreMenu && moreMenu.style.display === 'block') { closeMoreMenu(); return; }
            currentAction.id       = btn.getAttribute('data-id');
            currentAction.filename = btn.getAttribute('data-filename');
            currentAction.priority = btn.getAttribute('data-priority') === '1';
            currentAction.review   = btn.getAttribute('data-review-status') || 'pending';
            if (!moreMenu) return;
            var rect = btn.getBoundingClientRect();
            moreMenu.style.top  = (rect.bottom + 6) + 'px';
            moreMenu.style.left = Math.max(8, rect.right - 168) + 'px';
            moreMenu.style.display = 'block';

            // Only allow priority requests on records still pending review.
            var priorityItem = moreMenu.querySelector('[data-action="priority"]');
            if (priorityItem) {
                priorityItem.style.display = currentAction.review === 'pending' ? '' : 'none';
                priorityItem.textContent = currentAction.priority ? 'Remove priority review' : 'Request priority review';
            }
        });
    });

    document.addEventListener('click', function (e) {
        if (!moreMenu || moreMenu.style.display !== 'block') return;
        if (moreMenu.contains(e.target) || (e.target.closest && e.target.closest('.doc-card__more'))) return;
        closeMoreMenu();
    });

    if (moreMenu) {
        moreMenu.querySelectorAll('[data-action]').forEach(function (item) {
            item.addEventListener('click', function () {
                var action = item.getAttribute('data-action');
                closeMoreMenu();
                if (action === 'details') {
                    var id = currentAction.id;
                    window.location.href = '/history/' + encodeURIComponent(id) + '/view';
                }
                else if (action === 'rename') openRename(currentAction.id, currentAction.filename);
                else if (action === 'delete') showDeleteConfirm(currentAction.id);
                else if (action === 'priority') togglePriority(currentAction.id);
            });
        });
    }

    function togglePriority(id) {
        if (!id) return;
        fetchJson('/history/' + encodeURIComponent(id) + '/priority', {
            method: 'POST',
            headers: authHeaders
        })
        .then(function (data) {
            if (data && data.success) {
                currentAction.priority = !!data.value;
                if (window.showToast) showToast('success', data.value ? 'Priority requested' : 'Priority removed', data.value ? 'The admin has been notified to review this document first.' : 'Priority review request removed.');
                // Reflect the new state on the more button without a reload.
                var btn = document.querySelector('.doc-card__more[data-id="' + id + '"]');
                if (btn) btn.setAttribute('data-priority', data.value ? '1' : '0');
            }
        })
        .catch(function (err) {
            if (window.showToast) showToast('error', 'Error', err.message || 'Failed to update priority.');
        });
    }

    // ══════════════════════════════════════════════════════════════════════
    // Document Details modal
    // ══════════════════════════════════════════════════════════════════════
    var detailModal   = document.getElementById('detail-modal');
    var detailOverlay = detailModal ? detailModal.querySelector('.detail-modal__overlay') : null;
    var detailClose   = document.getElementById('detail-modal-close');
    var detailLoading = document.getElementById('detail-modal-loading');
    var detailContent = document.getElementById('detail-modal-content');

    function closeDetail() { closeModal(detailModal); }

    function loadDetail(id) {
        if (!detailModal) return;
        window.location.href = '/history/' + encodeURIComponent(id) + '/view';
        detailLoading.style.display = '';
        detailContent.style.display = 'none';
        openModal(detailModal);

        fetchJson('/history/' + encodeURIComponent(id), {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        })
        .then(renderDetail)
        .catch(function (err) {
            closeDetail();
            if (window.showErrorModal) showErrorModal('Unable to load details', err.message || 'Failed to load details.');
        });
    }

    function renderDetail(data) {
        detailLoading.style.display = 'none';
        detailContent.style.display = '';

        var isDoc      = (data.translation_type || 'document') === 'document';
        var isOriginal = !data.parent_document_id;

        var typeBadge = document.getElementById('detail-type-badge');
        typeBadge.textContent = isDoc ? 'Document' : 'Text';
        typeBadge.className = 'detail-modal__type-badge detail-modal__type-badge--' + (isDoc ? 'doc' : 'text');

        document.getElementById('detail-modal-title').textContent = isDoc
            ? (data.translated_filename || data.original_filename || 'Document')
            : 'Text Translation';
        document.getElementById('detail-modal-subtitle').textContent = isDoc && data.original_filename
            ? 'from: ' + data.original_filename
            : '';
        document.getElementById('detail-source-lang').textContent = data.source_language || '—';
        document.getElementById('detail-target-lang').textContent = data.target_language || '—';
        document.getElementById('detail-date').textContent = formatDate(data.created_at);
        document.getElementById('detail-type').textContent = isDoc ? 'Document Translation' : 'Text Translation';
        document.getElementById('detail-status').textContent = (data.status || 'completed').charAt(0).toUpperCase() + (data.status || 'completed').slice(1);
        document.getElementById('detail-review-status').textContent = (data.review_status || 'pending').charAt(0).toUpperCase() + (data.review_status || 'pending').slice(1);

        var filesizeWrap = document.getElementById('detail-filesize-wrap');
        if (isDoc && data.file_size) {
            filesizeWrap.style.display = '';
            document.getElementById('detail-filesize').textContent = formatFileSize(data.file_size);
        } else {
            filesizeWrap.style.display = 'none';
        }

        var translationsSection = document.getElementById('detail-translations-section');
        var translationsList = document.getElementById('detail-translations-list');
        if (isDoc && isOriginal && data.translations && data.translations.length > 0) {
            translationsSection.style.display = '';
            translationsList.innerHTML = '';
            data.translations.forEach(function (t) {
                var item = document.createElement('div');
                item.className = 'detail-modal__translation-item';
                item.innerHTML =
                    '<span class="detail-modal__translation-name">' + escapeHtmlText(t.translated_filename || 'Translation') + '</span>' +
                    '<span class="detail-modal__translation-lang">' + escapeHtmlText(t.source_language || '') + ' → ' + escapeHtmlText(t.target_language || '') + '</span>' +
                    '<span class="detail-modal__translation-date">' + formatDate(t.created_at) + '</span>';
                translationsList.appendChild(item);
            });
        } else {
            translationsSection.style.display = 'none';
        }

        var viewBtn = document.getElementById('detail-action-view');
        viewBtn.onclick = function () {
            fetchJson('/history/redownload/' + encodeURIComponent(data.id), {
                method: 'POST', headers: authHeaders
            })
            .then(function (res) { if (res && res.download_url) window.location.href = res.download_url; })
            .catch(function (err) { if (window.showToast) showToast('error', 'Error', err.message); });
        };

        var originalBtn = document.getElementById('detail-action-original');
        if (isDoc && data.original_storage_path) {
            originalBtn.style.display = '';
            originalBtn.onclick = function () {
                fetchJson('/history/redownload-original/' + encodeURIComponent(data.id), {
                    method: 'POST', headers: authHeaders
                })
                .then(function (res) { if (res && res.download_url) window.location.href = res.download_url; })
                .catch(function (err) { if (window.showToast) showToast('error', 'Error', err.message); });
            };
        } else {
            originalBtn.style.display = 'none';
        }

        var renameBtn = document.getElementById('detail-action-rename');
        renameBtn.onclick = function () {
            var current = isDoc ? (data.translated_filename || data.original_filename || '') : '';
            closeDetail();
            openRename(data.id, current);
        };

        document.getElementById('detail-action-delete').onclick = function () { showDeleteConfirm(data.id); };
    }

    if (detailClose) detailClose.addEventListener('click', closeDetail);
    if (detailOverlay) detailOverlay.addEventListener('click', closeDetail);

    // ══════════════════════════════════════════════════════════════════════
    // Rename modal
    // ══════════════════════════════════════════════════════════════════════
    var renameModal = document.getElementById('rename-modal');
    var renameInput = document.getElementById('rename-input');
    var renameError = document.getElementById('rename-error');

    function openRename(id, filename) {
        if (!renameModal) return;
        currentAction.id = id;
        renameInput.value = filename || '';
        renameError.style.display = 'none';
        openModal(renameModal);
        renameInput.focus();
        renameInput.select();
    }

    function closeRename() { closeModal(renameModal); }

    function saveRename() {
        var name = renameInput.value.trim();
        if (!name) { renameError.textContent = 'Please enter a name.'; renameError.style.display = ''; return; }

        var btn = document.getElementById('rename-save');
        btn.disabled = true;
        btn.textContent = 'Saving…';

        fetch('/history/' + encodeURIComponent(currentAction.id) + '/rename', {
            method: 'POST',
            headers: authHeaders,
            body: JSON.stringify({ name: name })
        })
        .then(function (r) { return r.text().then(function (raw) { return { r: r, raw: raw }; }); })
        .then(function (res) {
            var data = null;
            try { data = JSON.parse(res.raw); } catch (e) {}
            if (!res.r.ok) {
                var msg = (data && (data.error || (data.errors && Object.values(data.errors)[0][0]))) || 'Could not rename the document.';
                renameError.textContent = msg;
                renameError.style.display = '';
                return;
            }
            var newName = (data.record && (data.record.translated_filename || data.record.original_filename)) || name;
            if (window.showToast) showToast('success', 'Renamed', 'Document renamed successfully.');
            closeRename();

            var card = document.querySelector('.doc-card[data-id="' + currentAction.id + '"]');
            if (card) {
                var titleEl = card.querySelector('.doc-card__title');
                if (titleEl) { titleEl.textContent = newName; titleEl.setAttribute('title', newName); }
                card.setAttribute('data-title', newName.toLowerCase());
                var moreBtn = card.querySelector('.doc-card__more');
                if (moreBtn) moreBtn.setAttribute('data-filename', newName);
            }
        })
        .catch(function (err) {
            renameError.textContent = err.message || 'Network error. Please try again.';
            renameError.style.display = '';
        })
        .finally(function () {
            btn.disabled = false;
            btn.textContent = 'Save';
        });
    }

    if (renameModal) {
        document.getElementById('rename-cancel').addEventListener('click', closeRename);
        renameModal.querySelector('.detail-modal__overlay').addEventListener('click', closeRename);
        document.getElementById('rename-save').addEventListener('click', saveRename);
        renameInput.addEventListener('keydown', function (e) { if (e.key === 'Enter') saveRename(); });
    }

    // ══════════════════════════════════════════════════════════════════════
    // Delete confirmation modal
    // ══════════════════════════════════════════════════════════════════════
    var deleteConfirmModal = document.getElementById('delete-confirm');
    var deleteTargetId = null;

    function showDeleteConfirm(id) { deleteTargetId = id; openModal(deleteConfirmModal); }
    function closeDeleteConfirm() { closeModal(deleteConfirmModal); deleteTargetId = null; }

    if (deleteConfirmModal) {
        document.getElementById('delete-confirm-cancel').addEventListener('click', closeDeleteConfirm);
        deleteConfirmModal.querySelector('.detail-modal__overlay').addEventListener('click', closeDeleteConfirm);
        document.getElementById('delete-confirm-ok').addEventListener('click', function () {
            if (!deleteTargetId) return;
            var btn = this;
            btn.disabled = true;
            btn.textContent = 'Deleting…';

            fetchJson('/history/' + encodeURIComponent(deleteTargetId), {
                method: 'DELETE',
                headers: authHeaders
            })
            .then(function () {
                closeDeleteConfirm();
                if (window.showToast) showToast('success', 'Deleted', 'Document has been deleted.');
                var card = document.querySelector('.doc-card[data-id="' + deleteTargetId + '"]');
                if (card) {
                    card.style.transition = 'opacity 0.3s, transform 0.3s';
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';
                    setTimeout(function () { card.remove(); }, 300);
                }
            })
            .catch(function (err) { if (window.showErrorModal) showErrorModal('Delete failed', err.message || 'Failed to delete.'); })
            .finally(function () { btn.disabled = false; btn.textContent = 'Delete'; });
        });
    }

    // Esc closes every modal/dropdown.
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { closeDetail(); closeRename(); closeDeleteConfirm(); closeMoreMenu(); }
    });
})();
</script>
@endsection