async function testRecurringUI(source) {
 const assert=(ok,message)=>{if(!ok)throw Error(message)};
 const elements=new Map();
 const $=id=>{if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',textContent:'',disabled:false,hidden:false,replaceChildren(){this.innerHTML='';this.textContent=''},addEventListener(){},showModal(){}});return elements.get(id)};
 const pending=[],calls=[];
 const api=(path,body)=>{calls.push({path,body});return new Promise((resolve,reject)=>pending.push({resolve,reject}))};
 const fragment=source.slice(source.indexOf('// Recurring view'),source.indexOf('// End recurring view.'));
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let seq=0;
 const run=new Function('$','document','api','esc','key',`
 let sessionEpoch=0,state={accounts:[]};const detail=()=>{},classificationLabel=()=>'',refresh=async()=>{};
 ${fragment}
 return {loadRecurring,saveRecurring,clearRecurring,lock:()=>{sessionEpoch++;clearRecurring()}}`);
 const app=run($,{querySelectorAll:()=>[]},api,esc,()=>String(++seq));
 const first=app.loadRecurring();assert(!$('recurringProgress').hidden,'show loading');
 const second=app.loadRecurring();pending[1].resolve({patterns:[],has_more:false});await second;
 pending[0].resolve({patterns:[{id:'stale',merchant:'old'}]});await first;
 assert(!$('recurringBody').innerHTML.includes('old'),'ignore stale response');
 const pattern={id:'p',detection_id:'d',review_id:null,merchant:'<script>bad</script>',currency:'EUR',status:'proposed',observation_count:3,cadence:'monthly'};
 const loaded=app.loadRecurring();pending[2].resolve({patterns:[pattern],has_more:false});await loaded;
 assert($('recurringBody').innerHTML.includes('&lt;script&gt;'),'escape bank text');
 assert(!$('recurringBody').innerHTML.includes('<script>'),'no injected markup');
 const save1=app.saveRecurring(pattern,'confirmed','subscription');pending[3].reject(Error('temporary'));await save1;
 const save2=app.saveRecurring(pattern,'confirmed','subscription');assert(calls[3].body.key===calls[4].body.key,'retry retains idempotency key');pending[4].reject(Error('temporary'));await save2;
 const last=app.loadRecurring();app.lock();pending[5].resolve({patterns:[pattern],has_more:false});await last;
 assert($('recurringBody').innerHTML==='','locked page must stay empty');
 assert($('recurringAccount').innerHTML==='','lock clears accounts');
 return 'recurring UI: loading, stale responses, escaping, retry idempotency and lock passed';
}
if(typeof module!=='undefined'){
 module.exports=testRecurringUI;
 if(require.main===module)testRecurringUI(require('node:fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1});
}
