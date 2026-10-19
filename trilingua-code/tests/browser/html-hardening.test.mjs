import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const { build } = require('esbuild');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const snapshot = process.env.TRILINGUA_SOURCE_SNAPSHOT;
const source = name => readFileSync(resolve(snapshot || root, name), 'utf8');
const layout = source('resources/views/layouts/app.blade.php');
const admin = source('resources/views/admin/review-document.blade.php');
const dashboard = source('resources/views/dashboard.blade.php');
const toast = layout.slice(layout.indexOf('window.showToast = function'), layout.indexOf('// ── Global error modal'));
const load = layout.indexOf('function load() {');
const notificationStart = layout.indexOf('var fragment =', load) >= 0 ? layout.indexOf('var fragment =', load) : layout.indexOf("var html = '';", load);
const notification = layout.slice(notificationStart, layout.indexOf('function openNotification', load));
const regenStart = admin.indexOf('var published =') >= 0 ? admin.indexOf('var published =') : admin.indexOf("var html =\n                    '<div class=\"regen-result\">'");
const regen = admin.slice(regenStart, (admin.indexOf('result.replaceChildren(published);', regenStart) >= 0 ? admin.indexOf('result.replaceChildren(published);', regenStart) + 'result.replaceChildren(published);'.length : admin.indexOf('result.innerHTML = html;', regenStart) + 'result.innerHTML = html;'.length));
const refresh = dashboard.slice(dashboard.indexOf('document.querySelectorAll(\'.kpi-card__value\')'), dashboard.indexOf('\n            })', dashboard.indexOf('// Update recent translations')));
let browser, server, origin;
before(async () => {
    const bundle = (await build({ stdin: { contents: `import './resources/js/app.js'; import './resources/js/document-preview.js';
        import {sanitizePreviewHtml} from './resources/js/preview-sanitizer.js'; window.sanitizePreviewHtml = sanitizePreviewHtml;`, resolveDir: root },
        bundle: true, write: false, format: 'iife', plugins: snapshot ? [{ name: 'snapshot', setup(b) {
            b.onLoad({filter: /resources[\\/]js[\\/]/}, args => {
                const p = resolve(snapshot, args.path.slice(root.length + 1));
                if (existsSync(p)) return { contents: readFileSync(p, 'utf8'), loader: 'js' };
            });
        }}] : [] })).outputFiles[0].text;
    server = createServer((req, res) => {
        res.setHeader('Content-Type', req.url === '/bundle.js' ? 'text/javascript' : 'text/html');
        res.end(req.url === '/bundle.js' ? bundle : '<!doctype html><script src="/bundle.js"></script><div id="toast-container"></div><div id="list"></div><div id="result"></div><div class="kpi-card__value">0</div><table class="table"><tbody></tbody></table>');
    });
    await new Promise(done => server.listen(0, '127.0.0.1', done));
    origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({channel: 'chrome', headless: true});
});
after(async () => { await browser?.close(); if(server) await new Promise(done => server.close(done)); });
for (const kind of ['toast', 'notification', 'regeneration', 'dashboard KPI', 'dashboard table']) {
    test(`${kind}: actual renderer treats harmless attack marker as inert content`, async () => {
        const page = await browser.newPage();
        try {
            await page.route('**/fixture-error', r => r.fulfill({status:404, body:''}));
            await page.goto(origin);
            const result = await page.evaluate(({kind,toast,notification,regen,refresh}) => {
                const payload = '<img src="/fixture-error" onerror="window.phase1Executed=1">';
                if(kind === 'toast') { (0,eval)(toast); showToast('success', payload, payload, 10000); }
                if(kind === 'notification') new Function('items','list',notification)([{id:'x" onmouseover="window.phase1Executed=1',url:'javascript:window.phase1Executed=1',data:{title:payload,source_language:payload,target_language:'Cebuano'}}],document.getElementById('list'));
                if(kind === 'regeneration') new Function('data','result',regen)({new_download_url:'javascript:window.phase1Executed=1',original_download_url:'/safe',new_download_filename:payload,edited_blocks:payload}, document.getElementById('result'));
                if(kind.startsWith('dashboard')) {
                    const doc = new DOMParser().parseFromString(`<div class="kpi-card__value">5${kind.endsWith('KPI') ? payload : ''}</div><table class="table"><tbody><tr><td>${kind.endsWith('table') ? payload : 'Safe'}</td></tr></tbody></table>`, 'text/html');
                    new Function('doc', refresh)(doc);
                }
                return {active:document.querySelectorAll('[onerror],[onmouseover],a[href^="javascript:"]').length,
                    icon:document.querySelectorAll('#toast-container svg, #list .notif-item__icon').length};
            },{kind,toast,notification,regen,refresh});
            await page.waitForTimeout(150);
            assert.equal(await page.evaluate(() => window.phase1Executed || 0), 0);
            assert.equal(result.active, 0);
            if(['toast','notification'].includes(kind)) assert.ok(result.icon > 0);
        } finally {await page.close();}
    });
}
test('sanitizer retains only safe targets and adds both rel protections', async () => {
    const page=await browser.newPage();
    try {await page.goto(origin); const links=await page.evaluate(() => {
        const el=document.createElement('div'); el.innerHTML=window.sanitizePreviewHtml('<a href="/safe" target="_blank" rel="opener">safe</a><a href="/safe" target="named">named</a>');
        return [...el.querySelectorAll('a')].map(a=>[a.getAttribute('target'),a.rel]);
    });assert.deepEqual(links,[['_blank','noopener noreferrer'],[null,'noopener noreferrer']]);} finally {await page.close();}
});

