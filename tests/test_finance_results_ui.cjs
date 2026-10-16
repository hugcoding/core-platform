async function testFinanceResultsUI(source){
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 const elements={},$=id=>elements[id]??={value:'',innerHTML:'',textContent:'',open:true,disabled:false,
   listeners:{},replaceChildren(){this.innerHTML=''},querySelectorAll(){return []},
   addEventListener(event,callback){this.listeners[event]=callback},showModal(){this.open=true}};
 const pending=[];let details=0;
 const api=()=>new Promise(resolve=>pending.push(resolve));
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fragment=source.slice(source.indexOf('function clearCategorizationResults()'),source.indexOf('async function showSuggestions('));
 const ui=new Function('$','api','esc','money','transactionParty','detail','refresh','labels','URLSearchParams',
   `let sessionEpoch=0,resultsEpoch=0,resultsPage=0,resultsData=null;${fragment};return {load:loadCategorizationResults,card:resultCard,clear:clearCategorizationResults,data:()=>resultsData};`)
   ($,api,esc,String,t=>t.counter_account_label||t.counterparty,()=>details++,async()=>{},{},class {});
 const item={booking_date:'2026-01-01',amount:'12.34',account_label:'Synthetic savings',counterparty:'Synthetic bank',
   description:'<img src=x onerror=alert(1)>',result:{kind:'refined',source:'Jouw voorbeeld',before:'Inkomen',assigned:'Inkomen / Rente',current:'Inkomen / Salaris',reason:'Jouw bevestigde inkomenspatroon',state:'reviewed',processed_at:'2026-01-01T12:00:00Z'}};
 const html=ui.card(item,0);
 check(html.includes('Synthetic savings')&&html.includes('Inkomen / Rente')&&html.includes('Inkomen / Salaris'),'historical and current context rendered');
 check(html.includes('&lt;img')&&!html.includes('<img'),'untrusted bank text escaped');
 check(html.includes('data-result-detail="0"'),'active results can be reviewed');
 check(!ui.card({...item,result:{...item.result,state:'inactive'}},0).includes('data-result-detail'),'rolled-back transactions are not editable');
 $('resultsSource').value='core';
 const reviewButton={dataset:{resultDetail:'0'}};
 $('categorizationResultsBody').querySelectorAll=()=>[reviewButton];
 const old=ui.load();const newer=ui.load();
 const response={job:{id:'j'},jobs:[{id:'j',requested_at:'2026-01-01T12:00:00Z',status:'done'}],items:[item],total:51,page:0,page_size:50};
 pending[1](response);await newer;
 check($('resultsNext').disabled===false&&$('resultsPrevious').disabled===true,'pagination covers totals beyond preview');
 reviewButton.onclick();check(details===1,'review opens the existing transaction detail flow');
 const current=$('categorizationResultsBody').innerHTML;
 pending[0]({...response,total:0,items:[]});await old;
 check($('categorizationResultsBody').innerHTML===current&&ui.data().total===51,'older response cannot overwrite a newer selection');
 const closing=ui.load();$('categorizationResultsDialog').open=false;$('categorizationResultsDialog').listeners.close();
 pending[2](response);await closing;
 check(ui.data()===null&&$('categorizationResultsBody').innerHTML==='','closing clears private rows and rejects late responses');
 check(source.includes("clearCategorizationResults();$('categorizationResultsDialog').close();"),'lock clears the results dialog');
 return 'classification results UI OK';
}
