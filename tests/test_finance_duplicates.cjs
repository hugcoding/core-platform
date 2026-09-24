// Synthetic comparison and privacy regression. node tests/test_finance_duplicates.cjs
async function testFinanceDuplicates(source) {
  const elements={};
  const $=id=>elements[id]??={open:false,innerHTML:'',textContent:'',disabled:false,
    showModal(){this.open=true},replaceChildren(){this.innerHTML='';this.textContent=''},addEventListener(){}};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const row={id:'incoming',booking_date:'2026-09-01',amount:'-10.00',counterparty:'<script>synthetic</script>',
    description:'Incoming synthetic',entry_reference:'synthetic-1',locator:'stmt:1/entry:1',candidates:[{
      id:'existing',booking_date:'2026-09-01',amount:'-11.00',counterparty:'Original synthetic',
      description:'Existing synthetic',entry_reference:'synthetic-1',can_link:false}]};
  let finish;
  const api=()=>new Promise(resolve=>{finish=resolve});
  const fragment=source.slice(source.indexOf('function duplicateComparison('),source.indexOf('function clearManagement()'));
  const ui=new Function('$','api','esc',`
    let sessionEpoch=0,duplicateEpoch=0,state=null;
    const money=String,document={querySelectorAll:()=>[]};
    ${fragment}
    return {duplicates,duplicateComparison,lock(){sessionEpoch++;duplicateEpoch++;$('duplicates').open=false;$('duplicateBody').replaceChildren()}};
  `)($,api,esc);
  const assert=(value,message)=>{if(!value)throw Error(message)};
  let run=ui.duplicates();
  assert($('duplicates').open&&$('duplicateBody').textContent.includes('laden'),'Show loading immediately');
  finish({records:[row]});await run;
  assert($('duplicateBody').innerHTML.includes('Existing synthetic'),'Show original payment');
  assert($('duplicateBody').innerHTML.includes('synthetic-1'),'Show bank number');
  assert($('duplicateBody').innerHTML.includes('disabled'),'Conflicting candidate cannot be linked');
  assert(!$('duplicateBody').innerHTML.includes('<script>'),'Escape private bank fields');
  run=ui.duplicates();ui.lock();finish({records:[row]});await run;
  assert(!$('duplicateBody').innerHTML,'Late response must not restore private data after locking');
  assert(!$('duplicates').open,'Late response must not reopen dialog');
}
if(typeof module!=='undefined') {
  module.exports=testFinanceDuplicates;
  if(require.main===module)testFinanceDuplicates(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8')).then(()=>console.log('Finance duplicate comparison passed')).catch(e=>{console.error(e);process.exitCode=1});
}
