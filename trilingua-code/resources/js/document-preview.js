/**
 * Shared same-origin document preview.
 *
 * Used by both the admin review pane (admin/review-document) and the user-facing
 * history detail page (history-detail). Streams the actual file bytes through a
 * same-origin proxy route, converts the common office formats client-side, and
 * falls back to a block-based HTML document ("render from DB blocks") whenever a
 * format cannot be rendered or the conversion fails — so no preview is a dead end.
 *
 * Supported extensions:
 *   docx   → mammoth
 *   xlsx   → SheetJS
 *   pptx   → pptx-preview (lazy loaded)
 *   txt/md → plain text
 *   csv    → table
 *   rtf    → stripped text
 *   *      → block fallback (odt, unsupported, errors)
 */
(function () {
    'use strict';

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function decodeText(buffer) {
        try {
            return new TextDecoder('utf-8').decode(buffer);
        } catch (e) {
            return new TextDecoder('latin1').decode(buffer);
        }
    }

    // ── Converters (return an HTML string) ─────────────────────────────────

    function renderWorkbook(XLSX, workbook) {
        var firstSheetName = workbook.SheetNames[0];
        var sheet = workbook.Sheets[firstSheetName];
        if (!sheet) return '<p class="review-form-note">The workbook has no sheets.</p>';
        return XLSX.utils.sheet_to_html(sheet, { header: '', footer: '' });
    }

    function renderPlainText(buffer) {
        var text = decodeText(buffer);
        return '<pre class="converter-output converter-output--plain">' + escapeHtml(text || '') + '</pre>';
    }

    function renderCsv(buffer) {
        var text = decodeText(buffer);
        var rows = [];
        var row = [], field = '', inQuotes = false;

        for (var i = 0; i < text.length; i++) {
            var c = text[i];
            if (inQuotes) {
                if (c === '"') {
                    if (text[i + 1] === '"') { field += '"'; i++; }
                    else inQuotes = false;
                } else {
                    field += c;
                }
            } else if (c === '"') {
                inQuotes = true;
            } else if (c === ',') {
                row.push(field); field = '';
            } else if (c === '\n') {
                row.push(field); rows.push(row); row = []; field = '';
            } else if (c !== '\r') {
                field += c;
            }
        }
        if (field !== '' || row.length) { row.push(field); rows.push(row); }
        if (rows.length === 0) return '<p class="review-form-note">The file is empty.</p>';

        var html = '<div class="converter-output converter-output--table"><table>';
        rows.forEach(function (cells, r) {
            html += '<tr>';
            cells.forEach(function (cell) {
                var tag = r === 0 ? 'th' : 'td';
                html += '<' + tag + '>' + escapeHtml(cell) + '</' + tag + '>';
            });
            html += '</tr>';
        });
        return html + '</table></div>';
    }

    function renderRtf(buffer) {
        var text = new TextDecoder('latin1').decode(buffer);
        text = text.replace(/\\'([0-9a-fA-F]{2})/g, function (_, hex) {
            return String.fromCharCode(parseInt(hex, 16));
        });
        text = text.replace(/\\par[d]?/gi, '\n')
            .replace(/\\tab/gi, '\t')
            .replace(/\\(?:[a-zA-Z]+-?\d* ?|.)/g, '')
            .replace(/[{}]/g, '');
        return '<pre class="converter-output converter-output--plain">' + escapeHtml(text.trim() || '') + '</pre>';
    }

    /**
     * Render the saved document content from translation_blocks as an HTML
     * document. Works for any format because it reads the DB, not the file.
     *
     * @param {Array} blocks  Ordered solid blocks.
     * @param {Object} [opts]  { preferSource: bool } — when true (e.g. showing
     *                         the ORIGINAL document), source text wins.
     */
    function renderBlocksHtml(blocks, opts) {
        var list = Array.isArray(blocks) ? blocks : [];
        if (!list.length) return '';

                var mode = (opts && opts.mode) || ((opts && opts.preferSource) ? 'source' : 'draft');
        var html = '';
        list.forEach(function (b) {
            var index = b.block_index;
            var type = String(b.block_type || 'paragraph').toLowerCase();

            var text = '';
            var unavailable = false;
            if (mode === 'published') {
                // Final/Saved preview shows only what the downloadable file
                // actually contains. If the published text is unknown (legacy or
                // uncommitted), show an honest unavailable state - never a draft.
                if (b.published_text != null && b.published_text !== '') {
                    text = b.published_text;
                } else {
                    unavailable = true;
                }
            } else if (mode === 'source') {
                text = (b.source_text != null && b.source_text !== '')
                    ? b.source_text
                    : ((b.current_text != null && b.current_text !== '')
                        ? b.current_text
                        : (b.ai_translated_text || ''));
            } else {
                text = (b.current_text != null && b.current_text !== '')
                    ? b.current_text
                    : ((b.ai_translated_text != null && b.ai_translated_text !== '')
                        ? b.ai_translated_text
                        : (b.source_text || ''));
            }

            var cls = 'draft-block';
            if (type === 'title' || type === 'header' || type === 'heading') cls += ' draft-block--heading';
            if (type === 'table_cell') cls += ' draft-block--cell';
            if (unavailable) cls += ' draft-block--unavailable';

            html += '<div class="' + cls + '">' +
                '<div class="draft-block__head">' +
                '<span class="block-card__index">Block #' + escapeHtml(index) + '</span>' +
                '<span class="block-card__type">' + escapeHtml(type || 'block') + '</span>' +
                '</div>' +
                '<div class="draft-block__text">' + (unavailable
                    ? '<span class="preview-unavailable">Published text preview unavailable.</span>'
                    : escapeHtml(text || '')) +
                '</div>' +
                '</div>';
        });

        return '<div class="converter-output">' + html + '</div>';
    }

    // ── PPTX preview via pptx-preview (lazy loaded) ────────────────────────

    function renderPptx(host, buffer) {
        return import('pptx-preview').then(function (PPTX) {
            host.innerHTML = '';
            var wrapper = document.createElement('div');
            wrapper.className = 'pptx-preview-holder';
            host.appendChild(wrapper);

            var width = Math.max(420, Math.min(host.clientWidth || 900, 900));
            var height = Math.round((width * 9) / 16);

            var viewer = PPTX.init(wrapper, { width: width, height: height, mode: 'slide' });
            return viewer.preview(buffer);
        });
    }

    /**
     * Boot the preview on a host element:
     *   <div id="converter-host" data-ext="docx" data-file-url="..." data-blocks-url="...">
     */
    function mountDocumentPreview(host) {
        var ext = (host.getAttribute('data-ext') || '').toLowerCase();
        var fileUrl = host.getAttribute('data-file-url');
        var blocksUrl = host.getAttribute('data-blocks-url');

        if (!fileUrl) {
            host.innerHTML = '<div class="review-pane__placeholder"><p>Preview unavailable.</p></div>';
            return;
        }

        host.innerHTML = '<div class="review-pane__loading">Loading preview…</div>';

        fetch(fileUrl, { headers: { 'Accept': 'application/octet-stream' } })
            .then(function (res) {
                if (!res.ok) throw new Error('Could not load the file.');
                return res.arrayBuffer();
            })
            .then(function (buffer) {
                if (ext === 'pptx') return renderPptx(host, buffer);
                return convertToHtml(ext, buffer);
            })
            .then(function (result) {
                if (result && result.html) {
                    host.innerHTML = '<div class="converter-output">' + result.html + '</div>';
                }
            })
            .catch(function (err) {
                loadBlockFallback(host, ext, err);
            });
    }

    function convertToHtml(ext, buffer) {
        if (ext === 'docx') {
            return import('mammoth/mammoth.browser').then(function (mammoth) {
                return mammoth.convertToHtml({ arrayBuffer: buffer }, {
                    styleMap: [
                        "p[style-name='Title'] => h1:fresh",
                        "p[style-name='Heading 1'] => h1:fresh",
                        "p[style-name='Heading 2'] => h2:fresh",
                        "p[style-name='Heading 3'] => h3:fresh"
                    ]
                });
            }).then(function (result) {
                return { html: result.value || '' };
            });
        }

        if (ext === 'xlsx' || ext === 'xls') {
            return import('xlsx').then(function (XLSX) {
                var workbook = XLSX.read(buffer, { type: 'array' });
                return { html: renderWorkbook(XLSX, workbook) };
            });
        }

        if (ext === 'txt' || ext === 'md') {
            return { html: renderPlainText(buffer) };
        }
        if (ext === 'csv') {
            return { html: renderCsv(buffer) };
        }
        if (ext === 'rtf') {
            return { html: renderRtf(buffer) };
        }

        throw new Error('Unsupported file type: ' + ext);
    }

    /**
     * Render the stored block content when the binary file cannot be rendered
     * (e.g. ODT originals, unknown extensions, conversion errors).
     */
    function loadBlockFallback(host, ext, err) {
        var blocksUrl = host.getAttribute('data-blocks-url');
        if (!blocksUrl) {
            showConversionError(host, ext, err);
            return;
        }

        var mode = 'draft';
        if (host.getAttribute('data-blocks-mode') === 'published') mode = 'published';
        else if (host.getAttribute('data-blocks-field') === 'source_text') mode = 'source';

        fetch(blocksUrl, { headers: { 'Accept': 'application/json' } })
            .then(function (res) {
                if (!res.ok) throw new Error('Could not load the document content.');
                return res.json();
            })
            .then(function (data) {
                var blocks = data && (data.blocks || data);
                if (!Array.isArray(blocks) || !blocks.length) {
                    showConversionError(host, ext, err);
                    return;
                }

                var note = '<div class="preview-draft__note">' +
                    'Browser preview is not available for <strong>' + escapeHtml(ext || 'this file type') +
                    '</strong>, so a plain-text preview of the saved document is shown instead. ' +
                    '<strong>Real layout (tables, images, spacing, headers) may differ from the actual file.</strong> ' +
                    '<a class="review-pane__download" href="' + escapeHtml(host.getAttribute('data-file-url') || '') +
                    '" target="_blank" rel="noopener">Download file</a></div>';

                host.innerHTML = note + renderBlocksHtml(blocks, { mode: mode });
            })
            .catch(function () {
                showConversionError(host, ext, err);
            });
    }

    function showConversionError(host, ext, err) {
        var fileUrl = host.getAttribute('data-file-url');
        host.innerHTML =
            '<div class="review-pane__placeholder">' +
            '<p>Could not render this preview: ' + escapeHtml((err && err.message) || 'unknown error') + '</p>' +
            (fileUrl
                ? '<a class="review-btn" href="' + escapeHtml(fileUrl) + '" target="_blank" rel="noopener">Download document</a>'
                : '') +
            '</div>';
    }

    window.documentPreview = {
        mount: mountDocumentPreview,
        renderBlocksHtml: renderBlocksHtml,
        escapeHtml: escapeHtml
    };
})();