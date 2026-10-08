@extends('layouts.app')

@section('title', 'Review Document Translation')

@section('styles')
    @vite(['resources/css/views/admin.css', 'resources/js/document-preview.js', 'resources/js/review-document.js'])
@endsection

@section('content')
@php
    $hasDraft = $record->hasUnpublishedEdits();
@endphp
<div class="stack">

    <a href="{{ route('admin.review.index') }}" class="review-back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
        Back to review queue
    </a>

    <div class="review-detail-card">
        <div class="review-detail__header">
            <div>
                <span class="status-badge status-badge--{{ $record->review_status }}">{{ ucfirst($record->review_status) }}</span>
                @if ($hasDraft)
                    <span class="status-badge status-badge--edited">Unpublished edits</span>
                @elseif ($record->review_status === 'edited')
                    <span class="status-badge status-badge--edited">Published</span>
                @endif
                <h2 class="review-detail__title" style="font-size:1.15rem;font-weight:700;color:var(--text);margin:10px 0 0">{{ $record->original_filename ?? 'Document Translation' }}</h2>
                @if ($record->translated_filename)
                    <p class="review-detail__subtitle" style="font-size:0.82rem;color:var(--muted);margin:4px 0 0">translated to → {{ $record->translated_filename }}</p>
                @endif
            </div>
        </div>

        {{-- Metadata --}}
        <div class="review-detail__meta">
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Source Language</span>
                <span class="review-detail__meta-value">{{ $record->source_language ?? '—' }}</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Target Language</span>
                <span class="review-detail__meta-value">{{ $record->target_language ?? '—' }}</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">AI Review Signal</span>
                <span class="review-detail__meta-value" title="Automated AI review signal — not human-verified accuracy.">({{ $record->quality_score === null ? 'Unavailable' : $record->quality_score }})</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Submitted By</span>
                <span class="review-detail__meta-value">{{ $record->user->name ?? 'Unknown' }} ({{ $record->user->email ?? '—' }})</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Submitted At</span>
                <span class="review-detail__meta-value">{{ \Carbon\Carbon::parse($record->created_at)->utc()->format('Y-m-d H:i') }} UTC</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Blocks</span>
                <span class="review-detail__meta-value">{{ $totalBlocks }}</span>
            </div>
        </div>

        {{-- Document-level actions --}}
        <div class="review-form-card">
            <h4 class="review-form-card__title">Document Actions</h4>

            <p class="review-form-note" id="unsaved-count" style="display:none;margin:0 0 10px"></p>

            <div class="block-card__actions" style="border-top:none;padding-top:0;margin-top:0">
                @if ($hasDraft)
                    <p class="review-form-note" id="draft-warning" style="margin:0 0 10px;color:var(--warning,#b45309)">
                        Edits are saved as a <strong>draft</strong>. The downloadable file still shows the last published
                        version. Run <strong>Save &amp; Regenerate</strong> to publish them; Verify is disabled until then.
                    </p>
                @endif
                <form method="POST" action="{{ route('admin.review.document.verify', $record->id) }}" class="review-inline-form"
                      data-review-form data-reload="true" data-confirm-dirty="true">
                    @csrf
                    <button type="submit" class="review-btn review-btn--success">Verify Document</button>
                </form>

                <form method="POST" action="{{ route('admin.review.document.flag', $record->id) }}" class="review-inline-form"
                      data-review-form data-reload="true" data-confirm-dirty="true">
                    @csrf
                    <select name="reason" class="review-select" required aria-label="Flag reason">
                        <option value="">Flag…</option>
                        @foreach (\App\Support\FlagReason::ALL as $reason)
                            <option value="{{ $reason }}" @selected($record->flag_reason === $reason)>{{ ucwords(str_replace('_', ' ', $reason)) }}</option>
                        @endforeach
                    </select>
                    <button type="submit" class="review-btn review-btn--danger">Flag Document</button>
                </form>
            </div>

            <form method="POST" action="{{ route('admin.review.save-regenerate', $record->id) }}" class="review-form-card" style="margin-top:14px"
                  id="save-regenerate-form" data-regen-form>
                <input type="hidden" name="expected_draft_revision" value="{{ $record->draft_revision }}">
                <input type="hidden" name="expected_storage_path" value="{{ $record->storage_path }}">
                @csrf
                <p class="review-form-note" style="margin:0 0 8px">
                    Collects every edited block, re-renders the document (reconstruction only — AI translation is never
                    re-run), uploads the new version, and makes it the downloadable one. Until this succeeds, edits stay
                    a draft and the previous file remains downloadable.
                </p>
                <input type="text" name="note" class="review-input" placeholder="Optional audit note" style="width:100%;margin-bottom:8px">
                <button type="submit" class="review-btn review-btn--warning" id="regen-btn">Save &amp; Regenerate</button>
                <span class="review-form-note" id="regen-spinner" style="display:none">Regenerating… this can take a minute.</span>
            </form>

            <div id="regen-result"></div>
        </div>

        {{-- ── Two-pane review layout ──────────────────────────────────── --}}
        <div class="review-split">

            {{-- LEFT: Translated Document (reference) --}}
            <section class="review-pane review-pane--preview">
                <div class="review-pane__head">
                    <div class="review-pane__title-wrap">
                        <h4 class="review-pane__title">Translated Document</h4>
                        @if ($previewUrl)
                            <a class="review-pane__download" href="{{ $previewUrl }}" target="_blank" rel="noopener">Download</a>
                        @endif
                    </div>
                    <div class="review-pane__tabs" id="preview-tabs" role="tablist" aria-label="Document preview">
                        <button type="button" class="review-pane__tab is-active" data-tab="final" id="tab-final" role="tab" aria-selected="true" aria-controls="preview-final" tabindex="0">Final</button>
                        <button type="button" class="review-pane__tab" data-tab="draft" id="tab-draft" role="tab" aria-selected="false" aria-controls="preview-draft" tabindex="-1">Page preview</button>
                    </div>
                </div>

                <div class="review-pane__body">
                    <div class="preview-panel" id="preview-final" role="tabpanel" aria-labelledby="tab-final">
                        @if ($previewUrl && $isPdf)
                            <iframe class="review-pane__frame" src="{{ $previewUrl }}" title="Translated document"></iframe>
                        @elseif ($previewUrl)
                            <div id="converter-host"
                                 data-ext="{{ $previewExt }}"
                                 data-blocks-mode="published"
                                 data-file-url="{{ route('admin.review.document.file', $record->id) }}"
                                 data-blocks-url="{{ route('admin.review.blocks', $record->id) }}">
                                <div class="review-pane__loading">Loading preview…</div>
                            </div>
                        @else
                            <div class="review-pane__placeholder">
                                @if ($record->storage_path)
                                    <p class="review-form-note">Preview URL could not be generated.</p>
                                @else
                                    <p>Translated file is not available.</p>
                                @endif
                            </div>
                        @endif
                    </div>
                    <div class="preview-panel" id="preview-draft" style="display:none" role="tabpanel" aria-labelledby="tab-draft">
                        @php
                            $previewFirst = $blocks->firstItem();
                            $previewLast = $blocks->lastItem();
                        @endphp
                        <div class="preview-draft__note">
                            <strong>Current page draft preview</strong> — blocks {{ $previewFirst ?? 0 }}{{ $previewLast ? '–' . $previewLast : '' }} of {{ $totalBlocks }} (page {{ $blocks->currentPage() }} of {{ $blocks->lastPage() }}).
                            This mirrors only the blocks on the editable page you are viewing — not the whole document. Your unsaved edits show in blue; the downloadable file shows under <strong>Final</strong>.
                            @if ($blocksFilter !== [] && array_filter($blocksFilter) !== [])
                                <span class="review-form-note">Filters are active, so the preview mirrors only the matching blocks.</span>
                            @endif
                        </div>
                        <div class="preview-draft__doc" id="draft-doc"></div>
                    </div>
                </div>
            </section>

            {{-- RIGHT: Editable Document --}}
            <section class="review-pane review-pane--editable">
                <div class="review-pane__head">
                    <h4 class="review-pane__title">
                        Editable Document
                        <span class="count-badge">{{ $totalBlocks }}</span>
                    </h4>
                </div>

                <div class="review-pane__body">
                    {{-- Block filters --}}
                    <form method="GET" action="{{ route('admin.review.show', $record->id) }}" class="review-filters block-filters">
                        <div class="review-filters__field">
                            <label class="review-filters__label" for="b-status">Status</label>
                            <select name="status" id="b-status" class="review-select">
                                <option value="">All statuses</option>
                                @foreach (\App\Support\ReviewStatus::ALL as $s)
                                    <option value="{{ $s }}" @selected(($blocksFilter['status'] ?? '') === $s)>{{ ucfirst($s) }}</option>
                                @endforeach
                            </select>
                        </div>

                        <div class="review-filters__field">
                            <label class="review-filters__label" for="b-score">Score ≥</label>
                            <input type="number" name="score_min" id="b-score" class="review-input" min="0" max="100"
                                   value="{{ $blocksFilter['score_min'] ?? '' }}" placeholder="Any">
                        </div>

                        <div class="review-filters__field review-filters__field--grow">
                            <label class="review-filters__label" for="b-search">Search</label>
                            <input type="search" name="search" id="b-search" class="review-input" style="width:100%"
                                   value="{{ $blocksFilter['search'] ?? '' }}" placeholder="Source or translation…">
                        </div>

                        <div class="review-filters__field">
                            <label class="review-filters__label" for="b-sort">Sort</label>
                            <select name="sort" id="b-sort" class="review-select">
                                <option value="score" @selected(($blocksFilter['sort'] ?? 'score') === 'score')>Score (worst first)</option>
                                <option value="index" @selected(($blocksFilter['sort'] ?? '') === 'index')>Block order</option>
                                <option value="status" @selected(($blocksFilter['sort'] ?? '') === 'status')>Status</option>
                            </select>
                        </div>

                        <div class="review-filters__actions">
                            <button type="submit" class="review-btn review-btn--primary">Filter</button>
                            <a href="{{ route('admin.review.show', $record->id) }}" class="review-btn">Clear</a>
                        </div>
                    </form>

                    @if ($blocks->isEmpty())
                        <p class="empty-state">No blocks match the current filters.</p>
                    @else
                        <p class="block-filters__summary">
                            Showing {{ $blocks->count() }} of {{ $totalBlocks }} blocks
                        </p>
                        <div class="doc-block-list">
                            @foreach ($blocks as $block)
                            @php
                                $different = isset($block->current_text) && $block->current_text !== $block->ai_translated_text;
                                $score     = $block->quality_score;
                                $level     = $score === null ? '' : ($score < 60 ? 'low' : ($score < 80 ? 'medium' : 'high'));
                            @endphp
                            <div class="doc-block" data-block-id="{{ $block->id }}" data-block-index="{{ $block->block_index }}">
                                <div class="doc-block__head">
                                    <div class="block-card__badges">
                                        <span class="block-card__index">Block #{{ $block->block_index }}</span>
                                        <span class="block-card__type">{{ $block->block_type ?? 'block' }}</span>
                                        <span class="status-badge status-badge--{{ $block->status }}">{{ ucfirst($block->status) }}</span>
                                        @if ($different)
                                            <span class="status-badge status-badge--edited">{{ $hasDraft ? 'Draft edit' : 'Edited' }}</span>
                                        @endif
                                    </div>
                                    <span class="quality-score" style="min-width:0" title="Automated AI review signal (not human-verified)">
                                        <span class="quality-score__dot quality-score__dot--{{ $level }}" aria-hidden="true"></span>
                                        {{ $score === null ? 'Unavailable' : $score }}
                                    </span>
                                </div>

                                <label class="visually-hidden" for="block-editor-{{ $block->id }}">
                                    Block #{{ $block->block_index }} ({{ $block->block_type ?? 'block' }}) — review translation text
                                </label>
                                <textarea id="block-editor-{{ $block->id }}" class="doc-block__editor" name="current_text" data-block-current
                                          data-saved="{{ htmlspecialchars($block->current_text ?? '', ENT_QUOTES) }}">{{ $block->current_text ?? '' }}</textarea>

                                <details class="doc-block__ref">
                                    <summary>Source &amp; AI reference</summary>
                                    <div class="doc-block__ref-content">
                                        <div class="block-card__pair">
                                            <span class="block-card__pair-label">Source</span>
                                            <div class="block-card__text">{{ $block->source_text ?? '—' }}</div>
                                        </div>
                                        <div class="block-card__pair">
                                            <span class="block-card__pair-label">AI Translation (immutable)</span>
                                            <div class="block-card__text block-card__text--highlight">{{ $block->ai_translated_text ?? '—' }}</div>
                                        </div>
                                    </div>
                                </details>

                                <div class="block-card__actions">
                                    <form method="POST" action="{{ route('admin.review.block.update', [$record->id, $block->id]) }}"
                                          class="review-inline-form" data-review-form data-inplace="true">
                                        @csrf
                                        <input type="hidden" name="expected_draft_revision" value="{{ $record->draft_revision }}">
                                    <input type="hidden" name="current_text" value="{{ htmlspecialchars($block->current_text ?? '', ENT_QUOTES) }}">
                                        <button type="submit" class="review-btn review-btn--warning">Save Edit</button>
                                    </form>
                                </div>
                            </div>
                            @endforeach
                        </div>

                        {{-- Pagination (manual prev/next so it inherits app styling) --}}
                        @if ($blocks->hasPages())
                        <div class="review-pagination">
                            <div class="review-pagination__controls">
                                @if ($blocks->onFirstPage())
                                    <span class="review-btn review-btn--disabled">Prev</span>
                                @else
                                    <a href="{{ $blocks->previousPageUrl() }}" class="review-btn">Prev</a>
                                @endif
                                <span class="review-pagination__info">Page {{ $blocks->currentPage() }} of {{ $blocks->lastPage() }}</span>
                                @if ($blocks->hasMorePages())
                                    <a href="{{ $blocks->nextPageUrl() }}" class="review-btn">Next</a>
                                @else
                                    <span class="review-btn review-btn--disabled">Next</span>
                                @endif
                            </div>
                        </div>
                        @endif
                    @endif
                </div>
            </section>
        </div>
    </div>

