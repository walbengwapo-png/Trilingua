import assert from 'node:assert/strict';
import { test, before, after } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const { build } = require('esbuild');
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
let browser, appScript;

before(async () => {
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    appScript = (await build({ entryPoints: [resolve(root, 'resources/js/app.js')],
        bundle: true, write: false, format: 'iife' })).outputFiles[0].text;
});
after(async () => { await browser?.close(); });

function historyHtml() {
    const source = readFileSync(resolve(root, 'resources/views/history.blade.php'), 'utf8');
    const body = source.slice(source.indexOf("@section('content')") + "@section('content')".length, source.lastIndexOf('@endsection'));
    return execFileSync('php', ['-r', `require 'vendor/autoload.php'; $app=require 'bootstrap/app.php';
        $app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
        $rows=[];
        foreach ([4,3,2] as $id) $rows[]=['id'=>$id,'translation_type'=>'document','original_filename'=>'File '.$id.'.pdf',
            'translated_filename'=>'Result '.$id.'.pdf','source_language'=>'English','target_language'=>$id===3?'Filipino':'Cebuano',
            'created_at'=>'2026-11-01T0'.$id.':00:00Z','review_status'=>'pending'];
        $filters=['q'=>'','type'=>'','review'=>'','sort'=>'newest','group'=>'none'];
        $records=(new Illuminate\\Pagination\\LengthAwarePaginator($rows,60,50,2))
            ->withPath('http://localhost/history')->appends($filters);
        echo Illuminate\\Support\\Facades\\Blade::render(file_get_contents('php://stdin'),compact('records','filters')+['error'=>false]);`],
    { cwd: root, input: body, env: { ...process.env, APP_ENV: 'testing', DB_CONNECTION: 'sqlite', DB_DATABASE: ':memory:', DB_URL: '' } }).toString();
}

test('history preserves global ordering, submits combined filters without stale page, and displays local time', async () => {
    const context = await browser.newContext({ timezoneId: 'Asia/Manila', locale: 'en-US' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const html = historyHtml();
    await page.route('**/*', route => route.request().url().includes('/history')
        ? route.fulfill({ contentType: 'text/html', body: `<meta name="csrf-token" content="test">${html}<script>${appScript}</script>` })
        : route.abort());
    try {
        await page.goto('http://localhost/history?page=2');
        assert.deepEqual(await page.locator('.history-card').evaluateAll(cards => cards.map(card => card.dataset.id)), ['4', '3', '2']);
        assert.equal(await page.locator('.history-cards').count(), 1);
        assert.equal(await page.locator('#history-group').inputValue(), 'none');
        const firstDate = await page.locator('time[data-local-time]').first().textContent();
        assert.match(firstDate, /12:00 PM/);
        assert.match(firstDate, /GMT\+8/);
        await page.locator('#history-search').fill('rental contract');
        await page.locator('#history-type').selectOption('document');
        await page.locator('#history-status').selectOption('verified');
        await page.locator('#history-sort').selectOption('oldest');
        await Promise.all([page.waitForURL(url => url.searchParams.get('q') === 'rental contract'),
            page.getByRole('button', { name: 'Apply filters' }).click()]);
        const query = new URL(page.url()).searchParams;
        assert.equal(query.get('type'), 'document');
        assert.equal(query.get('review'), 'verified');
        assert.equal(query.get('sort'), 'oldest');
        assert.equal(query.has('page'), false);
        assert.deepEqual(errors, []);
    } finally { await context.close(); }
});
