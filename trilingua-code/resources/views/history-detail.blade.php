@extends('layouts.app')

@section('title', 'Translation Details')

@section('styles')
    @vite(['resources/css/views/history.css', 'resources/css/views/admin.css'])
@endsection

@section('content')
@php
    $isDoc       = ($record['translation_type'] ?? 'document') === 'document';
    $isOriginal  = empty($record['parent_document_id']);
    $reviewStatus = $record['review_status'] ?? 'pending';
    $status      = $record['status'] ?? 'completed';
    $score       = $record['quality_score'] ?? null;
    $scoreLevel  = $score === null ? '' : ($score < 60 ? 'low' : ($score < 80 ? 'medium' : 'high'));
    $dateStr     = \Carbon\Carbon::parse($record['created_at'])->utc()->format('Y-m-d H:i') . ' UTC';
    $fileSize    = $record['file_size'] ?? null;
    $translatedExt = strtolower((string) pathinfo((string) ($record['translated_filename'] ?? ''), PATHINFO_EXTENSION));
    $originalExt   = strtolower((string) pathinfo((string) ($record['original_filename'] ?? ''), PATHINFO_EXTENSION));
    $translatedUrl = $isDoc && !empty($record['storage_path']) ? route('history.file', $record['id']) : null;
    $originalUrl   = $isDoc && !empty($record['original_storage_path']) ? route('history.original-file', $record['id']) : null;
@endphp

