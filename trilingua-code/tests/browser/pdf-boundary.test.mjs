import assert from 'node:assert/strict';
import { test, before, after } from 'node:test';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const {chromium}=require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)), '../..');
let browser,server,origin,html='';
before(async()=>{
    server=createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end(html);});
    await new Promise(done=>server.listen(0,'127.0.0.1',done));origin=`http://127.0.0.1:${server.address().port}`;
    browser=await chromium.launch({channel:'chrome',headless:true});
});
after(async()=>{await browser?.close();if(server)await new Promise(done=>server.close(done));});
for(const [file,variable] of [['history-detail.blade.php','translatedUrl'],['history-detail.blade.php','originalUrl'],['admin/review-document.blade.php','previewUrl']]) {
    test(`actual Blade PDF iframe ${file}/${variable} rejects active URLs and escaped attributes`, async()=>{
        for(const value of ['javascript:parent.phase1Executed=1','/safe.pdf" onload="parent.phase1Executed=1','<img src=x onerror="parent.phase1Executed=1">']) {
            const code=`require 'vendor/autoload.php'; $app=require 'bootstrap/app.php'; $app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
                $args=json_decode($argv[1],true); $source=file_get_contents($args['path']); preg_match_all('/<iframe[^>]*><\\/iframe>/', $source,$m);
                foreach($m[0] as $tag) {if(str_contains($tag,'$'.$args['variable'])) echo Illuminate\\Support\\Facades\\Blade::render($tag,[$args['variable']=>$args['value']]);}`;
            html=execFileSync('php',['-r',code,JSON.stringify({path:resolve(process.env.TRILINGUA_SOURCE_SNAPSHOT || root,'resources/views',file),variable,value})],{cwd:root,env:{...process.env,APP_ENV:'testing',DB_CONNECTION:'sqlite',DB_DATABASE:':memory:'}}).toString();
            assert.match(html,/<iframe/);
            const page=await browser.newPage();
            try {await page.goto(origin);await page.waitForTimeout(100);
                assert.equal(await page.evaluate(()=>window.phase1Executed || 0),0);
                assert.equal(await page.locator('iframe[onload],iframe[src^="javascript:"],img').count(),0);
            } finally {await page.close();}
        }
    });
}
