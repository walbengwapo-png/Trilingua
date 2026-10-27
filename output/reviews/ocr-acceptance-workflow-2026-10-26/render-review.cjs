const {chromium}=require('C:/Users/walbe/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1200,height:1000}});
  const failures=[];page.on('requestfailed',r=>failures.push(r.url()));
  await page.goto('file:///C:/dev/Trilingua/output/ocr-acceptance/lion-mouse-review-2026-10-26/review.html');
  const result={pages:await page.locator('svg').count(),regions:await page.locator('svg rect').count(),candidate_text_regions:await page.locator('li').count(),failed_requests:failures};
  if(result.pages!==2||result.regions!==8||failures.length)throw Error(JSON.stringify(result));
  await page.screenshot({path:'C:/dev/Trilingua/output/reviews/ocr-acceptance-workflow-2026-10-26/review-preview.png'});
  fs.writeFileSync('C:/dev/Trilingua/output/reviews/ocr-acceptance-workflow-2026-10-26/review-visual-check.json',JSON.stringify(result,null,2));
  process.stdout.write(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(error=>{process.stderr.write(String(error));process.exitCode=1;});

