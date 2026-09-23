// Synthetic rendering checks: node tests/test_finance_balances.cjs
function testFinanceBalances(source) {
  const elements={};
  const $=id=>elements[id]??={textContent:'',innerHTML:''};
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fragment=source.slice(source.indexOf('function renderBankBalances('),source.indexOf("$('refreshBalances').onclick"));
  const render=new Function('$','money','esc',fragment+';return renderBankBalances')($,v=>'EUR '+v,esc);
  const assert=(value,message)=>{if(!value)throw Error(message)};
  const row={status:'reported',label:'<script>synthetic</script>',opening:'100.00',closing:'80.00',
    opening_date:'2026-08-31',closing_date:'2026-09-01',source_id:'synthetic',locator:'stmt:1'};
  render({accounts:[row],total:'80.00',as_of:'2026-09-01',requested_end:'2026-09-30'});
  assert($('bankBalanceStatus').textContent.includes('2026-09-01'),'Keep bank peildatum');
  assert($('bankBalances').innerHTML.includes('Geen banksaldo op gekozen einddatum'),'Do not project over gaps');
  assert(!$('bankBalances').innerHTML.includes('<script>'),'Escape account name');
  render({accounts:[{status:'unavailable',label:'Missing'}],total:null});
  assert(!$('bankBalances').innerHTML.includes('EUR'),'Missing is not zero and clears prior balance');
  render({accounts:[],pending:2,total:null},true);
  assert($('bankBalanceStatus').textContent.includes('Verwerking aangevraagd'),'Pending progress');
  render({accounts:[{status:'conflict',label:'Conflict',closing_date:'2026-09-01'}],total:null});
  assert($('bankBalances').innerHTML.includes('Tegenstrijdige'),'Surface conflicts');
}
if(typeof module!=='undefined') {
  module.exports=testFinanceBalances;
  if(require.main===module) {testFinanceBalances(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8'));console.log('Finance balance rendering passed')}
}
