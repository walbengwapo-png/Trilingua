import './bootstrap';
import { sanitizePreviewHtml, sanitizeDashboardRows } from './preview-sanitizer';

window.sanitizePreviewHtml = sanitizePreviewHtml;
window.sanitizeDashboardRows = sanitizeDashboardRows;
window.safeAppUrl = function (value, allowExternal = false) {
    if (value === '#') return '#';
    try {
        const url = new URL(String(value || ''), window.location.href);
        return ['http:', 'https:'].includes(url.protocol)
            && (url.origin === location.origin || allowExternal) ? url.href : '#';
    } catch { return '#'; }
};