</div>

<script>
(function () {
    'use strict';
    var csrfToken = document.querySelector('meta[name="csrf-token"]').content;

    var suppressLeavePrompt = false;

    // Keep each block's hidden current_text input in sync with its textarea so
    // "Save Edit" posts the latest value, and keep the unsaved-edit counter live.
    document.querySelectorAll('.doc-block').forEach(function (card) {
        var textarea = card.querySelector('textarea[data-block-current]');
        var hidden = card.querySelector('input[name="current_text"]');
        if (textarea && hidden) {
            textarea.addEventListener('input', function () {
                hidden.value = textarea.value;
                updateUnsavedCount();
            });
        }
    });

    function hasUnsavedEdits() {
        var list = document.querySelectorAll('textarea[data-block-current]');
        for (var i = 0; i < list.length; i++) {
            if (list[i].value !== (list[i].getAttribute('data-saved') || '')) return true;
        }
        return false;
    }

    function updateUnsavedCount() {
        var el = document.getElementById('unsaved-count');
        if (!el) return;
        var count = 0;
        document.querySelectorAll('textarea[data-block-current]').forEach(function (ta) {
            if (ta.value !== (ta.getAttribute('data-saved') || '')) count++;
        });
        if (count > 0) {
            el.style.display = '';
            el.textContent = count + ' unsaved block edit' + (count === 1 ? '' : 's') +
                ' — Save & Regenerate will include them.';
        } else {
            el.style.display = 'none';
        }
    }

    // Reflect a successful in-place "Save Edit": mark the textarea as saved and
    // update the status / Edited badges without a full page reload.
    function applyBlockSaved(card) {
        var textarea = card.querySelector('textarea[data-block-current]');
        if (!textarea) return;
        textarea.setAttribute('data-saved', textarea.value);

        var aiEl = card.querySelector('.block-card__text--highlight');
        var aiText = aiEl ? (aiEl.textContent || '') : '';
        var different = textarea.value !== aiText;

        var badges = card.querySelectorAll('.block-card__badges .status-badge');
        if (badges.length) {
            badges[0].className = 'status-badge status-badge--edited';
            badges[0].textContent = 'Edited';
        }

        var editedBadge = null;
        for (var i = 1; i < badges.length; i++) {
            if (badges[i].textContent.trim() === 'Edited') { editedBadge = badges[i]; break; }
        }
        if (different && !editedBadge && badges.length) {
            var b = document.createElement('span');
            b.className = 'status-badge status-badge--edited';
            b.textContent = 'Edited';
            badges[0].parentNode.insertBefore(b, badges[0].nextSibling);
        } else if (!different && editedBadge) {
            editedBadge.parentNode.removeChild(editedBadge);
        }
    }

    window.addEventListener('beforeunload', function (e) {
        if (suppressLeavePrompt) return;
        if (hasUnsavedEdits()) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    function postForm(form) {
        var btn = form.querySelector('button[type="submit"]');
        var label = btn.textContent.trim();
        btn.disabled = true;
        btn.textContent = 'Working…';

        var body = new FormData(form);
        return fetch(form.action, {
            method: 'POST',
            headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json' },
            body: body
        })
        .then(function (r) { return r.text().then(function (raw) { return { r: r, raw: raw }; }); })
        .then(function (res) {
            btn.disabled = false;
            btn.textContent = label;
            var data = null;
            try { data = JSON.parse(res.raw); } catch (e) {}
            if (!res.r.ok) {
                if (window.showErrorModal) showErrorModal('Action failed', (data && data.error) || 'Could not update.');
                return null;
            }
            return data;
        })
        .catch(function (err) {
            btn.disabled = false;
            btn.textContent = label;
            if (window.showErrorModal) showErrorModal('Action failed', err.message || 'Network error.');
            return null;
        });
    }

    document.querySelectorAll('form[data-review-form]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (form.getAttribute('data-confirm-dirty') === 'true' && hasUnsavedEdits()) {
                if (!window.confirm('You have unsaved block edits. Proceed without saving them?')) return;
            }
            postForm(form).then(function (data) {
                if (!data) return;
                if (window.showToast) showToast('success', 'Updated', data.message || ('Status: ' + (data.status || 'ok')));
                if (form.getAttribute('data-inplace') === 'true') {
                    var card = form.closest('.doc-block');
                    if (card) {
                        applyBlockSaved(card);
                        updateUnsavedCount();
                    }
                } else if (form.getAttribute('data-reload') === 'true') {
                    suppressLeavePrompt = true;
                    window.location.reload();
                }
            });
        });
    });

    // ── Save & Regenerate (publish) ────────────────────────────────────
    function markPublished(data) {
        // Textareas now hold the published text — the leave guard must not fire.
        document.querySelectorAll('textarea[data-block-current]').forEach(function (ta) {
            ta.setAttribute('data-saved', ta.value);
        });

        // Header: replace the review-status badge text and drop the
        // "Unpublished edits" badge; hide the draft warning paragraph.
        var statusBadge = document.querySelector('.review-detail__header .status-badge');
        if (statusBadge && data.review_status) {
            statusBadge.className = 'status-badge status-badge--' + data.review_status;
            statusBadge.textContent = data.review_status.charAt(0).toUpperCase() + data.review_status.slice(1);
            var draftBadge = statusBadge.nextElementSibling;
            if (draftBadge && draftBadge.classList.contains('status-badge--edited')) {
                draftBadge.parentNode.removeChild(draftBadge);
            }
        }

        // Hide the draft warning paragraph the moment a publish succeeds.
        var warning = document.getElementById('draft-warning');
        if (warning) {
            warning.style.display = 'none';
        }

        // Per-block "Draft edit" badges become plain "Edited".
        document.querySelectorAll('.doc-block .status-badge--edited').forEach(function (b) {
            if (b.textContent === 'Draft edit') b.textContent = 'Edited';
        });
    }

    var regenForm = document.getElementById('save-regenerate-form');
    if (regenForm) {
        regenForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var btn = document.getElementById('regen-btn');
            var spinner = document.getElementById('regen-spinner');
            var result = document.getElementById('regen-result');
            var label = btn.textContent;
            btn.disabled = true;
            spinner.style.display = '';
            result.innerHTML = '';
            suppressLeavePrompt = true;

            var body = new FormData(regenForm);
            // Include every on-screen block edit so regeneration reflects the
            // latest typed text; blocks not visible keep their persisted state.
            document.querySelectorAll('.doc-block').forEach(function (card) {
                var textarea = card.querySelector('textarea[data-block-current]');
                var blockId = card.getAttribute('data-block-id');
                if (textarea && blockId) {
                    body.append('blocks[' + blockId + ']', textarea.value);
                }
            });
            fetch(regenForm.action, {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json' },
                body: body
            })
            .then(function (r) { return r.text().then(function (raw) { return { r: r, raw: raw }; }); })
            .then(function (res) {
                btn.disabled = false;
                spinner.style.display = 'none';
                var data = null;
                try { data = JSON.parse(res.raw); } catch (e) {}
                if (!res.r.ok) {
                    suppressLeavePrompt = false;
                    if (window.showErrorModal) showErrorModal('Regeneration failed', (data && data.error) || 'Could not regenerate. Your edits stay saved as a draft.');
                    return;
                }
                if (window.showToast) showToast('success', 'Published', data.message || 'New version published and made downloadable.');
                var html =
                    '<div class="regen-result">' +
                    '<strong>Published.</strong> This is now the downloadable version. (' + (data.edited_blocks ?? 0) + ' edited blocks included)' +
                    '<div class="regen-result__links">' +
                    '<a href="' + data.new_download_url + '">Download new version (' + (data.new_download_filename || 'file') + ')</a>';
                if (data.original_download_url) {
                    html += '<a href="' + data.original_download_url + '">Download original</a>';
                }
                html += '</div></div>';
                result.innerHTML = html;
                markPublished(data);
                updateUnsavedCount();
            })
            .catch(function (err) {
                btn.disabled = false;
                spinner.style.display = 'none';
                suppressLeavePrompt = false;
                if (window.showErrorModal) showErrorModal('Regeneration failed', err.message || 'Network error.');
            });
        });
    }

    updateUnsavedCount();
})();
</script>
@endsection