test('regeneration retains signed storage downloads while notifications stay same-origin', async () => {
    const page = await browser.newPage();
    try {
        await page.goto(origin);
        const result = await page.evaluate(regen => {
            const host = document.getElementById('result');
            new Function('data','result',regen)({new_download_url:'https://storage.example.test/file?token=abc&x=1',new_download_filename:'Worksheet.xlsx',original_download_url:'/original'},host);
            return {links:[...host.querySelectorAll('a')].map(a=>a.getAttribute('href')),
                notification:window.safeAppUrl('https://storage.example.test/file'),
                unsafe:window.safeAppUrl('javascript:window.phase1Executed=1',true),fragment:window.safeAppUrl('#')};
        },regen);
        assert.match(result.links[0],/^https:\/\/storage\.example\.test\/file\?token=abc&x=1$/);
        assert.equal(result.notification,'#');assert.equal(result.unsafe,'#');assert.equal(result.fragment,'#');
    } finally { await page.close(); }
});

test('dashboard sanitization retains table rows and trusted badges/icons', async () => {
    const page = await browser.newPage();
    try {
        await page.goto(origin);
        const result = await page.evaluate(refresh => {
            const doc = new DOMParser().parseFromString('<table class="table"><tbody><tr><td class="table-cell-main"><div class="table-cell-icon"><svg width="16" height="16" viewBox="0 0 24 24" onload="window.phase1Executed=1"><path d="M1 2L3 4"/></svg></div><a href="/safe">Worksheet</a></td><td><span class="status-pill status-pill--pending" onclick="window.phase1Executed=1">Pending</span></td></tr></tbody></table>', 'text/html');
            new Function('doc',refresh)(doc);
            return {rows:document.querySelectorAll('.table tbody tr').length,
                badge:document.querySelectorAll('.status-pill--pending').length,
                icons:document.querySelectorAll('.table-cell-icon svg').length,
                active:document.querySelectorAll('.table [onload],.table [onclick]').length};
        }, refresh);
        assert.deepEqual(result,{rows:1,badge:1,icons:1,active:0});
    } finally { await page.close(); }
});
