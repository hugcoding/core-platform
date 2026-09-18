// Synthetic UI regression; run: node tests/test_finance_selection.cjs
async function testFinanceSelection(source) {
  const check=(condition,message)=>{if(!condition)throw new Error(message)};
  const elements=Object.fromEntries(['selectVisibleSuggestions','approveSelection','refreshSuggestions','suggestionsStatus'].map(id=>[id,{}]));
  let boxes=[],round=0,fail=false,submitted=[];
  const $=id=>elements[id];
  const document={querySelectorAll:q=>q==='[data-select-suggestion]'?boxes:q==='[data-select-suggestion]:checked'?boxes.filter(b=>b.checked):[elements.selectVisibleSuggestions,elements.approveSelection,...boxes]};
  const fragment=source.slice(source.indexOf('function updateSuggestionSelection()'),source.indexOf("$('refreshSuggestions').onclick"));
  const run=new Function('$','document','load','submit',`
    let suggestionsState=null,sessionEpoch=0,suggestionsEpoch=0;
    const key=()=>String(Math.random()),message=()=>{},refresh=async()=>{};
    const api=async(path,body)=>submit(body);
    async function showSuggestions(){suggestionsEpoch++;suggestionsState=load();updateSuggestionSelection()}
    ${fragment}
    return {showSuggestions,updateSuggestionSelection};
  `);
  const ui=run($,document,()=>{
    boxes=[0,1].map(i=>({checked:false,disabled:false,dataset:{selectSuggestion:String(i)}}));
    return {seed_transaction_id:'seed',seed_review_id:'review',transactions:[0,1].map(i=>({id:`round${round}-${i}`,review_id:null}))};
  },async body=>{
    check(elements.selectVisibleSuggestions.disabled,'select all must be disabled during submission');
    submitted.push(body);if(fail)throw Error('synthetic network failure');round++;
  });
  const selectAll=()=>{check(!elements.selectVisibleSuggestions.disabled,'select all must work in next round');elements.selectVisibleSuggestions.checked=true;elements.selectVisibleSuggestions.onchange();check(boxes.every(b=>b.checked),'all visible selected')};
  await ui.showSuggestions();check(elements.approveSelection.disabled,'empty selection disabled');
  selectAll();await elements.approveSelection.onclick();
  check(elements.approveSelection.disabled,'new round starts unchecked');
  selectAll();await elements.approveSelection.onclick();
  check(round===2,'two successive rounds approved');
  selectAll();fail=true;await elements.approveSelection.onclick();
  check(!elements.approveSelection.disabled,'failed request can retry');
  fail=false;await elements.approveSelection.onclick();
  check(submitted[2].key===submitted[3].key,'retry preserves idempotency key');
  check(submitted[0].items[0].id!==submitted[1].items[0].id,'second round uses new targets');
}
if(typeof module!=='undefined') {
  module.exports=testFinanceSelection;
  if(require.main===module) testFinanceSelection(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8')).then(()=>console.log('Finance selection regression passed')).catch(e=>{console.error(e);process.exitCode=1});
}
