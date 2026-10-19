// Uses installed Chrome and Playwright (or TRILINGUA_PLAYWRIGHT_MODULE).
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const { build } = require('esbuild');
const JSZip = require(require.resolve('jszip', { paths: [dirname(require.resolve('mammoth'))] }));
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
let browser, server, origin, bundle;

before(async () => {
    bundle = (await build({ stdin: { contents: `import './resources/js/document-preview.js';
        import {sanitizePreviewHtml} from './resources/js/preview-sanitizer.js';
        window.testPreviewSanitize = sanitizePreviewHtml;`, resolveDir: root },
        bundle: true, write: false, platform: 'browser', format: 'iife' })).outputFiles[0].text;
    server = createServer((req, res) => {
        if (req.url === '/preview.js') {
            res.setHeader('Content-Type', 'text/javascript'); res.end(bundle);
        } else {
            res.setHeader('Content-Type', 'text/html');
            res.end('<!doctype html><meta charset="utf-8"><script src="/preview.js"></script><div id="preview"></div>');
        }
    });
    await new Promise(done => server.listen(0, '127.0.0.1', done));
    origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({ channel: process.env.TRILINGUA_BROWSER_CHANNEL || 'chrome', headless: true });
});
after(async () => {
    await browser?.close();
    if (server) await new Promise(done => server.close(done));
});

async function docxWithLinks() {
    const zip = new JSZip();
    zip.file('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>');
    zip.file('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>');
    zip.file('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:hyperlink r:id="bad"><w:r><w:t>Unsafe fixture link</w:t></w:r></w:hyperlink></w:p><w:p><w:hyperlink r:id="good"><w:r><w:t>Safe fixture link</w:t></w:r></w:hyperlink></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Worksheet table</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>');
    zip.file('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="bad" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="javascript:void(0)" TargetMode="External"/><Relationship Id="good" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/lesson" TargetMode="External"/></Relationships>');
    return zip.generateAsync({ type: 'nodebuffer' });
}

async function mount(ext, bytes, attributes = {}) {
    const page = await browser.newPage();
    await page.route('**/fixture', route => route.fulfill({ body: bytes }));
    await page.route('**/blocks', route => route.fulfill({ json: { blocks: [
        { block_index: 0, block_type: 'paragraph', source_text: '<img src=x onerror="alert(1)">', current_text: 'Saved <script>text</script>' },
    ] } }));
    await page.goto(origin);
    await page.evaluate(({ ext, attributes }) => {
        const host = document.getElementById('preview');
        host.setAttribute('data-ext', ext); host.setAttribute('data-file-url', '/fixture');
        for (const [key, value] of Object.entries(attributes)) host.setAttribute(key, value);
        window.documentPreview.mount(host);
    }, { ext, attributes });
    await page.waitForFunction(() => !document.querySelector('#preview .review-pane__loading'));
    return page;
}

test('real DOCX conversion removes unsafe links and retains safe content in the shared renderer', async () => {
    const page = await mount('docx', await docxWithLinks());
    try {
        assert.equal(await page.locator('a[href^="javascript:"]').count(), 0);
        assert.equal(await page.locator('a[href="https://example.com/lesson"]').count(), 1);
        assert.match(await page.locator('#preview').innerText(), /Worksheet table/);
    } finally { await page.close(); }
});

test('policy removes active markup and enforces element-specific attributes', async () => {
    const page = await browser.newPage();
    try {
        await page.goto(origin);
        const result = await page.evaluate(() => {
            const host = document.getElementById('preview');
            host.innerHTML = window.testPreviewSanitize(`<script>window.bad=1</script><svg onload="window.bad=1"></svg>
                <math><mtext>bad</mtext></math><form><input autofocus></form><iframe srcdoc="bad"></iframe>
                <h2 id="clobber" style="color:red" onclick="window.bad=1" data-x="1" aria-label="bad" title="Lesson">Lesson</h2>
                <table><tr><th scope="col" colspan="2">Title</th><td colspan="999999" href="/wrong">Value</td></tr></table>
                <ol start="2" type="a"><li value="3">Item</li></ol>`);
            return { html: host.innerHTML, bad: window.bad || 0,
                forbidden: host.querySelectorAll('script,svg,math,form,input,iframe,[id],[style],[onclick],[data-x],[aria-label],td[href]').length,
                colspan: host.querySelector('th').getAttribute('colspan'),
                invalidSpan: host.querySelector('td').hasAttribute('colspan') };
        });
        assert.equal(result.bad, 0);
        assert.equal(result.forbidden, 0);
        assert.equal(result.colspan, '2');
        assert.equal(result.invalidSpan, false);
        assert.match(result.html, /title="Lesson"/);
    } finally { await page.close(); }
});

