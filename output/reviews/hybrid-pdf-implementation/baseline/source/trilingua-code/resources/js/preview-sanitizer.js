import createDOMPurify from 'dompurify';

const purifier = createDOMPurify(window);
const tags = ['p', 'br', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'u', 's', 'sup', 'sub', 'ul', 'ol', 'li',
    'blockquote', 'pre', 'code', 'hr', 'a', 'table', 'caption', 'colgroup',
    'col', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'img'];
const globalAttributes = new Set(['title', 'lang', 'dir']);
const attributes = {
    a: ['href', 'rel', 'target'], img: ['src', 'alt', 'width', 'height'],
    th: ['colspan', 'rowspan', 'scope'], td: ['colspan', 'rowspan', 'scope'],
    ol: ['start', 'reversed', 'type'], li: ['value'], col: ['span'], colgroup: ['span'],
};

function rasterDataUrl(value) {
    const match = /^data:image\/(png|jpeg|gif|webp);base64,([a-z0-9+/]+={0,2})$/i.exec(value);
    if (!match || match[2].length > 28_000_000) return false;
    try {
        const bytes = atob(match[2]);
        if (match[1].toLowerCase() === 'png') return bytes.startsWith('\x89PNG\r\n\x1a\n');
        if (match[1].toLowerCase() === 'jpeg') return bytes.startsWith('\xff\xd8\xff');
        if (match[1].toLowerCase() === 'gif') return /^GIF8[79]a/.test(bytes);
        return bytes.startsWith('RIFF') && bytes.slice(8, 12) === 'WEBP';
    } catch { return false; }
}

function safeUrl(value, image) {
    const normalized = value.trim();
    if (image && normalized.toLowerCase().startsWith('data:')) return rasterDataUrl(normalized);
    // No current converter registers application-created blob URLs. Reject all
    // supplied blobs until a real owner/lifetime registry exists.
    try {
        const url = new URL(normalized, window.location.href);
        const explicit = /^[a-z][a-z0-9+.-]*:/i.test(normalized);
        if (!image && explicit && url.protocol === 'mailto:') return true;
        if (!['https:', 'http:'].includes(url.protocol)) return false;
        return image || !explicit ? url.origin === window.location.origin : true;
    } catch { return false; }
}

function filterAttribute(node, data) {
    const tag = node.nodeName.toLowerCase();
    const name = data.attrName.toLowerCase();
    if (!globalAttributes.has(name) && !(attributes[tag] || []).includes(name)) {
        data.keepAttr = false;
        return;
    }
    if (name === 'href' || name === 'src') data.keepAttr = safeUrl(data.attrValue, name === 'src');
    if (name === 'target') data.keepAttr = ['_blank', '_self'].includes(data.attrValue);
    if (name === 'dir') data.keepAttr = ['ltr', 'rtl', 'auto'].includes(data.attrValue);
    if (name === 'lang') data.keepAttr = /^[a-z]{2,8}(?:-[a-z0-9]{1,8})*$/i.test(data.attrValue);
    if (name === 'scope') data.keepAttr = ['row', 'col', 'rowgroup', 'colgroup'].includes(data.attrValue);
    if (name === 'type') data.keepAttr = ['1', 'a', 'A', 'i', 'I'].includes(data.attrValue);
    if (['width', 'height', 'colspan', 'rowspan', 'span', 'start', 'value'].includes(name)) {
        const number = Number(data.attrValue);
        const dimension = ['width', 'height'].includes(name);
        const signed = ['start', 'value'].includes(name);
        data.keepAttr = /^-?\d+$/.test(data.attrValue) && Number.isSafeInteger(number)
            && number >= (signed ? -2147483648 : 1)
            && number <= (signed ? 2147483647 : dimension ? 10000 : 1000);
    }
}
purifier.addHook('uponSanitizeAttribute', filterAttribute);
purifier.addHook('afterSanitizeAttributes', node => {
    if (node.nodeName.toLowerCase() === 'a') node.setAttribute('rel', 'noopener noreferrer');
});

