import './bootstrap';
import { sanitizePreviewHtml, sanitizeDashboardRows } from './preview-sanitizer';

window.sanitizePreviewHtml = sanitizePreviewHtml;
window.sanitizeDashboardRows = sanitizeDashboardRows;
document.querySelectorAll('time[data-local-time]').forEach(function (element) {
    const date = new Date(element.dateTime);
    if (!Number.isNaN(date.getTime())) {
        element.textContent = date.toLocaleString(undefined, {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
        });
    }
});
window.safeAppUrl = function (value, allowExternal = false) {
    if (value === '#') return '#';
    try {
        const url = new URL(String(value || ''), window.location.href);
        return ['http:', 'https:'].includes(url.protocol)
            && (url.origin === location.origin || allowExternal) ? url.href : '#';
    } catch { return '#'; }
};
