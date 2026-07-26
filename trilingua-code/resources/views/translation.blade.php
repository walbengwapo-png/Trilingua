@extends('layouts.app')

@section('title', 'New Translation')

@section('styles')
    @vite(['resources/css/views/translation.css'])
@endsection

@section('content')
<div class="translation-page">

    {{-- Language selection bar --}}
    <div class="lang-bar">
        <div class="lang-bar__select-wrap">
            <select id="source-lang" aria-label="Source language">
                <option value="English" selected>English</option>
                <option value="Cebuano">Cebuano</option>
                <option value="Filipino">Filipino</option>
            </select>
        </div>

        <button class="lang-bar__swap" id="swap-btn" aria-label="Swap languages" title="Swap languages">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M7 16V4m0 0L3 8m4-4l4 4"/>
                <path d="M17 8v12m0 0l4-4m-4 4l-4-4"/>
            </svg>
        </button>

        <div class="lang-bar__select-wrap">
            <select id="target-lang" aria-label="Target language">
                <option value="English">English</option>
                <option value="Cebuano" selected>Cebuano</option>
                <option value="Filipino">Filipino</option>
            </select>
        </div>
    </div>

    {{-- Two panels --}}
    <div class="translation-panels">

        {{-- Source panel --}}
        <div class="translation-panel translation-panel--source">
            <div class="translation-panel__label">Source text</div>
            <div class="translation-panel__body">
                <textarea id="source-text" maxlength="5000" placeholder="Enter text to translate…" aria-label="Source text"></textarea>

                {{-- File attached state --}}
                <div class="translation-panel__file-info" id="file-info" style="display:none">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                    <span id="file-name"></span>
                    <button id="remove-file" type="button">Remove</button>
                </div>
            </div>

            <div class="translation-panel__footer">
                {{-- Speak --}}
                <button id="speak-source-btn" type="button" class="speak-btn" aria-label="Read source text aloud" title="Read aloud">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                        <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
                        <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                    </svg>
                </button>

                {{-- Attach file --}}
                <button id="attach-btn" type="button" class="attach-btn" title="Attach a document">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    Attach file
                </button>
                <input id="file-input" type="file" hidden accept=".docx,.pdf,.txt,.md,.rtf,.odt,.csv">

                {{-- PDF column mode --}}
                <select id="pdf-column-mode" style="display:none" aria-label="PDF column mode">
                    <option value="auto" selected>Auto columns</option>
                    <option value="single">Single column</option>
                    <option value="left">Left column</option>
                    <option value="right">Right column</option>
                </select>

                <span id="char-counter" aria-live="polite">0/5000</span>
            </div>

            <div class="translation-panel__error" id="source-error" role="alert"></div>
        </div>

        {{-- Output panel --}}
        <div class="translation-panel translation-panel--output">
            <div class="translation-panel__label">Translation</div>
            <div class="translation-panel__body">
                <div id="output-text" aria-live="polite" aria-label="Translation output"></div>

                <div id="output-download" hidden>
                    <a id="download-link" href="#" class="download-btn">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                        Download translated file
                    </a>
                </div>
            </div>

            <div class="translation-panel__footer">
                {{-- Speak --}}
                <button id="speak-output-btn" type="button" class="speak-btn" aria-label="Read translation aloud" title="Read aloud">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                        <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
                        <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                    </svg>
                </button>

                {{-- Copy --}}
                <button id="copy-btn" type="button" class="action-btn" aria-disabled="true" title="Copy translation">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    Copy
                </button>

                {{-- Save --}}
                <button id="save-btn" type="button" class="action-btn" aria-disabled="true" title="Save as text file">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
                    Save
                </button>
            </div>

            <div class="translation-panel__error" id="output-error" role="alert"></div>
        </div>
    </div>

    {{-- Translate button --}}
    <div class="translation-submit">
        <button id="translate-btn" type="button">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>
                <path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/>
            </svg>
            Translate
        </button>
    </div>

