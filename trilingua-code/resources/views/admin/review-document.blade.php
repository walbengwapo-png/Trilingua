@extends('layouts.app')

@section('title', 'Review Document Translation')

@section('styles')
    @vite(['resources/css/views/admin.css', 'resources/js/review-document.js'])
@endsection

@section('content')
<div class="stack">

    <a href="{{ route('admin.review.index') }}" class="review-back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
        Back to review queue
    </a>

    <div class="review-detail-card">
        <div class="review-detail__header">
            <div>
                <span class="status-badge status-badge--{{ $record->review_status }}">{{ ucfirst($record->review_status) }}</span>
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
                <span class="review-detail__meta-label">Quality Score</span>
                <span class="review-detail__meta-value">{{ $record->quality_score === null ? '—' : $record->quality_score }}</span>
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
                <span class="review-detail__meta-value">{{ $record->blocks->count() }}</span>
            </div>
        </div>

        {{-- Bulk approve + Save & Regenerate --}}
        <div class="review-form-card">
            <h4 class="review-form-card__title">Document Actions</h4>

            <form method="POST" action="{{ route('admin.review.block.bulk-approve', $record->id) }}" class="review-inline-form"
                  data-review-form data-reload="true">
                @csrf
                <label for="threshold" class="review-form-note" style="margin:0">Verify blocks with score ≥</label>
                <input type="number" name="threshold" id="threshold" class="review-input" min="0" max="100" value="80" required>
                <button type="submit" class="review-btn review-btn--success">Bulk Approve</button>
            </form>

            <form method="POST" action="{{ route('admin.review.save-regenerate', $record->id) }}" class="review-form-card" style="margin-top:14px"
                  id="save-regenerate-form" data-regen-form>
                @csrf
                <p class="review-form-note" style="margin:0 0 8px">
                    Collects every edited block and re-renders the document synchronously (reconstruction only —
                    AI translation is never re-run). The new version is uploaded and you get download links for both files.
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
                    <div class="review-pane__tabs" id="preview-tabs">
                        <button type="button" class="review-pane__tab is-active" data-tab="final">Final</button>
                        <button type="button" class="review-pane__tab" data-tab="draft">Draft</button>
                    </div>
                </div>

                <div class="review-pane__body">
                    <div class="preview-panel" id="preview-final">
                        @if ($previewUrl && $isPdf)
                            <iframe class="review-pane__frame" src="{{ $previewUrl }}" title="Translated document"></iframe>
                        @elseif ($previewUrl && in_array($previewExt, ['docx', 'xlsx']))
                            <div id="converter-host"
                                 data-ext="{{ $previewExt }}"
                                 data-file-url="{{ route('admin.review.document.file', $record->id) }}">
                                <div class="review-pane__loading">Loading preview…</div>
                            </div>
                        @else
                            <div class="review-pane__placeholder">
                                <p>Live preview is only available for <strong>PDF</strong>, <strong>DOCX</strong>, and <strong>XLSX</strong>.</p>
                                <p>This translated file is a <strong>{{ strtoupper($previewExt ?: 'document') }}</strong>.</p>
                                @if ($previewUrl)
                                    <a class="review-btn" href="{{ $previewUrl }}" target="_blank" rel="noopener">Download translated document</a>
                                @elseif ($record->storage_path)
                                    <p class="review-form-note">Preview URL could not be generated.</p>
                                @endif
                            </div>
                        @endif
                    </div>
                    <div class="preview-panel" id="preview-draft" style="display:none">
                        <div class="preview-draft__note">
                            Showing your <strong>unsaved edits</strong> in blue. Switch to <strong>Final</strong> to compare against the saved file.
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
                        <span class="count-badge">{{ $record->blocks->count() }}</span>
                    </h4>
                </div>

                <div class="review-pane__body">
                    @if ($record->blocks->isEmpty())
                        <p class="empty-state">No blocks were extracted for this document.</p>
                    @else
                        <div class="doc-block-list">
                            @foreach ($record->blocks as $block)
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
                                            <span class="status-badge status-badge--edited">Edited</span>
                                        @endif
                                    </div>
                                    <span class="quality-score" style="min-width:0">
                                        <span class="quality-score__dot quality-score__dot--{{ $level }}" aria-hidden="true"></span>
                                        {{ $score === null ? '—' : $score }}
                                    </span>
                                </div>

                                <textarea class="doc-block__editor" name="current_text" data-block-current
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
                                    <form method="POST" action="{{ route('admin.review.block.verify', [$record->id, $block->id]) }}"
                                          class="review-inline-form" data-review-form data-reload="true">
                                        @csrf
                                        <button type="submit" class="review-btn review-btn--success">Verify</button>
                                    </form>

                                    <form method="POST" action="{{ route('admin.review.block.update', [$record->id, $block->id]) }}"
                                          class="review-inline-form" data-review-form data-reload="true">
                                        @csrf
                                        <input type="hidden" name="current_text" value="{{ htmlspecialchars($block->current_text ?? '', ENT_QUOTES) }}">
                                        <button type="submit" class="review-btn review-btn--warning">Save Edit</button>
                                    </form>

                                    <form method="POST" action="{{ route('admin.review.block.flag', [$record->id, $block->id]) }}"
                                          class="review-inline-form" data-review-form data-reload="true">
                                        @csrf
                                        <select name="reason" class="review-select" required aria-label="Flag reason">
                                            <option value="">Flag…</option>
                                            @foreach (\App\Support\FlagReason::ALL as $reason)
                                                <option value="{{ $reason }}" @selected($block->flag_reason === $reason)>{{ ucwords(str_replace('_', ' ', $reason)) }}</option>
                                            @endforeach
                                        </select>
                                        <button type="submit" class="review-btn review-btn--danger">Flag</button>
                                    </form>
                                </div>
                            </div>
                            @endforeach
                        </div>
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

    // Keep each block's hidden current_text input in sync with its textarea so
    // "Save Edit" posts the latest value.
    document.querySelectorAll('.doc-block').forEach(function (card) {
        var textarea = card.querySelector('textarea[data-block-current]');
        var hidden = card.querySelector('input[name="current_text"]');
        if (textarea && hidden) {
            textarea.addEventListener('input', function () { hidden.value = textarea.value; });
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
                if (window.showToast) showToast('error', 'Action failed', (data && data.error) || 'Could not update.');
                return null;
            }
            return data;
        })
        .catch(function (err) {
            btn.disabled = false;
            btn.textContent = label;
            if (window.showToast) showToast('error', 'Error', err.message || 'Network error.');
            return null;
        });
    }

    document.querySelectorAll('form[data-review-form]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            postForm(form).then(function (data) {
                if (!data) return;
                if (window.showToast) showToast('success', 'Updated', 'Status: ' + (data.status || 'ok'));
                if (form.getAttribute('data-reload') === 'true') {
                    window.location.reload();
                }
            });
        });
    });

    // ── Save & Regenerate ──────────────────────────────────────────────
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

            var body = new FormData(regenForm);
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
                    if (window.showToast) showToast('error', 'Regeneration failed', (data && data.error) || 'Could not regenerate.');
                    return;
                }
                if (window.showToast) showToast('success', 'Regenerated', 'New version uploaded (' + (data.edited_blocks ?? 0) + ' edited blocks).');
                var html =
                    '<div class="regen-result">' +
                    '<strong>Regeneration complete.</strong> (' + (data.edited_blocks ?? 0) + ' edited blocks included)' +
                    '<div class="regen-result__links">' +
                    '<a href="' + data.new_download_url + '">Download new version (' + (data.new_download_filename || 'file') + ')</a>';
                if (data.original_download_url) {
                    html += '<a href="' + data.original_download_url + '">Download original</a>';
                }
                html += '</div></div>';
                result.innerHTML = html;
                // Refresh so the badges show the latest block statuses.
                setTimeout(function () { window.location.reload(); }, 1200);
            })
            .catch(function (err) {
                btn.disabled = false;
                spinner.style.display = 'none';
                if (window.showToast) showToast('error', 'Error', err.message || 'Network error.');
            });
        });
    }
})();
</script>
@endsection