<div class="stack">

    <a href="{{ route('history') }}" class="review-back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
        Back to Saved Translations
    </a>

    <div class="review-detail-card">
        <div class="review-detail__header">
            <div>
                <span class="status-badge status-badge--{{ $reviewStatus }}">{{ ucfirst($reviewStatus) }}</span>
                <h2 class="review-detail__title" style="font-size:1.15rem;font-weight:700;color:var(--text);margin:10px 0 0">
                    {{ $isDoc ? ($record['translated_filename'] ?? $record['original_filename'] ?? 'Document') : 'Text Translation' }}
                </h2>
                @if ($isDoc && !empty($record['original_filename']))
                    <p class="review-detail__subtitle" style="font-size:0.82rem;color:var(--muted);margin:4px 0 0">from: {{ $record['original_filename'] }}</p>
                @endif
            </div>
        </div>

        {{-- ── Two-pane layout ──────────────────────────────────────────── --}}
        <div class="review-split">

            {{-- LEFT: Metadata + actions --}}
            <section class="review-pane review-pane--editable">
                <div class="review-pane__head">
                    <h4 class="review-pane__title">Details</h4>
                </div>
                <div class="review-pane__body">
                    <div class="detail-modal__meta-grid" style="grid-template-columns:1fr;margin-bottom:16px">
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Type</span>
                            <span class="detail-modal__meta-value">
                                <span class="type-badge type-badge--{{ $isDoc ? 'doc' : 'text' }}">{{ $isDoc ? 'Document' : 'Text' }}</span>
                            </span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Source Language</span>
                            <span class="detail-modal__meta-value">{{ $record['source_language'] ?? '—' }}</span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Target Language</span>
                            <span class="detail-modal__meta-value">{{ $record['target_language'] ?? '—' }}</span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Date & Time</span>
                            <span class="detail-modal__meta-value">{{ $dateStr }}</span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Translation Status</span>
                            <span class="detail-modal__meta-value">{{ ucfirst($status) }}</span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Review Status</span>
                            <span class="detail-modal__meta-value">{{ ucfirst($reviewStatus) }}</span>
                        </div>
                        @if ($isDoc)
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">File Size</span>
                            <span class="detail-modal__meta-value">
                                @if ($fileSize)
                                    @if ($fileSize < 1024){{ $fileSize }} B
                                    @elseif ($fileSize < 1048576){{ number_format($fileSize / 1024, 1) }} KB
                                    @else{{ number_format($fileSize / 1048576, 1) }} MB
                                    @endif
                                @else—@endif
                            </span>
                        </div>
                        @endif
                        @if ($score !== null)
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Quality Score</span>
                            <span class="detail-modal__meta-value">
                                <span class="quality-score">
                                    <span class="quality-score__dot quality-score__dot--{{ $scoreLevel }}" aria-hidden="true"></span>
                                    {{ $score }}
                                </span>
                            </span>
                        </div>
                        @endif
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Priority</span>
                            <span class="detail-modal__meta-value">{{ !empty($record['is_priority']) ? 'Requested' : 'Not requested' }}</span>
                        </div>
                        <div class="detail-modal__meta-item">
                            <span class="detail-modal__meta-label">Bookmarked</span>
                            <span class="detail-modal__meta-value">{{ !empty($record['is_bookmarked']) ? 'Yes' : 'No' }}</span>
                        </div>
                    </div>

                    {{-- Action buttons --}}
                    <div class="detail-modal__actions" style="margin-top:0">
                        @if ($isDoc && $translatedUrl)
                            <a class="detail-modal__action-btn detail-modal__action-btn--primary" href="{{ $translatedUrl }}" target="_blank" rel="noopener">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                                Download Translated
                            </a>
                        @endif
                        @if ($isDoc && $originalUrl)
                            <a class="detail-modal__action-btn" href="{{ $originalUrl }}" target="_blank" rel="noopener">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                                Download Original
                            </a>
                        @endif
                        @if (!$isDoc)
                            <button class="detail-modal__action-btn" id="detail-copy-btn" data-text="{{ htmlspecialchars($record['translated_text'] ?? '', ENT_QUOTES) }}">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                                Copy Translation
                            </button>
                        @endif
                        <button class="detail-modal__action-btn {{ !empty($record['is_bookmarked']) ? 'bookmark-btn--active' : '' }}" id="detail-bookmark-btn" data-id="{{ $record['id'] }}">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="{{ !empty($record['is_bookmarked']) ? 'currentColor' : 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
                            {{ !empty($record['is_bookmarked']) ? 'Remove Bookmark' : 'Bookmark' }}
                        </button>
                        @if ($reviewStatus === 'pending')
                        <button class="detail-modal__action-btn {{ !empty($record['is_priority']) ? 'priority-btn--active' : '' }}" id="detail-priority-btn" data-id="{{ $record['id'] }}">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="{{ !empty($record['is_priority']) ? 'currentColor' : 'none' }}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 17v-5"/><path d="M12 7h.01"/><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
                            {{ !empty($record['is_priority']) ? 'Remove Priority' : 'Request Priority Review' }}
                        </button>
                        @endif
                        <button class="detail-modal__action-btn detail-modal__action-btn--danger" id="detail-delete-btn" data-id="{{ $record['id'] }}">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                            Delete
                        </button>
                    </div>
                </div>
            </section>

            {{-- RIGHT: Document / text viewer --}}
            <section class="review-pane review-pane--preview">
                <div class="review-pane__head">
                    <div class="review-pane__title-wrap">
                        <h4 class="review-pane__title">{{ $isDoc ? 'Document' : 'Text' }}</h4>
                    </div>
                    @if ($isDoc)
                    <div class="review-pane__tabs" id="detail-tabs">
                        <button type="button" class="review-pane__tab is-active" data-tab="translated">Translated</button>
                        <button type="button" class="review-pane__tab" data-tab="original">Original</button>
                    </div>
                    @endif
                </div>

                <div class="review-pane__body">
                    @if ($isDoc)
                        <div class="preview-panel" id="detail-panel-translated">
                            @if ($translatedUrl && $translatedExt === 'pdf')
                                <iframe class="review-pane__frame" src="{{ $translatedUrl }}" title="Translated document"></iframe>
                            @elseif ($translatedUrl)
                                <div class="review-pane__placeholder">
                                    <p>Live preview is only available for <strong>PDF</strong> files.</p>
                                    <p>This translated file is a <strong>{{ strtoupper($translatedExt ?: 'document') }}</strong>.</p>
                                    <a class="review-btn" href="{{ $translatedUrl }}" target="_blank" rel="noopener">Download translated document</a>
                                </div>
                            @else
                                <div class="review-pane__placeholder">
                                    <p>Translated file is not available.</p>
                                </div>
                            @endif
                        </div>
                        <div class="preview-panel" id="detail-panel-original" style="display:none">
                            @if ($originalUrl && $originalExt === 'pdf')
                                <iframe class="review-pane__frame" src="{{ $originalUrl }}" title="Original document"></iframe>
                            @elseif ($originalUrl)
                                <div class="review-pane__placeholder">
                                    <p>Live preview is only available for <strong>PDF</strong> files.</p>
                                    <p>This original file is a <strong>{{ strtoupper($originalExt ?: 'document') }}</strong>.</p>
                                    <a class="review-btn" href="{{ $originalUrl }}" target="_blank" rel="noopener">Download original document</a>
                                </div>
                            @else
                                <div class="review-pane__placeholder">
                                    <p>Original file is not available.</p>
                                </div>
                            @endif
                        </div>
                    @else
                        <h4 class="detail-modal__section-title">Original Text</h4>
                        <div class="detail-modal__text-block" style="max-height:none">{{ $record['source_text'] ?? '—' }}</div>
                        <h4 class="detail-modal__section-title">Translated Text</h4>
                        <div class="detail-modal__text-block" style="max-height:none">{{ $record['translated_text'] ?? '—' }}</div>
                    @endif
                </div>
            </section>

        </div>
    </div>
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

    // ── Tab switching (Translated / Original) ──────────────────────────────
    var tabs = document.querySelectorAll('#detail-tabs .review-pane__tab');
    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            tabs.forEach(function (t) { t.classList.remove('is-active'); });
            tab.classList.add('is-active');
            var name = tab.getAttribute('data-tab');
            document.querySelectorAll('.preview-panel').forEach(function (p) {
                p.style.display = (p.id === 'detail-panel-' + name) ? '' : 'none';
            });
        });
    });

    // ── Copy text ──────────────────────────────────────────────────────────
    var copyBtn = document.getElementById('detail-copy-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', function () {
            var text = copyBtn.getAttribute('data-text');
            if (navigator.clipboard && text) {
                navigator.clipboard.writeText(text).then(function () {
                    if (window.showToast) showToast('success', 'Copied!', 'Translation copied to clipboard.');
                });
            }
        });
    }

    // ── Bookmark toggle ────────────────────────────────────────────────────
    var bookmarkBtn = document.getElementById('detail-bookmark-btn');
    if (bookmarkBtn) {
        bookmarkBtn.addEventListener('click', function () {
            var id = bookmarkBtn.getAttribute('data-id');
            fetchJson('/history/' + encodeURIComponent(id) + '/bookmark', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function (data) {
                if (data && data.success) {
                    var svg = bookmarkBtn.querySelector('svg');
                    if (svg) svg.style.fill = data.value ? 'currentColor' : 'none';
                    bookmarkBtn.classList.toggle('bookmark-btn--active', !!data.value);
                    bookmarkBtn.lastChild.textContent = data.value ? ' Remove Bookmark' : ' Bookmark';
                    if (window.showToast) showToast('success', data.value ? 'Bookmarked' : 'Removed', data.value ? 'Translation bookmarked.' : 'Bookmark removed.');
                }
            })
            .catch(function (err) {
                if (window.showToast) showToast('error', 'Error', err.message || 'Failed to update bookmark.');
            });
        });
    }

    // ── Priority toggle ────────────────────────────────────────────────────
    var priorityBtn = document.getElementById('detail-priority-btn');
    if (priorityBtn) {
        priorityBtn.addEventListener('click', function () {
            var id = priorityBtn.getAttribute('data-id');
            fetchJson('/history/' + encodeURIComponent(id) + '/priority', {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
            })
            .then(function (data) {
                if (data && data.success) {
                    var svg = priorityBtn.querySelector('svg');
                    if (svg) svg.style.fill = data.value ? 'currentColor' : 'none';
                    priorityBtn.classList.toggle('priority-btn--active', !!data.value);
                    priorityBtn.lastChild.textContent = data.value ? ' Remove Priority' : ' Request Priority Review';
                    if (window.showToast) showToast('success', data.value ? 'Priority requested' : 'Priority removed', data.value ? 'The admin has been notified to review this translation first.' : 'Priority review request removed.');
                }
            })
            .catch(function (err) {
                if (window.showToast) showToast('error', 'Error', err.message || 'Failed to update priority.');
            });
        });
    }

    // ── Delete confirmation ────────────────────────────────────────────────
    var deleteBtn = document.getElementById('detail-delete-btn');
    var deleteConfirmModal = document.getElementById('delete-confirm');
    var deleteTargetId = null;

    function showDeleteConfirm(id) {
        deleteTargetId = id;
        deleteConfirmModal.style.display = 'flex';
    }
    function closeDeleteConfirm() {
        deleteConfirmModal.style.display = 'none';
        deleteTargetId = null;
    }

    if (deleteBtn) {
        deleteBtn.addEventListener('click', function () {
            showDeleteConfirm(deleteBtn.getAttribute('data-id'));
        });
    }

    document.getElementById('delete-confirm-cancel').addEventListener('click', closeDeleteConfirm);
    deleteConfirmModal.querySelector('.detail-modal__overlay').addEventListener('click', closeDeleteConfirm);

    document.getElementById('delete-confirm-ok').addEventListener('click', function () {
        if (!deleteTargetId) return;
        var btn = this;
        btn.disabled = true;
        btn.textContent = 'Deleting…';

        fetchJson('/history/' + encodeURIComponent(deleteTargetId), {
            method: 'DELETE',
            headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json', 'Content-Type': 'application/json' }
        })
        .then(function () {
            closeDeleteConfirm();
            if (window.showToast) showToast('success', 'Deleted', 'Translation has been deleted.');
            window.location.href = '{{ route('history') }}';
        })
        .catch(function (err) {
            if (window.showErrorModal) showErrorModal('Delete failed', err.message || 'Failed to delete.');
        })
        .finally(function () {
            btn.disabled = false;
            btn.textContent = 'Delete';
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeDeleteConfirm();
    });
})();
</script>
@endsection