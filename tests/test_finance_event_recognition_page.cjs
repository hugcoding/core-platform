// Full-page regression: real HTML and both real scripts, only synthetic HTTP.
// Requires Playwright and Chromium or installed Edge. No live services used.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CORE_TEST_BROWSER_CHANNEL?{channel:process.env.CORE_TEST_BROWSER_CHANNEL}:{})});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const rule={id:'asn-interest-6607',name:'ASN rente',origin:'ASN',version:'v1',issuer:'ASNBANK',code:'6607',counterparty:'ASN Bank',conditions:['ASNBANK + 6607'],result:'Inkomen / Rente'};
  let fail=false,directDone=false;const applied=[],directApplied=[];
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());assert.equal(u.hostname,'core.test','No external services');
   const assets={'/corefinance':'finance.html','/coredashboard/assets/finance.js':'finance.js','/coredashboard/assets/finance-recognizer.js':'finance-recognizer.js','/coredashboard/assets/finance.css':'finance.css','/coredashboard/assets/style.css':'style.css'};
   if(assets[u.pathname])return route.fulfill({contentType:u.pathname.endsWith('.js')?'application/javascript':u.pathname.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(__dirname,'../dashboard/static',assets[u.pathname]),'utf8')});
   if(u.pathname==='/api/v1/finance/data')return route.fulfill({json:{accounts:[],groups:[],months:[],periods:[],categories:[],transaction_types:[],transactions:[],imports:[],jobs:[],totals:{total:0,uncategorized:0},unresolved:0,bank_balances:{accounts:[],groups:[],pending:0,total:null}}});
   if(u.pathname==='/api/v1/finance/recognizers')return route.fulfill({json:{rules:[rule]}});
   if(u.pathname==='/api/v1/finance/recognizers/asn-interest-6607/transactions')return route.fulfill(fail?{status:503,json:{detail:'service_unavailable'}}:{json:{mode:'matching',total:2,approval:{snapshot:'b'.repeat(64),previous:null},items:[{id:'00000000-0000-4000-8000-000000000010',booking_date:'2026-09-05',amount:'0.02',account_label:'Synthetic account',bank_counterparty:'Niet aangeleverd',description:'Synthetic interest',recognized_counterparty:'ASN Bank',current_category:'Inkomen / Rente',status:directDone?'manual':'eligible',evidence:[]}],counts:{eligible:directDone?0:1,aligned:0,manual:directDone?1:0,manual_conflict:0,protected:1},missing_evidence:0,message:'Synthetische controle'}});
   if(u.pathname==='/api/v1/finance/recognizers/asn-interest-6607/approve'){
    directApplied.push(route.request().postDataJSON());directDone=true;return route.fulfill({json:{applied:1}});
   }
   if(u.pathname==='/api/v1/finance/recognizer-rules/preview'){
    const body=route.request().postDataJSON();assert.equal(body.rule.module,'finance');
    const t={id:'00000000-0000-4000-8000-000000000001',booking_date:'2026-09-05',amount:'0.02',account_label:'Synthetic savings',counterparty:'',description:'Synthetic rent',current_merchant:null,category_code:'inkomen',subcategory_code:'inkomen_rente',status:'eligible',changes:{counterparty:body.rule.set.counterparty}};
    const items=[{...t,id:'00000000-0000-4000-8000-000000000002',status:'protected'}];if(!(body.rule.exclude||[]).includes(t.id))items.unshift(t);
    return route.fulfill({json:{snapshot:'a'.repeat(64),total:items.length,counts:{eligible:items.length-1,protected:1,aligned:0},items}});
   }
   if(u.pathname==='/api/v1/finance/recognizer-rules/apply'){
    const body=route.request().postDataJSON();applied.push(body);
    return route.fulfill({json:{status:'saved',rule_id:body.rule_id,event_id:'00000000-0000-4000-8000-000000000099',applied:body.scope==='none'?0:1}});
   }
   if(u.pathname==='/api/v1/finance/session')return route.fulfill({json:{status:'locked'}});
   return route.abort();
  });
  await page.goto('http://core.test/corefinance');
  await page.locator('#workspace').waitFor({state:'visible'});
  assert.equal(await page.evaluate(()=>typeof window.$),'undefined','Finance helpers stay private');
  await page.click('#showEventRecognizer');
  await page.locator('#recognizerStatus').filter({hasText:'2 betalingen passen'}).waitFor();
  assert.equal(await page.locator('#eventRecognizerDialog').evaluate(e=>e.open),true);
  assert.equal(await page.locator('#recognizerEditor').isVisible(),false,'initial overview does not require an own rule');
  await page.check('#recognizerSelectVisible');await page.click('#recognizerApprove');
  await page.locator('#recognizerStatus').filter({hasText:'1 transacties geaccordeerd'}).waitFor();
  assert.deepEqual(directApplied[0].selection,['00000000-0000-4000-8000-000000000010']);
  assert.equal('rule' in directApplied[0],false,'direct approval does not create an editable own rule');
  assert.equal(await page.locator('#recognizerEditor').isVisible(),false);
  fail=true;await page.click('#recognizerRefresh');await page.locator('#recognizerStatus').filter({hasText:'Dienst tijdelijk niet beschikbaar'}).waitFor();
  fail=false;await page.click('#recognizerRefresh');await page.locator('#recognizerStatus').filter({hasText:'2 betalingen passen'}).waitFor();
  await page.locator('#eventRecognizerDialog .close').click();
  await page.click('#showEventRecognizer');await page.locator('#recognizerStatus').filter({hasText:'2 betalingen passen'}).waitFor();
  await page.click('#recognizerEdit');await page.fill('#ruleParty','Synthetic Confirmed Bank');
  await page.click('#rulePreview');await page.locator('#ruleStatus').filter({hasText:'Controleer de wijzigingen'}).waitFor();
  assert.equal(await page.locator('[data-rule-select]:disabled').count(),1,'manual name protected');
  await page.check('#ruleSelectVisible');await page.click('#ruleApprove');await page.locator('#ruleStatus').filter({hasText:'1 transacties geaccordeerd'}).waitFor();
  assert.deepEqual(applied[0].selection,['00000000-0000-4000-8000-000000000001']);
  assert.deepEqual(applied[0].rule.set,{counterparty:'Synthetic Confirmed Bank'},'party-only update does not resubmit category');
  await page.click('#ruleCodeTab');const definition=JSON.parse(await page.locator('#ruleCode').inputValue());definition.name='Edited as JSON';
  await page.fill('#ruleCode',JSON.stringify(definition,null,2));await page.click('#ruleFormTab');assert.equal(await page.locator('#ruleName').inputValue(),'Edited as JSON');
  await page.click('#rulePreview');await page.locator('[data-rule-exclude]').first().click();
  assert.match(await page.locator('#ruleExcluded').textContent(),/1 transacties/);
  await page.click('#rulePreview');await page.locator('#ruleCounts').filter({hasText:'0 wijzigbaar'}).waitFor();
  await page.click('#ruleResetExcluded');await page.click('#ruleSave');await page.locator('#ruleStatus').filter({hasText:'Opgeslagen.'}).waitFor();
  assert.equal(applied.at(-1).scope,'none');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.locator('#eventRecognizerDialog').evaluate(e=>e.scrollWidth>e.clientWidth+2),false,'mobile dialog fits');
  await page.locator('#eventRecognizerDialog .close').click();await page.click('#lock');
  assert.equal(await page.locator('#recognizerDefinition').textContent(),'');assert.equal(await page.locator('#ruleCode').inputValue(),'');
  assert.deepEqual(errors,[],'No script-scope or initialization errors');
  console.log('Full Finance page: direct overview approval, open/reopen, rule form/code, party-only approval, selection, exclusions, mobile and lock passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
