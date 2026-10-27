import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
test('strict report-only script policy records violations while existing behavior runs',async()=>{
    const server=createServer((req,res)=>{
        res.setHeader('Content-Type','text/html');
        res.setHeader('Content-Security-Policy-Report-Only',"script-src 'self'; script-src-attr 'none';");
        res.end('<!doctype html><script>window.inlineRan=1; eval("window.evalRan=1")</script><button onclick="window.handlerRan=1">Test</button>');
    });
    await new Promise(done=>server.listen(0,'127.0.0.1',done));
    const browser=await chromium.launch({channel:'chrome',headless:true});
    try{
        const page=await browser.newPage();
        await page.addInitScript(()=>{window.violations=[];document.addEventListener('securitypolicyviolation',e=>window.violations.push({directive:e.effectiveDirective,disposition:e.disposition,blocked:e.blockedURI}));});
        await page.goto(`http://127.0.0.1:${server.address().port}`);await page.locator('button').click();await page.waitForTimeout(100);
        const result=await page.evaluate(()=>({inline:inlineRan,eval:evalRan,handler:handlerRan,violations}));
        assert.equal(result.inline,1);assert.equal(result.eval,1);assert.equal(result.handler,1);
        assert.ok(result.violations.some(v=>v.directive==='script-src-elem'));
        assert.ok(result.violations.some(v=>v.directive==='script-src-attr'));
        assert.ok(result.violations.some(v=>v.blocked==='eval'));
        assert.ok(result.violations.every(v=>v.disposition==='report'));
    } finally {await browser.close();await new Promise(done=>server.close(done));}
});
