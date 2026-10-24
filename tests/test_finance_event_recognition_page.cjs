// Full-page regression: real HTML and both real scripts, only synthetic HTTP.
// Requires Playwright and Chromium or installed Edge. No live services used.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CORE_TEST_BROWSER_CHANNEL?{channel:process.env.CORE_TEST_BROWSER_CHANNEL}:{})});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const rule={id:'asn-interest-6607',name:'ASN rente',origin:'ASN',version:'v1',conditions:['ASNBANK + 6607'],result:'Inkomen / Rente'};
  let fail=false;
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());assert.equal(u.hostname,'core.test','No external services');
   const assets={'/corefinance':'finance.html','/coredashboard/assets/finance.js':'finance.js','/coredashboard/assets/finance-recognizer.js':'finance-recognizer.js','/coredashboard/assets/finance.css':'finance.css','/coredashboard/assets/style.css':'style.css'};
   if(assets[u.pathname])return route.fulfill({contentType:u.pathname.endsWith('.js')?'application/javascript':u.pathname.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(__dirname,'../dashboard/static',assets[u.pathname]),'utf8')});
   if(u.pathname==='/api/v1/finance/data')return route.fulfill({json:{accounts:[],groups:[],months:[],periods:[],categories:[],transaction_types:[],transactions:[],imports:[],jobs:[],totals:{total:0,uncategorized:0},unresolved:0,bank_balances:{accounts:[],groups:[],pending:0,total:null}}});
   if(u.pathname==='/api/v1/finance/recognizers')return route.fulfill({json:{rules:[rule]}});
   if(u.pathname==='/api/v1/finance/recognizers/asn-interest-6607/transactions')return route.fulfill(fail?{status:503,json:{detail:'service_unavailable'}}:{json:{mode:'matching',total:0,items:[],counts:{eligible:0,aligned:0,manual:0,manual_conflict:0,protected:0},missing_evidence:0,message:'Synthetische controle'}});
   if(u.pathname==='/api/v1/finance/session')return route.fulfill({json:{status:'locked'}});
   return route.abort();
  });
  await page.goto('http://core.test/corefinance');
  await page.locator('#workspace').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>typeof window.$),'undefined','Finance helpers stay private');
  await page.click('#showEventRecognizer');
  await page.locator('#recognizerStatus').filter({hasText:'0 betalingen passen'}).waitFor();
  assert.equal(await page.locator('#eventRecognizerDialog').evaluate(e=>e.open),true);
  fail=true;await page.click('#recognizerRefresh');await page.locator('#recognizerStatus').filter({hasText:'Dienst tijdelijk niet beschikbaar'}).waitFor();
  fail=false;await page.click('#recognizerRefresh');await page.locator('#recognizerStatus').filter({hasText:'0 betalingen passen'}).waitFor();
  await page.locator('#eventRecognizerDialog .close').click();
  await page.click('#showEventRecognizer');await page.locator('#recognizerStatus').filter({hasText:'0 betalingen passen'}).waitFor();
  await page.locator('#eventRecognizerDialog .close').click();await page.click('#lock');
  assert.equal(await page.locator('#recognizerDefinition').textContent(),'');
  assert.deepEqual(errors,[],'No script-scope or initialization errors');
  console.log('Full Finance page: private scope, open/reopen, error/retry and lock passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
