import assert from 'node:assert/strict';
import {test,before,after} from 'node:test';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const {chromium}=require(process.env.TRILINGUA_PLAYWRIGHT_MODULE || 'playwright');
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
let browser;
before(async()=>{browser=await chromium.launch({channel:'chrome',headless:true});});
after(async()=>{await browser?.close();});

function translationHtml(){
    const source=readFileSync(resolve(root,'resources/views/translation.blade.php'),'utf8');
    const body=source.slice(source.indexOf("@section('content')")+"@section('content')".length,source.lastIndexOf('@endsection'));
    const capabilities={languages:['English','Cebuano','Filipino'],modes:['fast','balanced','thorough'],
        text_max_chars:5000,formats:['pdf'],accept:'.pdf',max_upload_bytes:10_000_000,pdf_column_modes:['auto','left','right']};
    return execFileSync('php',['-r',`require 'vendor/autoload.php'; $app=require 'bootstrap/app.php';
        $app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
        $input=json_decode(file_get_contents('php://stdin'),true);echo Illuminate\\Support\\Facades\\Blade::render($input['source'],['capabilities'=>$input['capabilities']]);`],
        {cwd:root,input:JSON.stringify({source:body,capabilities}),env:{...process.env,APP_ENV:'testing',DB_CONNECTION:'sqlite',DB_DATABASE:':memory:',DB_URL:''}}).toString();
}

for(const preview of [false,true]){
    test(`PDF OCR preview is opt-in and forwarded (${preview})`,async()=>{
        const page=await browser.newPage();let posted='';
        await page.route('**/*',async route=>{
            const url=new URL(route.request().url());
            if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:`<meta name="csrf-token" content="test">${translationHtml()}`});
            if(url.pathname==='/translate'){
                posted=route.request().postDataBuffer().toString();
                return route.fulfill({json:{status:'completed',download_url:'/download',
                    content_summary:{status:'complete',translated:1,held:0,...(preview?{ocr_mode:'preview',ocr_verified:false}:{})}}});
            }
            return route.abort();
        });
        try{
            await page.goto('https://hybrid.test/');
            assert.equal(await page.locator('#ocr-preview').isChecked(),false);
            await page.locator('#file-input').setInputFiles(resolve(root,'tests/testPDFs/M1_Q1_ENGLISH 8.pdf'));
            assert.equal(await page.locator('#ocr-preview-option').isVisible(),true);
            if(preview)await page.locator('#ocr-preview').check();
            await page.locator('#translate-btn').click();
            await page.waitForFunction(()=>!document.querySelector('#output-download').hidden);
            assert.match(posted,new RegExp(`name="ocr_mode"\\r\\n\\r\\n${preview?'preview':'strict'}`));
            if(preview)assert.match(await page.locator('#output-text').innerText(),/Unverified OCR preview/);
            await page.locator('#remove-file').click();
            assert.equal(await page.locator('#ocr-preview').isChecked(),false);
        }finally{await page.close();}
    });
}

for(const status of ['partial','untranslated']){
    test(`actual completion UI labels ${status} and original-language holds`,async()=>{
        const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
        const summary={status,translated:status==='partial'?1:0,held:2,passthrough:0};
        const html=translationHtml();
        await page.route('**/*',async route=>{
            const url=new URL(route.request().url());
            if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:`<meta name="csrf-token" content="test">${html}`});
            if(url.pathname==='/translate')return route.fulfill({json:{status:'processing',job_id:'fixed-ui-job'}});
            if(url.pathname==='/translate/status/fixed-ui-job')return route.fulfill({json:{status:'completed',
                content_summary:summary,warnings:['Held regions retain original content.'],download_url:'/download',download_filename:`result_${status}.pdf`}});
            return route.abort();
        });
        try{
            await page.goto('https://hybrid.test/');
            await page.locator('#file-input').setInputFiles(resolve(root,'tests/testPDFs/M1_Q1_ENGLISH 8.pdf'));
            await page.locator('#translate-btn').click();
            await page.waitForFunction(()=>document.querySelector('#output-text').textContent.includes('held regions'));
            const text=await page.locator('#output-text').innerText();
            assert.match(text,new RegExp(status));assert.match(text,/original language/);
            assert.match(await page.locator('#workbook-warning').innerText(),/original content/);
            assert.equal(await page.locator('#download-link').getAttribute('download'),`result_${status}.pdf`);
            assert.doesNotMatch(text,/Your document has been translated/);assert.deepEqual(errors,[]);
        }finally{await page.close();}
    });
}

for(const status of ['partial','untranslated']){
    test(`unavailable download retains ${status} content warnings`,async()=>{
        const page=await browser.newPage();
        const html=translationHtml();
        await page.route('**/*',async route=>{
            const url=new URL(route.request().url());
            if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:`<meta name="csrf-token" content="test">${html}`});
            if(url.pathname==='/translate')return route.fulfill({json:{status:'processing',job_id:'held-job'}});
            if(url.pathname==='/translate/status/held-job')return route.fulfill({json:{status:'completed',download_available:false,
                content_summary:{status,translated:status==='partial'?1:0,held:2,passthrough:0},
                warnings:['Held regions retain original content.'],message:'Download temporarily unavailable.'}});
            return route.abort();
        });
        try{
            await page.goto('https://hybrid.test/');
            await page.locator('#file-input').setInputFiles(resolve(root,'tests/testPDFs/M1_Q1_ENGLISH 8.pdf'));
            await page.locator('#translate-btn').click();
            await page.waitForFunction(()=>document.querySelector('#output-text').textContent.includes('Download temporarily unavailable.'));
            const text=await page.locator('#output-text').innerText();
            assert.match(text,new RegExp(status));assert.match(text,/2 held regions/);
            assert.match(await page.locator('#workbook-warning').innerText(),/original content/);
            assert.doesNotMatch(await page.locator('#translate-progress-stage').innerText(),/Translation complete/);
            assert.equal(await page.locator('#output-download').getAttribute('hidden'),'');
        }finally{await page.close();}
    });
}
