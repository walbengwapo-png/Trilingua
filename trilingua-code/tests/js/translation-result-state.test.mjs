// Unit tests of the real form script using a minimal DOM adapter. No browser,
// web server, external services, or new packages are involved.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';

const blade = fs.readFileSync(new URL('../../resources/views/translation.blade.php', import.meta.url), 'utf8');
const script = blade.match(/<script>\s*([\s\S]*?)<\/script>/)[1].replace(/@json\([^\n]+\);/g, match => {
    if (match.includes('$capabilities')) return JSON.stringify({formats:['pdf','md','docx'],max_upload_bytes:1024000,text_max_chars:8000})+';';
    if (match.includes('STATUS_MESSAGES')) return JSON.stringify({complete:'Complete',partial:'Partly translated'})+';';
    return '"Review required";';
});

class Element {
    constructor() { this.value='';this.textContent='';this.style={};this.hidden=true;this.files=[];this.attrs=new Map();this.listeners={};this.options=[];this.classList={add(){},remove(){},toggle(){}}; }
    addEventListener(name,fn) {(this.listeners[name]??=[]).push(fn);}
    fire(name) {for(const fn of this.listeners[name]??[]) fn({preventDefault(){}});}
    setAttribute(k,v) {this.attrs.set(k,v);if(k==='hidden')this.hidden=true;}
    removeAttribute(k) {this.attrs.delete(k);if(k==='hidden')this.hidden=false;}
    getAttribute(k) {return this.attrs.get(k)??null;}
    set href(v) {this.setAttribute('href',v);} get href() {return this.getAttribute('href');}
    set download(v) {this.setAttribute('download',v);}
}

function form() {
    const elements=new Map();
    const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
    el('source-lang').value='English';el('target-lang').value='Cebuano';
    el('source-text').value='Good morning';
    const requests=[];
    const stored=new Map();
    const context={document:{getElementById:el,querySelector:()=>({content:'test-csrf'}),addEventListener(){},hidden:false},
        window:{addEventListener(){}},sessionStorage:{getItem:k=>stored.get(k)??null,setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},
        fetch:url=>new Promise(resolve=>requests.push({url,reply:data=>resolve({ok:true,status:200,text:()=>Promise.resolve(JSON.stringify(data))})})),
        FormData,Date,setInterval:()=>1,clearInterval(){},setTimeout:()=>1,clearTimeout(){}};
    vm.runInNewContext(script,context);
    return {el,requests};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const docResult={download_url:'/history/1/file?download=1',download_filename:'notes.md',content_summary:{status:'partial'},warnings:['Some text unchanged']};

test('language, file, remove, swap and clear invalidate result links and warnings',async()=>{
    for(const action of ['language','file','remove','swap','clear']) {
        const {el,requests}=form();
        el('translate-btn').fire('click');requests[0].reply(docResult);await settle();
        assert.equal(el('download-link').href,docResult.download_url);
        assert.equal(el('workbook-warning').hidden,false);
        if(action==='language')el('target-lang').fire('change');
        if(action==='file'){el('file-input').files=[{name:'new.pdf',size:10}];el('file-input').fire('change');}
        if(action==='remove')el('remove-file').fire('click');
        if(action==='swap')el('swap-btn').fire('click');
        if(action==='clear')el('clear-btn').fire('click');
        assert.equal(el('download-link').href,null,action);
        assert.equal(el('output-download').hidden,true,action);
        assert.equal(el('workbook-warning').hidden,true,action);
        assert.equal(el('copy-btn').getAttribute('aria-disabled'),'true',action);
    }
});

test('an earlier submission cannot replace the current translation',async()=>{
    const {el,requests}=form();
    el('translate-btn').fire('click');
    el('target-lang').value='Filipino';el('target-lang').fire('change');
    el('translate-btn').fire('click');
    requests[1].reply({translated:'Magandang umaga',saved:true});await settle();
    requests[0].reply(docResult);await settle();
    assert.equal(el('output-text').textContent,'Magandang umaga');
    assert.equal(el('download-link').href,null);
    assert.equal(el('workbook-warning').hidden,true);
    assert.equal(el('translate-btn').disabled,false);
});

test('an earlier polling response cannot restore a stale download',async()=>{
    const {el,requests}=form();
    el('translate-btn').fire('click');
    requests[0].reply({job_id:'old-job',status:'processing'});await settle();
    assert.equal(requests[1].url,'/translate/status/old-job');
    el('source-text').value='New text';el('source-text').fire('input');
    el('translate-btn').fire('click');requests[2].reply({translated:'New result',saved:true});await settle();
    requests[1].reply({...docResult,status:'completed'});await settle();
    assert.equal(el('output-text').textContent,'New result');
    assert.equal(el('download-link').href,null);
});
