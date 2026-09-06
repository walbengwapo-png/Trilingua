@extends('layouts.app')

@section('title', 'Review Text Translation')

@section('styles')
    @vite(['resources/css/views/admin.css'])
@endsection

@section('content')
@php
    $presentation = \App\Support\TranslationPresentation::for($record, auth()->user()->resolvedPreferences());
@endphp
<div class="stack">

    <a href="{{ route('admin.review.index') }}" class="review-back">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
        Back to review queue
    </a>

    <div class="review-detail-card">
        <div class="review-detail__header">
            <div>
                <span class="status-badge status-badge--{{ $record->review_status }}" title="{{ $presentation['lifecycle']['translation_label'] }}; {{ $presentation['lifecycle']['review_label'] }}">{{ $presentation['lifecycle']['label'] }}</span>
                <h2 class="review-detail__title" style="font-size:1.15rem;font-weight:700;color:var(--text);margin:10px 0 0">Text Translation</h2>
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
                <span class="review-detail__meta-value"><x-quality-badge :score="$record->quality_score" /></span>
            </div>
            @if ($record->flag_reason)
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Flag Reason</span>
                <span class="review-detail__meta-value">{{ ucwords(str_replace('_', ' ', $record->flag_reason)) }}</span>
            </div>
            @endif
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Submitted By</span>
                <span class="review-detail__meta-value">{{ $record->user->name ?? 'Unknown' }} ({{ $record->user->email ?? '—' }})</span>
            </div>
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Submitted At</span>
                <time class="review-detail__meta-value" datetime="{{ $record->created_at }}" title="{{ $presentation['date']['exact'] }}">{{ $presentation['date']['relative'] }}</time>
            </div>
            @if ($record->reviewer)
            <div class="review-detail__meta-item">
                <span class="review-detail__meta-label">Reviewed By</span>
                <span class="review-detail__meta-value">{{ $record->reviewer->name }}</span>
            </div>
            @endif
        </div>

        <div class="review-comparison" aria-label="Source and current translation comparison">
            <section><h4 class="review-detail__section-title">Source text</h4><div class="review-text-block">{{ $record->source_text ?? '—' }}</div></section>
            <section><h4 class="review-detail__section-title">Current translation</h4><div class="review-text-block" id="text-current" data-original="{{ $record->translated_text ?? '' }}">{{ $record->translated_text ?? '—' }}</div></section>
        </div>

        {{-- Write actions --}}
        <div class="review-form-card">
            <h4 class="review-form-card__title">Actions</h4>

            <form method="POST" action="{{ route('admin.review.text.verify', $record->id) }}" class="review-inline-form"
                  data-review-form data-success="verified">
                @csrf
                <input type="text" name="note" class="review-input" placeholder="Optional verification note" aria-label="Verification note">
                <button type="submit" class="review-btn review-btn--success" data-shortcut="v">Verify</button>
            </form>

            <form method="POST" action="{{ route('admin.review.text.update', $record->id) }}" class="review-form-card" style="margin-top:14px"
                  data-review-form data-success="edited">
                @csrf
                <textarea name="translated_text" class="review-textarea" aria-label="Translated text">{{ $record->translated_text }}</textarea>
                <input type="text" name="note" class="review-input" placeholder="Optional edit note" aria-label="Edit note">
                <div class="review-form-actions">
                    <button type="submit" class="review-btn review-btn--warning">Save Edit</button>
                </div>
                <p class="review-form-note">Saving an edit logs the previous translated text to the audit trail before overwriting.</p>
            </form>

            <form method="POST" action="{{ route('admin.review.text.flag', $record->id) }}" class="review-form-card" style="margin-top:14px"
                  data-review-form data-success="flagged">
                @csrf
                <div class="block-card__actions" style="border-top:none;padding-top:0;margin-top:0">
                    <select name="reason" class="review-select" required aria-label="Flag reason">
                        <option value="">Select flag reason…</option>
                        @foreach (\App\Support\FlagReason::ALL as $reason)
                            <option value="{{ $reason }}" @selected($record->flag_reason === $reason)>{{ ucwords(str_replace('_', ' ', $reason)) }}</option>
                        @endforeach
                    </select>
                    <input type="text" name="note" class="review-input" placeholder="Required flag note" value="{{ $record->flag_note ?? '' }}" required style="flex:1" aria-describedby="flag-note-help">
                    <button type="submit" class="review-btn review-btn--danger" data-shortcut="f">Flag</button>
                </div>
                <p class="review-form-note" id="flag-note-help">Explain the issue so the audit trail is useful to the next reviewer.</p>
            </form>
            <div id="review-result" class="review-form-note" role="status" aria-live="polite"></div>
        </div>
    </div>

</div>

<script>
(function () {
    'use strict';
    var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    var statusEl = document.querySelector('.status-badge--' + '{{ $record->review_status }}');

    document.querySelectorAll('form[data-review-form]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var btn = form.querySelector('button[type="submit"]');
            var label = btn.textContent.trim();
            btn.disabled = true;
            btn.textContent = 'Working…';

            var body = new FormData(form);
            var action = form.getAttribute('data-success') || 'update';
            if (!window.confirm('Confirm ' + action + '. This will be recorded in the immutable review audit trail.')) { btn.disabled = false; btn.textContent = label; return; }
            fetch(form.action, {
                method: 'POST',
                headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json' },
                body: body
            })
            .then(function (r) { return r.text().then(function (raw) { return { r: r, raw: raw }; }); })
            .then(function (res) {
                var data = null;
                try { data = JSON.parse(res.raw); } catch (e) {}
                btn.disabled = false;
                btn.textContent = label;
                if (!res.r.ok) {
                    var err = data && data.error && typeof data.error === 'object' ? data.error.message : 'Could not update.';
                    if (window.showErrorModal) showErrorModal('Action failed', err);
                    return;
                }
                if (window.showToast) showToast('success', 'Updated', 'Status: ' + (data.status || 'ok'));
                var result = document.getElementById('review-result');
                if (result) result.textContent = 'Saved: ' + (data.audit && data.audit.action ? data.audit.action : action) + ' is recorded in the audit history.';
                if (statusEl && data.status) { statusEl.className = 'status-badge status-badge--' + data.status; statusEl.textContent = 'Translation complete · Review ' + data.status; }
            })
            .catch(function (err) {
                btn.disabled = false;
                btn.textContent = label;
                if (window.showErrorModal) showErrorModal('Action failed', err.message || 'Network error.');
            });
        });
    });
    document.addEventListener('keydown', function (event) {
        if (event.altKey || event.ctrlKey || event.metaKey || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName)) return;
        if (event.key.toLowerCase() === 'v') { var verify = document.querySelector('[data-shortcut="v"]'); if (verify) { event.preventDefault(); verify.focus(); } }
        if (event.key.toLowerCase() === 'e') { var editor = document.querySelector('textarea[name="translated_text"]'); if (editor) { event.preventDefault(); editor.focus(); } }
        if (event.key.toLowerCase() === 'f') { var flag = document.querySelector('[data-shortcut="f"]'); if (flag) { event.preventDefault(); flag.focus(); } }
    });
})();
</script>
@endsection
