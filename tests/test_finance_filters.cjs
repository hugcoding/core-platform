// Synthetic dependent filters; no network or financial data.
function testFinanceFilters(source) {
  const assert=(ok,message)=>{if(!ok)throw Error(message)};
  const elements={};
  const $=id=>elements[id]??={value:'',innerHTML:'',textContent:'',disabled:false};
  // Match native select behaviour: a removed option cannot stay selected.
  for(const id of ['account','month']){
    let html='',value='';
    Object.defineProperties($(id),{
      innerHTML:{get:()=>html,set:v=>{html=v;value=''}},
      value:{get:()=>value,set:v=>{value=html.includes(`value="${v}"`)?v:''}}
    });
  }
  const state={all_accounts:[{id:'a',group_id:'g',label:'A'},{id:'b',group_id:'h',label:'B'},
    {id:'c',group_id:null,label:'C'}],groups:[{id:'g',name:'G'},{id:'h',name:'H'}],
    periods_by_account:{a:['2026-09'],b:['2025-08'],c:['2024-01']}};
  const calls=[];
  const refresh=()=>calls.push({group:$('wealthGroup').value,account:$('account').value});
  const filters=source.slice(source.indexOf('function scopeAccounts()'),source.indexOf('function importDates('));
  const options=source.slice(source.indexOf('function select('),source.indexOf('function periodChanged('));
  const ui=new Function('$','state','refresh',`const esc=String;let page=4;${options}${filters};return {syncScope,chooseScope}`)($,state,refresh);
  ui.syncScope();$('account').value='a';$('month').value='2026-09';
  $('wealthGroup').value='h';$('wealthGroup').onchange();
  assert(!$('account').innerHTML.includes('value="a"'),'group immediately removes unrelated accounts');
  assert($('account').value==='','invalid account cleared before request');
  assert(calls[0].group==='h'&&calls[0].account==='','request uses consistent scope');
  assert($('month').value==='2026-09','explicit period preserved even if new group has no entries');
  assert($('month').innerHTML.includes('2025-08'),'period choices follow new group immediately');
  ui.chooseScope('g','a');
  assert(calls[1].group==='g'&&calls[1].account==='a','account drilldown sets both filters');
  ui.chooseScope('unassigned');
  assert($('account').innerHTML.includes('value="c"')&&!$('account').innerHTML.includes('value="b"'),'unassigned scope');
  $('wealthGroup').value='';$('wealthGroup').onchange();
  assert($('account').innerHTML.includes('value="a"')&&$('account').innerHTML.includes('value="b"'),'all accounts restored from complete metadata');
  const dateFragment=source.slice(source.indexOf('function importDates('),source.indexOf("$('refreshBalances').onclick"));
  const dates=new Function('esc',dateFragment+';return importDates')(String);
  const text=dates({created_at:'2026-09-01T10:00:00Z',imported_at:'2026-09-01T10:01:00Z',
    rolled_back_at:'2026-09-02T11:00:00Z',last_transaction_date:'2026-08-31',status:'rolled_back',unresolved:0});
  assert(text.includes('Teruggedraaid:')&&text.includes('2026-08-31')&&text.includes('historie'),'import and rollback timeline');
}
if(typeof module!=='undefined'){
  module.exports=testFinanceFilters;
  if(require.main===module){testFinanceFilters(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8'));console.log('Finance filters passed')}
}