export function sanitizePreviewHtml(html) {
    return purifier.sanitize(String(html), {
        ALLOWED_TAGS: tags,
        ALLOWED_ATTR: [...globalAttributes, ...new Set(Object.values(attributes).flat())],
        ALLOWED_NAMESPACES: ['http://www.w3.org/1999/xhtml'],
        ALLOW_DATA_ATTR: false,
        ALLOW_ARIA_ATTR: false,
        FORBID_TAGS: ['script', 'style', 'form', 'iframe', 'object', 'embed', 'svg', 'math'],
        FORBID_ATTR: ['style', 'id', 'name'],
    });
}

// The application table has trusted badges and decorative SVGs; uploaded
// document HTML continues to use the stricter, SVG-free profile above.
const tablePurifier = createDOMPurify(window);
const tableClasses = new Set(['table-cell-main', 'table-cell-icon', 'table-cell-text',
    'table-cell-muted', 'table-empty', 'lang-pair', 'link', 'status-pill',
    'status-pill--pending', 'status-pill--reviewed', 'status-pill--verified',
    'status-pill--flagged', 'quality-badge', 'quality-badge--empty', 'quality-badge__dot']);
const svgAttributes = ['width', 'height', 'viewbox', 'fill', 'stroke', 'stroke-width',
    'stroke-linecap', 'stroke-linejoin', 'd', 'points', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r'];
tablePurifier.addHook('uponSanitizeAttribute', (node, data) => {
    const name = data.attrName.toLowerCase();
    if (name === 'class') {
        data.attrValue = data.attrValue.split(/\s+/).filter(value => tableClasses.has(value)).join(' ');
        data.keepAttr = !!data.attrValue;
        return;
    }
    if (name === 'aria-hidden') { data.keepAttr = data.attrValue === 'true'; return; }
    if (name === 'aria-label') return;
    if (name === 'role') { data.keepAttr = data.attrValue === 'img'; return; }
    if (node.namespaceURI === 'http://www.w3.org/2000/svg') {
        const value = data.attrValue;
        data.keepAttr = svgAttributes.includes(name) && value.length <= 10000 &&
            (['fill', 'stroke'].includes(name) ? ['none', 'currentColor'].includes(value) :
                ['stroke-linecap', 'stroke-linejoin'].includes(name) ? ['round', 'butt', 'square', 'miter', 'bevel'].includes(value) :
                    name === 'd' ? /^[MmLlHhVvCcSsQqTtAaZz0-9.,+\- eE]+$/.test(value) :
                        /^[0-9.,+\- eE]+$/.test(value));
        return;
    }
    filterAttribute(node, data);
});
tablePurifier.addHook('afterSanitizeAttributes', node => {
    if (node.nodeName.toLowerCase() === 'a') node.setAttribute('rel', 'noopener noreferrer');
});

export function sanitizeDashboardRows(html) {
    // A table context is required: parsing bare tr/td markup as a document
    // silently discards row structure before the sanitizer can preserve it.
    const fragment = tablePurifier.sanitize('<table><tbody>' + String(html) + '</tbody></table>', {
        ALLOWED_TAGS: [...tags, 'svg', 'path', 'line', 'polyline', 'circle'],
        ALLOWED_ATTR: [...globalAttributes, ...new Set(Object.values(attributes).flat()),
            'class', 'role', 'aria-label', 'aria-hidden', ...svgAttributes],
        ALLOW_DATA_ATTR: false,
        FORBID_TAGS: ['script', 'style', 'form', 'iframe', 'object', 'embed', 'math', 'foreignObject', 'animate', 'use'],
        FORBID_ATTR: ['style', 'id', 'name'],
        RETURN_DOM_FRAGMENT: true,
    });
    return fragment.querySelector('tbody') || document.createElement('tbody');
}
