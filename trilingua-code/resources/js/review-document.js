/**
 * Admin document-review two-pane preview.
 *
 * - Final tab: renders the actual saved file (PDF iframe is rendered server-side;
 *   DOCX/XLSX are converted client-side from the same-origin file proxy).
 * - Draft tab: a live, block-rendered document mirroring the editable pane,
 *   rebuilt on every keystroke with changed blocks highlighted — no DB writes.
 *
 * Converters (mammoth / SheetJS) are lazy-loaded via dynamic import so they only
 * download when a DOCX/XLSX preview is actually present.
 */
(function () {
    'use strict';

    // ── Final preview: DOCX / XLSX conversion ──────────────────────────────
    function renderFinalPreview() {
        var host = document.getElementById('converter-host');
        if (!host) return;

        var ext = (host.getAttribute('data-ext') || '').toLowerCase();
        var fileUrl = host.getAttribute('data-file-url');
        if (!fileUrl) {
            host.innerHTML = '<div class="review-pane__placeholder"><p>Preview unavailable.</p></div>';
            return;
        }

        fetch(fileUrl, { headers: { 'Accept': 'application/octet-stream' } })
            .then(function (res) {
                if (!res.ok) throw new Error('Could not load the translated file.');
                return res.arrayBuffer();
            })
            .then(async function (buffer) {
                if (ext === 'docx') {
                    var mammoth = await import('mammoth/mammoth.browser');
                    return mammoth.convertToHtml({ arrayBuffer: buffer }, {
                        styleMap: [
                            "p[style-name='Title'] => h1:fresh",
                            "p[style-name='Heading 1'] => h1:fresh",
                            "p[style-name='Heading 2'] => h2:fresh",
                            "p[style-name='Heading 3'] => h3:fresh"
                        ]
                    });
                }
                if (ext === 'xlsx') {
                    var XLSX = await import('xlsx');
                    var workbook = XLSX.read(buffer, { type: 'array' });
                    return { value: renderWorkbook(XLSX, workbook) };
                }
                throw new Error('Unsupported file type.');
            })
            .then(function (result) {
                host.innerHTML = '<div class="converter-output">' + (result.value || '') + '</div>';
            })
            .catch(function (err) {
                host.innerHTML =
                    '<div class="review-pane__placeholder">' +
                    '<p>Could not render this preview: ' + escapeHtml(err.message || 'unknown error') + '</p>' +
                    '</div>';
            });
    }

    function renderWorkbook(XLSX, workbook) {
        var firstSheetName = workbook.SheetNames[0];
        var sheet = workbook.Sheets[firstSheetName];
        if (!sheet) return '<p class="review-form-note">The workbook has no sheets.</p>';
        return XLSX.utils.sheet_to_html(sheet, { header: '', footer: '' });
    }

    // ── Draft preview: live block mirror ───────────────────────────────────
    function renderDraft() {
        var container = document.getElementById('draft-doc');
        if (!container) return;

        var blocks = Array.from(document.querySelectorAll('.doc-block'));
        var html = '';

        blocks.forEach(function (block) {
            var index = block.getAttribute('data-block-index') || '';
            var type = (block.querySelector('.block-card__type') || {}).textContent || 'block';
            var editor = block.querySelector('textarea[data-block-current]');
            if (!editor) return;

            var value = editor.value;
            var saved = editor.getAttribute('data-saved') || '';
            var changed = value !== saved;

            var cls = 'draft-block' + (changed ? ' draft-block--changed' : '');
            if (type === 'header' || type === 'heading') cls += ' draft-block--heading';
            if (type === 'table_cell') cls += ' draft-block--cell';

            html += '<div class="' + cls + '" data-block-index="' + escapeAttr(index) + '">';
            html += '<div class="draft-block__head"><span class="block-card__index">Block #' + escapeHtml(index) + '</span>';
            if (changed) html += '<span class="draft-block__tag">edited</span>';
            html += '</div>';
            html += '<div class="draft-block__text">' + escapeHtml(value || '') + '</div>';
            html += '</div>';
        });

        container.innerHTML = html || '<p class="review-form-note">No blocks to preview.</p>';
    }

    // ── Tab switching ──────────────────────────────────────────────────────
    function bindTabs() {
        var tabs = document.getElementById('preview-tabs');
        if (!tabs) return;

        var finalPanel = document.getElementById('preview-final');
        var draftPanel = document.getElementById('preview-draft');

        tabs.querySelectorAll('.review-pane__tab').forEach(function (tab) {
            tab.addEventListener('click', function () {
                tabs.querySelectorAll('.review-pane__tab').forEach(function (t) { t.classList.remove('is-active'); });
                tab.classList.add('is-active');

                var name = tab.getAttribute('data-tab');
                finalPanel.style.display = name === 'final' ? '' : 'none';
                draftPanel.style.display = name === 'draft' ? '' : 'none';
                if (name === 'draft') renderDraft();
            });
        });
    }

    // ── Helpers ────────────────────────────────────────────────────────────
    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function escapeAttr(str) {
        return escapeHtml(str);
    }

    // ── Boot ───────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        bindTabs();

        var editors = document.querySelectorAll('textarea[data-block-current]');
        editors.forEach(function (editor) {
            editor.addEventListener('input', function () {
                if (document.getElementById('preview-draft').style.display !== 'none') {
                    renderDraft();
                }
            });
        });

        renderFinalPreview();
    });
})();