</div>

<script>
(function () {
    'use strict';

    var sourceText    = document.getElementById('source-text');
    var charCounter   = document.getElementById('char-counter');
    var sourceLang    = document.getElementById('source-lang');
    var targetLang    = document.getElementById('target-lang');
    var swapBtn       = document.getElementById('swap-btn');
    var outputText    = document.getElementById('output-text');
    var attachBtn     = document.getElementById('attach-btn');
    var fileInput     = document.getElementById('file-input');
    var fileNameSpan  = document.getElementById('file-name');
    var removeFile    = document.getElementById('remove-file');
    var fileInfo      = document.getElementById('file-info');
    var pdfColumnMode = document.getElementById('pdf-column-mode');
    var sourceError   = document.getElementById('source-error');
    var outputError   = document.getElementById('output-error');
    var translateBtn  = document.getElementById('translate-btn');
    var copyBtn       = document.getElementById('copy-btn');
    var saveBtn       = document.getElementById('save-btn');
    var outputDownload = document.getElementById('output-download');
    var downloadLink   = document.getElementById('download-link');

    function showError(el, msg) { if (el) el.textContent = msg; }
    function clearError(el)     { if (el) el.textContent = ''; }

    // ── Character counter ────────────────────────────────────────────────────
    var MAX_CHARS = 5000, WARN = 4500;

    function updateCounter() {
        var len = sourceText.value.length;
        var remaining = MAX_CHARS - len;
        charCounter.textContent = len + '/' + MAX_CHARS;
        charCounter.classList.toggle('counter-warning', len > WARN);
        if (len > WARN) {
            charCounter.textContent = remaining + ' left';
        }
    }

    sourceText.addEventListener('input', updateCounter);

    sourceText.addEventListener('paste', function (e) {
        e.preventDefault();
        var pasted = (e.clipboardData || window.clipboardData).getData('text');
        var before = sourceText.value.substring(0, sourceText.selectionStart);
        var after  = sourceText.value.substring(sourceText.selectionEnd);
        var combined = (before + pasted + after).substring(0, MAX_CHARS);
        sourceText.value = combined;
        sourceText.setSelectionRange(Math.min(before.length + pasted.length, MAX_CHARS), Math.min(before.length + pasted.length, MAX_CHARS));
        updateCounter();
    });

    // ── Swap ─────────────────────────────────────────────────────────────────
    swapBtn.addEventListener('click', function () {
        var src = sourceLang.value, tgt = targetLang.value;
        if (src === tgt) { showError(sourceError, 'Source and target languages must be different.'); return; }
        sourceLang.value = tgt; targetLang.value = src;
        clearError(sourceError); outputText.textContent = ''; clearError(outputError);
    });

    // ── File attachment ───────────────────────────────────────────────────────
    var ALLOWED = ['.docx','.pdf','.txt','.md','.rtf','.odt','.csv'];
    var MAX_SIZE = 10485760;

    attachBtn.addEventListener('click', function () { fileInput.click(); });

    fileInput.addEventListener('change', function () {
        var file = fileInput.files[0];
        if (!file) return;
        var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
        if (ALLOWED.indexOf(ext) === -1) { showError(sourceError, 'Unsupported file type. Allowed: ' + ALLOWED.join(', ')); fileInput.value = ''; return; }
        if (file.size > MAX_SIZE) { showError(sourceError, 'File too large. Maximum size is 10 MB.'); fileInput.value = ''; return; }
        clearError(sourceError);
        fileNameSpan.textContent = file.name;
        sourceText.style.display = 'none';
        charCounter.style.display = 'none';
        fileInfo.style.display = '';
        pdfColumnMode.style.display = ext === '.pdf' ? '' : 'none';
        if (ext !== '.pdf') pdfColumnMode.value = 'auto';
    });

    removeFile.addEventListener('click', function () {
        fileInput.value = '';
        fileInfo.style.display = 'none';
        sourceText.style.display = '';
        charCounter.style.display = '';
        clearError(sourceError);
        pdfColumnMode.style.display = 'none';
        pdfColumnMode.value = 'auto';
    });

    // ── Translate ─────────────────────────────────────────────────────────────
    function setLoading(on) {
        translateBtn.disabled = on;
        translateBtn.innerHTML = on
            ? '<span class="btn-spinner"></span> Translating…'
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 8l6 6"/><path d="M4 14l6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="M22 22l-5-10-5 10"/><path d="M14 18h6"/></svg> Translate';
        // Toggle skeleton loading state on output panel
        if (on) {
            outputText.classList.add('skeleton-loading');
        } else {
            outputText.classList.remove('skeleton-loading');
        }
    }

    translateBtn.addEventListener('click', function () {
        clearError(sourceError); clearError(outputError);
        var file = fileInput.files[0];
        var csrfToken = document.querySelector('meta[name="csrf-token"]').content;
        setLoading(true);

        var formData = new FormData();
        formData.append('source_lang', sourceLang.value);
        formData.append('target_lang', targetLang.value);
        formData.append('_token', csrfToken);

        if (file) {
            formData.append('document', file);
            var ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
            if (ext === '.pdf') formData.append('pdf_column_mode', pdfColumnMode.value);
        } else {
            var text = sourceText.value.trim();
            if (!text) { showError(sourceError, 'Please enter text to translate.'); setLoading(false); return; }
            formData.append('text', text);
        }

        fetch('/translate', {
            method: 'POST',
            headers: { 'X-CSRF-TOKEN': csrfToken, 'Accept': 'application/json' },
            body: formData
        })
        .then(function (res) {
            return res.text().then(function (raw) {
                var data = null;
                try { data = JSON.parse(raw); } catch (e) {}

                if (res.ok && data && data.status === 'processing' && data.job_id) {
                    // Document translation queued - poll for status
                    outputText.textContent = 'Translation in progress... This may take a few minutes depending on document size.';
                    outputDownload.setAttribute('hidden', '');
                    copyBtn.setAttribute('aria-disabled', 'true');
                    saveBtn.setAttribute('aria-disabled', 'true');
                    pollJobStatus(data.job_id);
                } else if (res.ok && data && (data.download_url || data.download_data)) {
                    outputText.textContent = '';
                    outputDownload.removeAttribute('hidden');
                    downloadLink.href = data.download_data || data.download_url;
                    downloadLink.download = data.download_filename || 'translated_document';
                    downloadLink.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download: ' + (data.download_filename || 'translated_document');
                    copyBtn.setAttribute('aria-disabled', 'true');
                    saveBtn.setAttribute('aria-disabled', 'true');
                    if (window.showToast) showToast('success', 'Document translated!', 'Your file is ready to download.');
                } else if (res.ok && data && data.translated) {
                    outputText.textContent = data.translated;
                    outputDownload.setAttribute('hidden', '');
                    copyBtn.removeAttribute('aria-disabled');
                    saveBtn.removeAttribute('aria-disabled');
                } else if (res.status === 422 && data && data.errors) {
                    showError(sourceError, data.errors[Object.keys(data.errors)[0]][0]);
                } else if (res.status === 504) {
                    showError(outputError, (data && data.error) || 'Translation took too long. Please try with a smaller file.');
                } else if (res.status === 400 && data && data.error) {
                    showError(sourceError, data.error);
                } else {
                    var errorMsg = (data && (data.error || data.detail)) || 'Translation failed. Please try again.';
                    showError(outputError, errorMsg);
                }
            });
        })
        .catch(function () { showError(outputError, 'Network error. Please check your connection and try again.'); })
        .finally(function () { setLoading(false); });
    });

    // Poll for document translation status
    function pollJobStatus(jobId) {
        var maxAttempts = 180; // 6 minutes max (180 * 2s)
        var attempts = 0;
        var interval = setInterval(function () {
            attempts++;
            if (attempts > maxAttempts) {
                clearInterval(interval);
                showError(outputError, 'Translation timed out. Please try again or contact support if the issue persists.');
                return;
            }

            fetch('/translate/status/' + jobId, {
                credentials: 'include',
                headers: { 'Accept': 'application/json' }
            })
            .then(function (res) {
                return res.text().then(function (raw) {
                    var data = null;
                    try { data = JSON.parse(raw); } catch (e) {}

                    if (data && data.status === 'completed') {
                        clearInterval(interval);
                        outputText.textContent = '';
                        outputDownload.removeAttribute('hidden');
                        downloadLink.href = data.download_data || data.download_url;
                        downloadLink.download = data.download_filename || 'translated_document';
                        downloadLink.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> Download: ' + (data.download_filename || 'translated_document');
                        copyBtn.setAttribute('aria-disabled', 'true');
                        saveBtn.setAttribute('aria-disabled', 'true');
                        if (window.showToast) showToast('success', 'Document translated!', 'Your file is ready to download.');
                    } else if (data && data.status === 'failed') {
                        clearInterval(interval);
                        showError(outputError, (data && data.error) || 'Translation failed. Please try again.');
                    } else if (attempts % 15 === 0) {
                        // Update message every 30 seconds
                        outputText.textContent = 'Still translating... (' + Math.round(attempts / 30) + ' minute(s) elapsed)';
                    }
                });
            })
            .catch(function () {
                // Don't show error on polling failure, just continue
            });
        }, 2000); // Poll every 2 seconds
    }

    // ── Copy ──────────────────────────────────────────────────────────────────
    copyBtn.addEventListener('click', function () {
        if (copyBtn.getAttribute('aria-disabled') === 'true') return;
        navigator.clipboard.writeText(outputText.textContent).then(function () {
            if (window.showToast) showToast('success', 'Copied!', 'Translation copied to clipboard.');
        }).catch(function () {
            if (window.showToast) showToast('error', 'Copy failed', 'Could not access clipboard.');
        });
    });

    // ── Save ──────────────────────────────────────────────────────────────────
    saveBtn.addEventListener('click', function () {
        if (saveBtn.getAttribute('aria-disabled') === 'true') return;
        var now = new Date(), pad = function(n){ return String(n).padStart(2,'0'); };
        var ts = now.getUTCFullYear()+pad(now.getUTCMonth()+1)+pad(now.getUTCDate())+'_'+pad(now.getUTCHours())+pad(now.getUTCMinutes())+pad(now.getUTCSeconds());
        var blob = new Blob([outputText.textContent], { type: 'text/plain' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url; a.download = 'translation_' + ts + '.txt';
        document.body.appendChild(a); a.click();
        document.body.removeChild(a); URL.revokeObjectURL(url);
        if (window.showToast) showToast('success', 'File saved', 'Translation saved as .txt file.');
    });

    // ── Text-to-speech ────────────────────────────────────────────────────────
    var speakSrc = document.getElementById('speak-source-btn');
    var speakOut = document.getElementById('speak-output-btn');

    if (!window.speechSynthesis) {
        if (speakSrc) speakSrc.style.display = 'none';
        if (speakOut) speakOut.style.display = 'none';
    } else {
        function getLang(val) { return val === 'English' ? 'en-US' : val === 'Filipino' ? 'fil-PH' : 'ceb'; }
        speakSrc.addEventListener('click', function () {
            window.speechSynthesis.cancel();
            var t = sourceText.value.trim(); if (!t) return;
            var u = new SpeechSynthesisUtterance(t); u.lang = getLang(sourceLang.value);
            window.speechSynthesis.speak(u);
        });
        speakOut.addEventListener('click', function () {
            window.speechSynthesis.cancel();
            var t = outputText.textContent.trim(); if (!t) return;
            var u = new SpeechSynthesisUtterance(t); u.lang = getLang(targetLang.value);
            window.speechSynthesis.speak(u);
        });
    }

})();
</script>
@endsection
