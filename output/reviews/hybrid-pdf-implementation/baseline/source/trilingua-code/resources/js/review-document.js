/**
 * Admin document-review two-pane preview.
 *
 * - Final tab: renders the actual saved file. The heavy lifting (DOCX via
 *   mammoth, XLSX via SheetJS, PPTX via pptx-preview, plain text/CSV/RTF) lives
 *   in document-preview.js, which also falls back to the DB block content.
 * - Draft tab: a live, block-rendered document mirroring the editable pane,
 *   rebuilt on every keystroke with changed blocks highlighted — no DB writes.
 *
 * Converters are lazy-loaded via dynamic import so they only download when a
 * preview is actually present.
 */
(function () {
    'use strict';

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
        var items = Array.from(tabs.querySelectorAll('.review-pane__tab'));

        function activate(tab) {
            items.forEach(function (t) {
                var on = t === tab;
                t.classList.toggle('is-active', on);
                t.setAttribute('aria-selected', on ? 'true' : 'false');
                t.tabIndex = on ? 0 : -1;
            });

            var name = tab.getAttribute('data-tab');
            var showDraft = name === 'draft';
            finalPanel.style.display = showDraft ? 'none' : '';
            draftPanel.style.display = showDraft ? '' : 'none';
            if (showDraft) renderDraft();
        }

        items.forEach(function (tab, i) {
            tab.addEventListener('click', function () {
                activate(tab);
                tab.focus(); // keep visible focus on the active tab
            });
            tab.addEventListener('keydown', function (e) {
                if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                e.preventDefault();
                var next = e.key === 'ArrowRight'
                    ? (i + 1) % items.length
                    : (i - 1 + items.length) % items.length;
                activate(items[next]);
                items[next].focus();
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

        var host = document.getElementById('converter-host');
        if (host && window.documentPreview) {
            documentPreview.mount(host);
        }
    });
})();