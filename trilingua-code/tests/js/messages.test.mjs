import test from 'node:test';
import assert from 'node:assert/strict';
import {messageFor, readableMessage, readAppJson, noticeFor, showToast} from '../../resources/js/messages.js';

test('technical document failures become actionable messages with the original reference', () => {
    const id = '11111111-2222-4333-8444-555555555555';
    assert.equal(readableMessage(JSON.stringify({message: 'Saved PDF validation failed: Block 15'})), messageFor('pdf_save_failed').message);
    const text = readableMessage(`Document status is temporarily unavailable. Operator reconciliation is required. Reference: ${id}`);
    assert.ok(text.includes('Do not upload the file again.'));
    assert.ok(text.includes(id));
    assert.ok(!text.includes('Operator'));
    for (const raw of ['SQLSTATE private data', '<html>private data</html>', 'C:\\private\\secret.txt']) {
        assert.equal(readableMessage(raw), messageFor('action_failed').message);
    }
    assert.equal(messageFor('__proto__'), messageFor('action_failed'));
    assert.equal(messageFor('constructor'), messageFor('action_failed'));
});

test('JSON requests distinguish signed-out, throttled, invalid and successful responses', async () => {
    const expired = new Response('<html>sign in</html>', {status: 200});
    Object.defineProperties(expired, {redirected: {value: true}, url: {value: 'https://trilingua.test/login'}});
    await assert.rejects(readAppJson(expired), error => error.status === 401 && error.code === 'sign_in_required');
    await assert.rejects(readAppJson(new Response('<html>bad gateway</html>', {status: 502})),
        error => error.code === 'service_unavailable' && !error.message.includes('<html>'));
    await assert.rejects(readAppJson(new Response(JSON.stringify({code: 'constructor'}), {status: 429})),
        error => error.code === 'rate_limited');
    await assert.rejects(readAppJson(new Response('"unexpected JSON"', {status: 200})));
    const data = {id: 76, translated_text: 'Hello'};
    assert.deepEqual(await readAppJson(new Response(JSON.stringify(data))), data);
});

class Element {
    children = []; dataset = {}; attributes = {}; listeners = {}; textContent = '';
    append(...elements) { this.children.push(...elements); elements.forEach(el => { el.parent = this; }); }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, handler) { this.listeners[name] = handler; }
    remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
}

test('warnings persist, duplicates are suppressed, and text is rendered safely', () => {
    const root = new Element();
    const timers = [];
    const previousDocument = globalThis.document;
    const previousTimer = globalThis.setTimeout;
    globalThis.document = {getElementById: () => root, createElement: () => new Element()};
    globalThis.setTimeout = (fn, delay) => timers.push({fn, delay});
    try {
        showToast('warning', 'Review result', 'Some text remains unchanged.');
        showToast('warning', 'Review result', 'Some text remains unchanged.');
        assert.equal(root.children.length, 1);
        assert.equal(timers.length, 0);
        assert.equal(root.children[0].attributes.role, 'alert');
        root.children[0].children[2].listeners.click();
        assert.equal(root.children.length, 0);
        showToast('success', '<b>unsafe title</b>', 'Saved.');
        assert.equal(root.children[0].children[1].children[0].textContent, '<b>unsafe title</b>');
        assert.equal(root.children[0].attributes.role, 'status');
        assert.equal(timers[0].delay, 5000);
        timers[0].fn();
        assert.equal(root.children.length, 0);
        assert.equal(noticeFor('error', 'Error', 'AI provider is stopped.').title, 'Translation is unavailable');
    } finally {
        globalThis.document = previousDocument;
        globalThis.setTimeout = previousTimer;
    }
});
