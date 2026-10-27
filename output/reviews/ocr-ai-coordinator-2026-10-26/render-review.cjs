const {chromium}=require('C:/Users/walbe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');const path=require('path');
(async()=>{
 const root='C:/dev/Trilingua/output/reviews/ocr-ai-coordinator-2026-10-26';
 const live=JSON.parse(fs.readFileSync(path.join(root,'live-run.json'),'utf8'));
 const folder=live.new_runs[0].replaceAll('\\','/');
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:1000}});const failures=[];
  page.on('requestfailed',r=>failures.push(r.url()));
  await page.goto('file:///'+folder+'/review.html');
  const links=await page.locator('a').evaluateAll(nodes=>nodes.map(n=>n.href));
  if(links.length!==3||failures.length)throw Error(JSON.stringify({links,failures}));
  for(const url of links)if(!fs.existsSync(require('url').fileURLToPath(url)))throw Error('Missing linked file');
  await page.screenshot({path:path.join(root,'coordinator-preview.png'),fullPage:true});
  fs.writeFileSync(path.join(root,'visual-check.json'),JSON.stringify({links,failed_requests:failures},null,2));
  process.stdout.write(JSON.stringify({links,failed_requests:failures}));
 }finally{await browser.close();}
})().catch(e=>{process.stderr.write(String(e));process.exitCode=1;});
