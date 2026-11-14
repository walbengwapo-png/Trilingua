import catalog from '../messages/en.json' with {type: 'json'};

export function messageFor(code) {
    return Object.hasOwn(catalog.messages, code) ? catalog.messages[code] : catalog.messages.action_failed;
}

export function readableMessage(value, fallback = 'action_failed', depth = 0) {
    if (depth > 3) return messageFor(fallback).message;
    if (value && typeof value === 'object') value = value.message || value.error || value.detail;
    if (typeof value !== 'string' || !value.trim()) return messageFor(fallback).message;
    let text = value.trim();
    if (text.startsWith('{')) {
        try { return readableMessage(JSON.parse(text), fallback, depth + 1); }
        catch { return messageFor(fallback).message; }
    }
    for (const rule of catalog.patterns) {
        if (new RegExp(rule.pattern, 'i').test(text)) {
            const reference = text.match(/Reference:\s*([a-f0-9-]{36})\b/i);
            return messageFor(rule.code).message + (reference ? ` Reference: ${reference[1]}` : '');
        }
    }
    return text.length > 600 || text.includes('<') ? messageFor(fallback).message : (Object.hasOwn(catalog.copy, text) ? catalog.copy[text] : text);
}

export function noticeFor(type, title, message) {
    let result = {type, title: Object.hasOwn(catalog.titles, title) ? catalog.titles[title] : title, message: readableMessage(message)};
    for (const rule of catalog.patterns) {
        if (new RegExp(rule.pattern, 'i').test(String(message || ''))) {
            const entry = messageFor(rule.code);
            result = {...result, type: entry.type, title: entry.title};
            break;
        }
    }
    if (!message) result.message = '';
    if (!['success', 'info', 'warning', 'error'].includes(result.type)) result.type = 'info';
    return result;
}

export async function readAppJson(response, fallback = 'action_failed') {
    const raw = await response.text();
    let data;
    try { data = JSON.parse(raw); } catch { data = null; }
    const loginRedirect = response.redirected && new URL(response.url).pathname === '/login';
    if (!response.ok || !data || typeof data !== 'object' || loginRedirect) {
        const statusCodes = {401: 'sign_in_required', 403: 'access_denied', 404: 'page_missing',
            419: 'session_expired', 429: 'rate_limited', 502: 'service_unavailable',
            503: 'service_unavailable', 504: 'service_unavailable'};
        const code = loginRedirect ? 'sign_in_required' : (Object.hasOwn(catalog.messages, data?.code) ? data.code : (statusCodes[response.status] || fallback));
        const error = new Error(readableMessage(data?.error || data?.message || data?.detail, code));
        error.status = loginRedirect ? 401 : response.status;
        error.code = code;
        if (data?.reference && /^[a-f0-9-]{36}$/i.test(data.reference)) error.message += ` Reference: ${data.reference}`;
        throw error;
    }
    return data;
}

export function showToast(type, title, message, duration) {
    const entry = noticeFor(type, title, message);
    const container = document.getElementById('toast-container');
    if (!container) return;
    const key = entry.type + entry.title + entry.message;
    if ([...container.children].some(child => child.dataset.messageKey === key)) return;
    const el = document.createElement('div');
    el.className = `app-notice app-toast app-notice--${entry.type}`;
    el.dataset.messageKey = key;
    el.setAttribute('role', ['error', 'warning'].includes(entry.type) ? 'alert' : 'status');
    const icon = document.createElement('span');
    icon.className = 'app-notice__icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = {success: '\u2713', warning: '!', error: '!', info: 'i'}[entry.type];
    const body = document.createElement('div');
    body.className = 'app-notice__body';
    const heading = document.createElement('strong');
    heading.textContent = entry.title;
    body.append(heading);
    if (entry.message) {
        const text = document.createElement('p');
        text.textContent = entry.message;
        body.append(text);
    }
    const reference = entry.message.match(/Reference:\s*([a-f0-9-]{36})\b/i);
    if (reference) {
        const copy = document.createElement('button');
        copy.type = 'button'; copy.className = 'app-notice__action'; copy.textContent = 'Copy reference';
        copy.addEventListener('click', async () => {
            try { await navigator.clipboard.writeText(reference[1]); copy.textContent = 'Reference copied'; }
            catch { copy.textContent = 'Select and copy the reference above'; }
        });
        body.append(copy);
    }
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'app-notice__close'; close.textContent = '\u00d7';
    close.setAttribute('aria-label', 'Dismiss message'); close.addEventListener('click', () => el.remove());
    el.append(icon, body, close); container.append(el);
    if (['success', 'info'].includes(entry.type) || Number(duration) > 0) {
        setTimeout(() => el.remove(), Number(duration) > 0 ? Number(duration) : 5000);
    }
}
