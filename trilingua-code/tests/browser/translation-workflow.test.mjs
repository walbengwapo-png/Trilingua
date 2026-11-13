import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const template = readFileSync(new URL('../../resources/views/translation.blade.php', import.meta.url), 'utf8');
const source = template.match(/<script>([\s\S]*?)<\/script>/)[1];
const job = '40872971-81cc-4f22-9196-d8567ba459a4';
const flush = () => new Promise(resolve => setImmediate(resolve));

function screen({ initial = null, replies = [], stored = {}, viewer = 1 } = {}) {
    const key = `trilingua.active_document_job.${viewer}`;
    const storage = new Map(Object.entries(stored));
    const elements = new Map(), calls = [], timers = new Map();
    const state = { now: 1_000_000 };
    class Element {
        constructor(id) {
            this.id = id; this.attributes = {}; this.events = {}; this.style = {}; this.dataset = {};
            this.files = []; this.textContent = ''; this.disabled = false; this.hidden = false;
            this.options = []; this._value = '';
            const names = new Set();
            this.classList = { add: n => names.add(n), remove: n => names.delete(n), contains: n => names.has(n),
                toggle: (n, on = !names.has(n)) => on ? names.add(n) : names.delete(n) };
        }
        get value() { return this._value; }
        set value(v) { this._value = v; if (this.id === 'file-input' && v === '') this.files = []; }
        addEventListener(type, fn) { (this.events[type] ||= []).push(fn); }
        emit(type) { for (const fn of this.events[type] || []) fn({ preventDefault() {} }); }
        click() { if (!this.disabled) this.emit('click'); }
        getAttribute(k) { return this.attributes[k] ?? null; }
        setAttribute(k, v) { this.attributes[k] = v; if (k === 'hidden') this.hidden = true; }
        removeAttribute(k) { delete this.attributes[k]; if (k === 'href') this.href = ''; if (k === 'hidden') this.hidden = false; }
        setSelectionRange() {}
    }
    for (const match of template.matchAll(/<[^>]+id="([^"]+)"[^>]*>/g)) {
        const el = new Element(match[1]);
        el.hidden = /\bhidden\b/.test(match[0]);
        elements.set(el.id, el);
    }
    const get = id => { assert.ok(elements.has(id), `Missing DOM element: ${id}`); return elements.get(id); };
    for (const id of ['source-lang', 'target-lang']) {
        get(id).options = ['English', 'Cebuano', 'Filipino'].map(value => ({ value }));
    }
    get('source-lang').value = 'English'; get('target-lang').value = 'Cebuano';
    get('source-text').value = 'Water';
    const window = { location: { href: 'https://trilingua.test/translate' }, addEventListener() {},
        history: { replaceState(_state, _title, url) { window.location.href = url; } } };
    const values = {
        CAPABILITIES: { text_max_chars: 8000, formats: ['txt', 'docx', 'pdf'], max_upload_bytes: 52428800 },
        INITIAL_JOB: initial, JOB_STORAGE_KEY: key,
        ROUTES: { submit: '/translate', status: '/translate/status/__JOB__', track: '/translate?job=__JOB__', login: '/login' },
        CONTENT_MESSAGES: {}, PREVIEW_MESSAGE: 'Experimental preview.', REASON_MESSAGES: {}, UNKNOWN_REASON_MESSAGE: 'Check the document.'
    };
    const script = source.replace(/var (\w+) = @json\([^\n]+\);/g, (_match, name) => {
        assert.ok(name in values, `Unreviewed template variable ${name}`);
        return `var ${name} = ${JSON.stringify(values[name])};`;
    });
    const context = {
        window, document: { hidden: false, getElementById: get, addEventListener() {}, querySelector: () => ({ content: 'test-only-csrf' }) },
        sessionStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
        fetch(url, options) {
            calls.push({ url, options });
            if (!replies.length) return new Promise(() => {});
            const [status, body] = replies.shift();
            return Promise.resolve({ status, ok: status >= 200 && status < 300, text: () => Promise.resolve(JSON.stringify(body)) });
        },
        FormData: class { append() {} }, URL, navigator: {},
        Date: class extends Date { static now() { return state.now; } },
        setTimeout(fn) { const id = Symbol(); timers.set(id, fn); return id; }, clearTimeout: id => timers.delete(id),
        setInterval: () => 1, clearInterval() {}
    };
    vm.runInNewContext(script, context);
    return { get, calls, storage, key, window, state, timers, nextPoll() {
        const [id, fn] = timers.entries().next().value; timers.delete(id); fn();
    } };
}

test('pending submit remains labeled, blocks duplicate clicks and removes stale download actions', () => {
    const ui = screen();
    ui.get('download-link').href = '/old-file'; ui.get('output-download').hidden = false;
    ui.get('translate-btn').emit('click'); ui.get('translate-btn').emit('click');
    assert.equal(ui.calls.length, 1);
    assert.equal(ui.get('translate-btn').disabled, true);
    assert.match(ui.get('translate-btn-label').textContent, /Sending request/);
    assert.equal(ui.get('output-download').hidden, true);
    assert.equal(ui.get('download-link').href, '');
});

