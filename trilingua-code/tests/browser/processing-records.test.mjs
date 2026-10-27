import assert from 'node:assert/strict';
import { test, before, after } from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const root=process.env.TRILINGUA_APP_ROOT || resolve(dirname(fileURLToPath(import.meta.url)),'../..');
let browser,server,origin,html='';
before(async()=>{
    server=createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);});
    await new Promise(done=>server.listen(0,'127.0.0.1',done)); origin=`http://127.0.0.1:${server.address().port}`;
    browser=await chromium.launch({channel:'chrome',headless:true});
});
after(async()=>{await browser?.close(); if(server) await new Promise(done=>server.close(done));});

function render(overrides={}) {
    const source=readFileSync(resolve(root,'resources/views/admin/dashboard.blade.php'),'utf8');
    const panel=source.slice(source.indexOf("@if ($engineHealth['samples'] > 0)"),source.indexOf('{{-- Reviewer Leaderboard --}}'));
    const health={samples:2,avg_latency_ms:null,avg_llm_calls:null,cache_hit_rate:null,retranslation_rate:null,
        active_provider:'configured',active_model:'configured-model',legacy_samples:1,measured_samples:1,
        latency_scope:null,latency_samples:0,cache_samples:0,rework_samples:0,attribution_samples:1,
        last_observed_providers:[{provider:'fixture',model:'one'},{provider:'fixture',model:'two'}],
        last_observed_at:'2026-10-19T12:00:00+00:00',
        latest_usage:{input:{value:12,provenance:'provider-reported',method:null},
            output:{value:4,provenance:'estimated',method:'word-proxy-v1'}},...overrides};
    html=execFileSync('php',['-r',`require 'vendor/autoload.php'; $app=require 'bootstrap/app.php';
        $app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
        $data=json_decode($argv[1],true); echo Illuminate\\Support\\Facades\\Blade::render($data['source'],['engineHealth'=>$data['health']]);`,
        JSON.stringify({source:panel,health})],{cwd:root,env:{...process.env,APP_ENV:'testing',DB_CONNECTION:'sqlite',DB_DATABASE:':memory:',DB_URL:''}}).toString();
}

test('actual performance panel labels samples and last observation without live-health claims',async()=>{
    render(); const page=await browser.newPage();
    try {await page.goto(origin); const text=await page.locator('body').innerText();
        assert.match(text,/recorded metric samples/i); assert.match(text,/Last observed provider\/model/i);
        assert.doesNotMatch(text,/Active Provider/); assert.match(text,/fixture/); assert.match(text,/one/); assert.match(text,/two/);
        assert.match(text,/2026-10-19/);
    } finally {await page.close();}
});

test('unknown timing and rate values are unavailable instead of zero or an unlabeled dash',async()=>{
    render(); const page=await browser.newPage();
    try {await page.goto(origin); const text=await page.locator('body').innerText();
        assert.ok((text.match(/Unavailable/g)||[]).length>=3); assert.doesNotMatch(text,/0%/);
        assert.match(text,/legacy/i); assert.match(text,/0.*2|0 of 2/);
    } finally {await page.close();}
});

test('reported and estimated usage stay visibly distinct in the actual panel',async()=>{
    render(); const page=await browser.newPage();
    try {await page.goto(origin); const text=await page.locator('body').innerText();
        assert.match(text,/provider-reported/i); assert.match(text,/estimated/i); assert.match(text,/word-proxy-v1/);
        assert.match(text,/retained translation result/i);
    } finally {await page.close();}
});

test('new provider attribution remains escaped text',async()=>{
    render({last_observed_providers:[{provider:'<img src=x onerror="window.marker=1">',model:'<b>fixture</b>'}]});
    const page=await browser.newPage();
    try {await page.goto(origin); assert.equal(await page.locator('img,[onerror]').count(),0);
        assert.equal(await page.evaluate(()=>window.marker||0),0); assert.match(await page.locator('body').innerText(),/<img/);
    } finally {await page.close();}
});