test('policy rejects encoded unsafe URLs and preserves permitted link forms', async () => {
    const page = await browser.newPage();
    try {
        await page.goto(origin);
        const links = await page.evaluate(() => {
            const host = document.getElementById('preview');
            host.innerHTML = window.testPreviewSanitize(`<a href="jav&#x61;script:alert(1)">bad</a>
                <a href="java&#10;script:alert(1)">bad2</a><a href="data:text/html,bad">bad3</a>
                <a href="https://example.com/lesson">web</a><a href="mailto:teacher@example.com">email</a>
                <a href="/lesson">relative</a><a href="#question">fragment</a><a href="//evil.example/">external relative</a>`);
            return [...host.querySelectorAll('a')].map(a => [a.getAttribute('href'), a.getAttribute('rel')]);
        });
        assert.deepEqual(links.map(x => x[0]), [null, null, null, 'https://example.com/lesson',
            'mailto:teacher@example.com', '/lesson', '#question', null]);
        assert.ok(links.every(x => x[1] === 'noopener noreferrer'));
    } finally { await page.close(); }
});

test('policy allows validated raster data and same-origin images only', async () => {
    const page = await browser.newPage();
    try {
        await page.goto(origin);
        const sources = await page.evaluate(() => {
            const host = document.getElementById('preview');
            const png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==';
            host.innerHTML = window.testPreviewSanitize(`<img src="${png}" alt="pixel"><img src="/image.png">
                <img src="https://evil.example/pixel"><img src="data:image/svg+xml;base64,PHN2Zy8+">
                <img src="data:image/png;base64,PHNjcmlwdD4="><img src="blob:${location.origin}/untracked">`);
            return [...host.querySelectorAll('img')].map(n => n.getAttribute('src'));
        });
        assert.match(sources[0], /^data:image\/png;base64,/);
        assert.deepEqual(sources.slice(1), ['/image.png', null, null, null, null]);
    } finally { await page.close(); }
});

function workbookBytes(cached) {
    const XLSX = require('xlsx');
    const workbook = XLSX.utils.book_new();
    const sheet = { '!ref': 'A1:B1', A1: { t: 'n', f: 'SUM(1,2)', ...(cached ? { v: 3 } : {}) },
        B1: { t: 's', v: 'Worksheet' } };
    XLSX.utils.book_append_sheet(workbook, sheet, 'Lesson');
    return XLSX.write(workbook, { type: 'buffer', bookType: 'xlsx' });
}

test('actual XLSX preview shows uncached formulas and a recalculation notice', async () => {
    const page = await mount('xlsx', workbookBytes(false));
    try {
        const text = await page.locator('#preview').innerText();
        assert.match(text, /=SUM\(1,2\)/);
        assert.match(text, /recalculate/);
        assert.match(text, /Worksheet/);
    } finally { await page.close(); }
});

test('actual XLSX preview keeps a saved calculated result', async () => {
    const page = await mount('xlsx', workbookBytes(true));
    try {
        assert.match(await page.locator('#preview table').innerText(), /3/);
        assert.doesNotMatch(await page.locator('#preview').innerText(), /recalculate/);
    } finally { await page.close(); }
});

test('plain text and CSV content remain escaped', async () => {
    for (const ext of ['txt', 'csv']) {
        const page = await mount(ext, Buffer.from('<img src=x onerror=alert(1)>'));
        try {
            assert.equal(await page.locator('#preview img').count(), 0);
            assert.match(await page.locator('#preview').innerText(), /<img/);
        } finally { await page.close(); }
    }
});

test('unsupported format falls back to escaped saved blocks', async () => {
    const page = await mount('odt', Buffer.from('fixture'), { 'data-blocks-url': '/blocks' });
    try {
        assert.equal(await page.locator('#preview script').count(), 0);
        assert.match(await page.locator('#preview').innerText(), /Saved <script>text<\/script>/);
    } finally { await page.close(); }
});


test('PPTX viewer treats embedded markup and unsafe hyperlink as inert', async () => {
    const page = await mount('pptx', readFileSync(resolve(root, 'tests/fixtures/preview-attack.pptx')));
    try {
        await page.waitForTimeout(800);
        assert.equal(await page.locator('#preview [onerror], #preview a[href^="javascript:"]').count(), 0);
        assert.equal(await page.evaluate(() => window.phase1Executed || 0), 0);
        assert.match(await page.locator('#preview').innerText(), /<img/);
    } finally { await page.close(); }
});

test('fallback/error downloads reject unsafe URLs and protect blank targets', async () => {
    for (const blocks of [false, true]) {
        const page = await mount('odt', Buffer.from('fixture'), {
            'data-file-url': 'javascript:window.phase1Executed=1', ...(blocks ? {'data-blocks-url':'/blocks'} : {})});
        try {
            assert.equal(await page.locator('#preview a[href^="javascript:"]').count(), 0);
            assert.ok((await page.locator('#preview a').evaluateAll(nodes => nodes.map(a => a.rel))).every(rel => rel === 'noopener noreferrer'));
            assert.equal(await page.evaluate(() => window.phase1Executed || 0), 0);
        } finally { await page.close(); }
    }
});