test('queued acceptance exposes the owned tracking URL and blocks a second translation', async () => {
    const ui = screen({ replies: [[200, { job_id: job, status: 'queued' }], [200, { status: 'queued' }]] });
    ui.get('translate-btn').click(); await flush();
    assert.equal(ui.storage.get(ui.key), job);
    assert.equal(ui.get('job-link').href, `/translate?job=${job}`);
    assert.match(ui.window.location.href, new RegExp(`job=${job}`));
    assert.equal(ui.get('translate-progress').hidden, false);
    assert.match(ui.get('translate-progress-stage').textContent, /Queued/);
    assert.equal(ui.get('translate-btn').disabled, true);
    assert.equal(ui.calls.filter(c => c.options.method === 'POST').length, 1);
});

test('server-selected job resumes after refresh and links to the HTML result', async () => {
    const ui = screen({ initial: { id: job }, replies: [[200, { status: 'completed', view_url: '/history/26/view', download_url: '/history/26/file' }]] });
    await flush();
    assert.equal(ui.calls[0].url, `/translate/status/${job}`);
    assert.equal(ui.get('result-link').href, '/history/26/view');
    assert.equal(ui.get('result-link').hidden, false);
    assert.equal(ui.get('download-link').href, '/history/26/file');
    assert.equal(ui.get('output-download').hidden, false);
    assert.equal(ui.get('translate-btn').disabled, false);
    assert.equal(ui.storage.has(ui.key), false);
});

test('expired sessions preserve the job reference and offer sign-in without retrying translation', async () => {
    const ui = screen({ initial: { id: job }, replies: [[401, { message: 'Unauthenticated' }]] });
    await flush();
    assert.equal(ui.storage.get(ui.key), job);
    assert.equal(ui.get('job-link').href, '/login');
    assert.equal(ui.get('job-link').textContent, 'Sign in');
    assert.equal(ui.timers.size, 0);
    assert.equal(ui.calls.length, 1);
});

test('long queued jobs stay described as queued', async () => {
    const ui = screen({ initial: { id: job }, replies: [[200, { status: 'queued' }], [200, { status: 'queued' }]] });
    await flush(); ui.state.now += 601_000; ui.nextPoll(); await flush();
    assert.match(ui.get('translate-progress-stage').textContent, /Still queued/);
    assert.doesNotMatch(ui.get('translate-progress-stage').textContent, /Still translating/);
});

test('completed download uncertainty leaves a result link without inventing a download or blocking new work', async () => {
    const ui = screen({ initial: { id: job }, replies: [[200, { status: 'completed', download_available: false, view_url: '/history/26/view' }]] });
    await flush();
    assert.equal(ui.get('output-download').hidden, true);
    assert.equal(ui.get('result-link').href, '/history/26/view');
    assert.equal(ui.get('translate-btn').disabled, false);
    assert.equal(ui.timers.size, 1);
});

test('another account or the old unscoped browser key cannot choose the job to resume', () => {
    const ui = screen({ viewer: 2, stored: { 'trilingua.active_document_job.1': job, 'trilingua.active_document_job': job } });
    assert.equal(ui.calls.length, 0);
    assert.equal(ui.get('translate-btn').disabled, false);
});

test('an owned conflict follows the existing job instead of resubmitting it', async () => {
    const ui = screen({ replies: [[409, { job_id: job, status: 'processing' }], [200, { status: 'processing' }]] });
    ui.get('translate-btn').click(); await flush();
    assert.equal(ui.calls.length, 2);
    assert.equal(ui.get('translate-btn').disabled, true);
    assert.equal(ui.storage.get(ui.key), job);
});

test('attachment metadata is visible and invalid replacements restore the source input', () => {
    const ui = screen();
    ui.get('file-input').files = [{ name: 'lesson.docx', size: 2048 }]; ui.get('file-input').emit('change');
    assert.equal(ui.get('translate-btn-label').textContent, 'Translate document');
    assert.equal(ui.get('file-size').textContent, '2 KB');
    ui.get('file-input').files = [{ name: 'program.exe', size: 2048 }]; ui.get('file-input').emit('change');
    assert.equal(ui.get('source-text').style.display, '');
    assert.match(ui.get('source-error').textContent, /Unsupported file type/);
    assert.equal(ui.get('translate-btn-label').textContent, 'Translate text');
});

test('swapping languages removes actions for the previous result and keeps the source text', () => {
    const ui = screen();
    ui.get('download-link').href = '/old-file'; ui.get('output-download').hidden = false;
    ui.get('result-link').href = '/history/26/view'; ui.get('result-link').hidden = false;
    ui.get('swap-btn').click();
    assert.equal(ui.get('source-text').value, 'Water');
    assert.equal(ui.get('source-lang').value, 'Cebuano');
    assert.equal(ui.get('output-download').hidden, true);
    assert.equal(ui.get('result-link').hidden, true);
    assert.equal(ui.get('copy-btn').getAttribute('aria-disabled'), 'true');
});
