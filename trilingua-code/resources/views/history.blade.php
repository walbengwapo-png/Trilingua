@extends('layouts.app')

@section('title', 'Translation History')

@section('styles')
    @vite(['resources/css/views/history.css', 'resources/css/views/admin.css'])

    {{-- Inline modal styles (ensures they work without Vite recompilation) --}}
    <style>
    /* ════════════════════════════════════════════════════════════════════════
       Translation Details Modal — Inline Styles
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
    .detail-modal__info-row{display:flex;align-items:center;gap:8px;padding:6px 0;font-size:.85rem}
    .detail-modal__info-icon{flex-shrink:0;color:var(--muted,#6b7280)}
    .detail-modal__info-label{color:var(--muted,#6b7280);min-width:100px}
    .detail-modal__info-value{color:var(--text,#111827);font-weight:500}
    @media(max-width:640px){.detail-modal__dialog{padding:24px 20px;max-height:90vh}.detail-modal__meta-grid{grid-template-columns:1fr}.detail-modal__actions{flex-direction:column}.detail-modal__action-btn{justify-content:center}.detail-modal__translation-item{flex-wrap:wrap}}
    </style>
@endsection

@section('content')
<div class="stack">

    @if ($error)
        <p class="error-message">Unable to load history. Please try again later.</p>
    @else

    {{-- Page header --}}
    <div class="history-page-header">
        <div class="history-page-header__title">
            <h2>Saved Translations <span class="count-badge">{{ count($records) }}</span></h2>
        </div>
        <div class="history-page-header__controls">
            <a href="{{ route('bookmarks') }}" class="history-select history-bookmarks-btn" title="View bookmarked translations">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                Bookmarks
            </a>
            <input type="search" id="history-search" class="history-search" placeholder="Search translations…" aria-label="Search translations">
            <select id="history-group" class="history-select" aria-label="Group by">
                <option value="language">Group by Language Pair</option>
                <option value="none">No Grouping</option>
            </select>
            <select id="history-status" class="history-select" aria-label="Filter by status">
                <option value="">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="verified">Verified</option>
                <option value="edited">Edited</option>
                <option value="flagged">Flagged</option>
            </select>
            <select id="history-sort" class="history-select" aria-label="Sort order">
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="lang-az">Language A–Z</option>
            </select>
        </div>
    </div>

    @if (empty($records))
        <p class="empty-state">You have no translation history yet.</p>
    @else

    @php
        // Group records by language pair
        $grouped = [];
        foreach ($records as $r) {
            $key = ($r['source_language'] ?? '?') . ' → ' . ($r['target_language'] ?? '?');
            $grouped[$key][] = $r;
        }
    @endphp

    {{-- Grouped card sections --}}
    <div id="history-content">
        @foreach ($grouped as $langPair => $groupRecords)
        <section class="history-group" data-lang-pair="{{ $langPair }}">
            <h3 class="history-group__title">
                {{ $langPair }}
                <span class="count-badge">{{ count($groupRecords) }}</span>
            </h3>
            <div class="history-cards">
                @foreach ($groupRecords as $record)
                @php
                    $isDoc    = ($record['translation_type'] ?? 'document') === 'document';
                    $matchPct = $isDoc
                        ? 100
                        : min(100, (int)(
                            mb_strlen($record['translated_text'] ?? '')
                            / max(1, mb_strlen($record['source_text'] ?? ''))
                            * 100
                          ));
                    $preview  = $isDoc
                        ? ($record['original_filename'] ?? 'Document')
                        : \Illuminate\Support\Str::limit($record['source_text'] ?? '', 80);
                    $dateStr  = \Carbon\Carbon::parse($record['created_at'])->utc()->format('Y-m-d H:i') . ' UTC';
                @endphp
                @php
                    $reviewStatus = $record['review_status'] ?? 'pending';
                @endphp
                <div class="history-card"
                     data-search="{{ strtolower($preview . ' ' . ($record['source_language'] ?? '') . ' ' . ($record['target_language'] ?? '') . ' ' . $reviewStatus) }}"
                     data-date="{{ $record['created_at'] ?? '' }}"
                     data-lang="{{ $langPair }}"
                     data-review-status="{{ $reviewStatus }}"
                     data-id="{{ $record['id'] }}">

                    <div class="history-card__header">
                        <span class="match-badge">{{ $matchPct }}%</span>
                        <span class="type-badge type-badge--{{ $isDoc ? 'doc' : 'text' }}">
                            {{ $isDoc ? 'Document' : 'Text' }}
                        </span>
                        <span class="status-badge status-badge--{{ $reviewStatus }}">{{ ucfirst($reviewStatus) }}</span>
                        @if (!empty($record['quality_score']))
                            @php
                                $score = (int) $record['quality_score'];
                                $scoreClass = $score >= 80 ? 'high' : ($score >= 50 ? 'medium' : 'low');
                            @endphp
                            <span class="quality-score" title="Quality score: {{ $score }}/100">
                                <span class="quality-score__dot quality-score__dot--{{ $scoreClass }}"></span>
                                {{ $score }}
                            </span>
                        @endif
                    </div>

                    <div class="history-card__body">
                        <p class="history-card__preview" title="{{ $preview }}">{{ $preview }}</p>
                        @if ($isDoc)
                            <p class="history-card__sub">→ {{ $record['translated_filename'] ?? '' }}</p>
                        @endif
                    </div>

                    <div class="history-card__footer">
                        <span class="history-card__date">{{ $dateStr }}</span>
                        <div class="history-card__actions">
                            {{-- View Details button (opens modal) --}}
                            <button class="history-card__action-btn view-details-btn"
                                    title="View details"
                                    data-id="{{ $record['id'] }}"
                                    aria-label="View translation details">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                            </button>

                            {{-- Copy button (text records) --}}
                            @if (!$isDoc)
                            <button class="history-card__action-btn copy-text-btn"
                                    title="Copy translation"
                                    data-text="{{ htmlspecialchars($record['translated_text'] ?? '', ENT_QUOTES) }}"
                                    aria-label="Copy translation">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                            </button>
                            @endif

                            {{-- Download button --}}
                            @if ($isDoc)
                            <button class="history-card__action-btn redownload-btn"
                                    title="Re-download"
                                    data-id="{{ $record['id'] }}"
                                    data-filename="{{ $record['translated_filename'] ?? '' }}"
                                    aria-label="Re-download document">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            </button>
                            @else
                            <button class="history-card__action-btn download-text-btn"
                                    title="Save as text"
                                    data-text="{{ htmlspecialchars($record['translated_text'] ?? '', ENT_QUOTES) }}"
                                    data-filename="translation-{{ $record['id'] ?? 'export' }}.txt"
                                    aria-label="Save translation as text file">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            </button>
                            @endif

                            {{-- Bookmark button --}}
                            <button class="history-card__action-btn bookmark-btn {{ !empty($record['is_bookmarked']) ? 'bookmark-btn--active' : '' }}"
                                    title="{{ !empty($record['is_bookmarked']) ? 'Remove bookmark' : 'Bookmark' }}"
                                    data-id="{{ $record['id'] }}"
                                    aria-label="Bookmark translation">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="{{ !empty($record['is_bookmarked']) ? 'currentColor' : 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                            </button>

                            {{-- Priority button (pending review records only) --}}
                            @if (($record['review_status'] ?? 'pending') === 'pending')
                            <button class="history-card__action-btn priority-btn {{ !empty($record['is_priority']) ? 'priority-btn--active' : '' }}"
                                    title="{{ !empty($record['is_priority']) ? 'Remove priority request' : 'Request priority review' }}"
                                    data-id="{{ $record['id'] }}"
                                    aria-label="Request priority review">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="{{ !empty($record['is_priority']) ? 'currentColor' : 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 17v-5"/><path d="M12 7h.01"/><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
                            </button>
                            @endif
                        </div>
                    </div>
                </div>
                @endforeach
            </div>
        </section>
        @endforeach
    </div>

    @endif {{-- empty($records) --}}
    @endif {{-- $error --}}

    <div id="redownload-error" class="error-message" style="display:none"></div>

</div>

{{-- Delete confirmation dialog --}}
<div id="delete-confirm" class="detail-modal" style="display:none">
    <div class="detail-modal__overlay"></div>
    <div class="detail-modal__dialog detail-modal__dialog--small" role="alertdialog" aria-modal="true" aria-labelledby="delete-confirm-title">
        <h3 id="delete-confirm-title" class="detail-modal__title">Delete Translation?</h3>
        <p class="detail-modal__confirm-text">This will permanently delete this translation and all associated files. This action cannot be undone.</p>
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

    // ── Helper: fetch JSON ──────────────────────────────────────────────────
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

    // ── Re-download ──────────────────────────────────────────────────────────
    var errorEl = document.getElementById('redownload-error');

    function showError(message) { errorEl.textContent = message; errorEl.style.display = ''; }
    function clearError()       { errorEl.textContent = ''; errorEl.style.display = 'none'; }

    document.querySelectorAll('.redownload-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            clearError();
            var id = btn.getAttribute('data-id');

            btn.disabled    = true;
            var orig        = btn.innerHTML;
            btn.textContent = 'Loading…';

            fetchJson('/history/redownload/' + encodeURIComponent(id), {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function (data) {
                if (data && data.download_url) {
                    window.location.href = data.download_url;
                    if (window.showToast) showToast('success', 'Download started', 'Your file is downloading.');
                } else {
                    if (window.showErrorModal) showErrorModal('Download failed', 'Unable to generate download link. Please try again later.');
                }
            })
            .catch(function (err) { if (window.showErrorModal) showErrorModal('Download failed', err.message || 'Network error. Please try again.'); })
            .finally(function () { btn.disabled = false; btn.innerHTML = orig; });
        });
    });

    // ── Copy text ────────────────────────────────────────────────────────────
    document.querySelectorAll('.copy-text-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var text = btn.getAttribute('data-text');
            if (navigator.clipboard && text) {
                navigator.clipboard.writeText(text).then(function () {
                    if (window.showToast) showToast('success', 'Copied!', 'Translation copied to clipboard.');
                }).catch(function () {
                    if (window.showToast) showToast('error', 'Copy failed', 'Could not copy to clipboard.');
                });
            }
        });
    });

    // ── Download as .txt ─────────────────────────────────────────────────────
    document.querySelectorAll('.download-text-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var text     = btn.getAttribute('data-text') || '';
            var filename = btn.getAttribute('data-filename') || 'translation.txt';
            var blob     = new Blob([text], { type: 'text/plain' });
            var url      = URL.createObjectURL(blob);
            var a        = document.createElement('a');
            a.href = url; a.download = filename; a.click();
            URL.revokeObjectURL(url);
            if (window.showToast) showToast('success', 'File saved', filename + ' downloaded.');
        });
    });

    // ── Bookmark (persisted) ────────────────────────────────────────────────
    function setBookmarkVisual(btn, active) {
        btn.classList.toggle('bookmark-btn--active', active);
        var svg = btn.querySelector('svg');
        if (svg) svg.style.fill = active ? 'currentColor' : 'none';
        btn.title = active ? 'Remove bookmark' : 'Bookmark';
    }

    document.querySelectorAll('.bookmark-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = btn.getAttribute('data-id');
            if (!id) return;

            fetchJson('/history/' + encodeURIComponent(id) + '/bookmark', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function (data) {
                if (data && data.success) {
                    setBookmarkVisual(btn, !!data.value);
                    if (window.showToast) showToast('success', data.value ? 'Bookmarked' : 'Removed', data.value ? 'Translation bookmarked.' : 'Bookmark removed.');
                }
            })
            .catch(function (err) {
                if (window.showToast) showToast('error', 'Error', err.message || 'Failed to update bookmark.');
            });
        });
    });

    // ── Priority (request priority review, persisted) ─────────────────────
    function setPriorityVisual(btn, active) {
        btn.classList.toggle('priority-btn--active', active);
        var svg = btn.querySelector('svg');
        if (svg) svg.style.fill = active ? 'currentColor' : 'none';
        btn.title = active ? 'Remove priority request' : 'Request priority review';
    }

    document.querySelectorAll('.priority-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = btn.getAttribute('data-id');
            if (!id) return;

            fetchJson('/history/' + encodeURIComponent(id) + '/priority', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function (data) {
                if (data && data.success) {
                    setPriorityVisual(btn, !!data.value);
                    if (window.showToast) showToast('success', data.value ? 'Priority requested' : 'Priority removed', data.value ? 'The admin has been notified to review this translation first.' : 'Priority review request removed.');
                }
            })
            .catch(function (err) {
                if (window.showToast) showToast('error', 'Error', err.message || 'Failed to update priority.');
            });
        });
    });

    // ── View details button click — navigate to the dedicated detail page ──
    document.querySelectorAll('.view-details-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = btn.getAttribute('data-id');
            window.location.href = '/history/' + encodeURIComponent(id) + '/view';
        });
    });

    // ══════════════════════════════════════════════════════════════════════════
    // Delete Confirmation
    // ══════════════════════════════════════════════════════════════════════════
    var deleteConfirmModal = document.getElementById('delete-confirm');
    var deleteConfirmOverlay = deleteConfirmModal.querySelector('.detail-modal__overlay');
    var deleteConfirmCancel = document.getElementById('delete-confirm-cancel');
    var deleteConfirmOk = document.getElementById('delete-confirm-ok');
    var deleteTargetId = null;

    function showDeleteConfirm(id) {
        deleteTargetId = id;
        deleteConfirmModal.style.display = 'flex';
    }

    function closeDeleteConfirm() {
        deleteConfirmModal.style.display = 'none';
        deleteTargetId = null;
    }

    if (deleteConfirmCancel) deleteConfirmCancel.addEventListener('click', closeDeleteConfirm);
    if (deleteConfirmOverlay) deleteConfirmOverlay.addEventListener('click', closeDeleteConfirm);

    if (deleteConfirmOk) {
        deleteConfirmOk.addEventListener('click', function () {
            if (!deleteTargetId) return;
            deleteConfirmOk.disabled = true;
            deleteConfirmOk.textContent = 'Deleting…';

            fetchJson('/history/' + encodeURIComponent(deleteTargetId), {
                method: 'DELETE',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function () {
                closeDeleteConfirm();
                if (window.showToast) showToast('success', 'Deleted', 'Translation has been deleted.');
                // Remove the card from the page
                var card = document.querySelector('.history-card[data-id="' + deleteTargetId + '"]');
                if (card) {
                    card.style.transition = 'opacity 0.3s, transform 0.3s';
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.95)';
                    setTimeout(function () { card.remove(); }, 300);
                }
            })
            .catch(function (err) {
                if (window.showErrorModal) showErrorModal('Delete failed', err.message || 'Failed to delete.');
            })
            .finally(function () {
                deleteConfirmOk.disabled = false;
                deleteConfirmOk.textContent = 'Delete';
            });
        });
    }

    // ── Client-side search, group-by, status filter, and sort ──────────────
    var searchInput  = document.getElementById('history-search');
    var groupSelect  = document.getElementById('history-group');
    var statusSelect = document.getElementById('history-status');
    var sortSelect   = document.getElementById('history-sort');
    var contentEl    = document.getElementById('history-content');

    if (!contentEl) return; // no records — nothing to filter

    // Collect all cards and groups for manipulation
    function getAllCards() {
        return Array.from(contentEl.querySelectorAll('.history-card'));
    }

    function getAllGroups() {
        return Array.from(contentEl.querySelectorAll('.history-group'));
    }

    // Apply search filter: hide cards whose data-search doesn't match query
    function applySearch(query) {
        var q = query.trim().toLowerCase();
        var s = (statusSelect ? statusSelect.value : '').toLowerCase();
        getAllCards().forEach(function (card) {
            var haystack = (card.getAttribute('data-search') || '').toLowerCase();
            var status = (card.getAttribute('data-review-status') || 'pending').toLowerCase();
            var visible = true;
            if (q && haystack.indexOf(q) === -1) visible = false;
            if (s && status !== s) visible = false;
            card.style.display = visible ? '' : 'none';
        });
        // Hide groups that have no visible cards
        getAllGroups().forEach(function (group) {
            var visibleCards = group.querySelectorAll('.history-card:not([style*="display: none"])');
            group.style.display = visibleCards.length > 0 ? '' : 'none';
        });
    }

    // Apply group-by toggle: when "none", flatten all cards into a single pseudo-group
    function applyGroupBy(mode) {
        var groups = getAllGroups();
        if (mode === 'none') {
            // Show all group headings hidden, merge visually by hiding h3
            groups.forEach(function (g) {
                var heading = g.querySelector('.history-group__title');
                if (heading) heading.style.display = 'none';
            });
        } else {
            groups.forEach(function (g) {
                var heading = g.querySelector('.history-group__title');
                if (heading) heading.style.display = '';
            });
        }
    }

    // Apply sort: reorder cards within each group (or across all if no grouping)
    function applySort(order) {
        getAllGroups().forEach(function (group) {
            var grid  = group.querySelector('.history-cards');
            if (!grid) return;
            var cards = Array.from(grid.querySelectorAll('.history-card'));

            cards.sort(function (a, b) {
                if (order === 'newest' || order === 'oldest') {
                    var da = new Date(a.getAttribute('data-date') || 0);
                    var db = new Date(b.getAttribute('data-date') || 0);
                    return order === 'newest' ? db - da : da - db;
                } else if (order === 'lang-az') {
                    var la = (a.getAttribute('data-lang') || '').toLowerCase();
                    var lb = (b.getAttribute('data-lang') || '').toLowerCase();
                    return la < lb ? -1 : la > lb ? 1 : 0;
                }
                return 0;
            });

            cards.forEach(function (card) { grid.appendChild(card); });
        });
    }

    function applyAll() {
        applySearch(searchInput ? searchInput.value : '');
        applyGroupBy(groupSelect ? groupSelect.value : 'language');
        applySort(sortSelect ? sortSelect.value : 'newest');
    }

    if (searchInput) searchInput.addEventListener('input', applyAll);
    if (groupSelect) groupSelect.addEventListener('change', applyAll);
    if (statusSelect) statusSelect.addEventListener('change', applyAll);
    if (sortSelect)  sortSelect.addEventListener('change', applyAll);

    // Initial sort (newest first by default)
    applyAll();

    // ── Auto-open detail page from ?open={id} (notification deep link) ──
    var openId = @json($openId ?? null);
    if (openId) {
        window.location.href = '/history/' + encodeURIComponent(openId) + '/view';
    }

})();
</script>
@endsection