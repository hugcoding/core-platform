/* Synthetic DOM and API only; never contacts Finance. */
const fs=require('node:fs'),path=require('node:path');
async function run(){
 const source=fs.readFileSync(path.join(__dirname,'../dashboard/static/finance-recognizer.js'),'utf8');
 const check=(ok,msg)=>{if(!ok)throw Error(msg)};
 const elements={};
 const $=id=>elements[id]??={value:'',textContent:'',_html:'',open:false,disabled:false,listeners:{},
  set innerHTML(v){this._html=v;if(id==='recognizerSelect')this.value=(v.match(/value="([^"]+)"/)||[])[1]||''},
  get innerHTML(){return this._html},replaceChildren(){this._html='';this.textContent='';if(id==='recognizerSelect')this.value=''},
  addEventListener(k,f){this.listeners[k]=f},showModal(){this.open=true},close(){this.open=false;this.listeners.close?.()},querySelectorAll(){return []}};
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const pending=[],api=p=>new Promise((resolve,reject)=>pending.push({p,resolve,reject}));
 const ui=new Function('$','api','esc','money','detail','refresh',`let sessionEpoch=0;const reasons={};${source};const ui=initializeFinanceRecognizer({$,api,esc,money,detail,refresh,reasons,getSessionEpoch:()=>sessionEpoch});return {...ui,expire:()=>{sessionEpoch++;ui.clear(true)}}`)
  ($,api,esc,String,()=>{},async()=>{});
 const rule={id:'asn-interest-6607',name:'ASN rente',conditions:['Issuer ASNBANK','Code 6607'],origin:'ASN',version:'v1',result:'Inkomen / Rente'};
 const item={id:'synthetic',booking_date:'2026-09-05',amount:'0.02',account_label:'Synthetic savings',bank_counterparty:'',description:'<img src=x onerror=alert(1)>',recognized_counterparty:'ASN Bank',current_category:'Inkomen',status:'manual_conflict',evidence:[{issuer:'ASNBANK',proprietary:'6607'}]};
 const result={mode:'matching',items:[item],total:80,counts:{eligible:70,aligned:5,manual:3,manual_conflict:1,protected:1},missing_evidence:2,message:'Geen wijzigingen'};
 const opening=ui.show();pending[0].resolve({rules:[rule]});await Promise.resolve();
 check(pending[1].p==='/recognizers/asn-interest-6607/transactions','loads shared recognizer evidence');pending[1].resolve(result);await opening;
 check($('recognizerStatus').textContent.includes('80'),'full total shown');
 check($('recognizerExamples').innerHTML.includes('&lt;img'),'bank content escaped');
 check(!$('recognizerExamples').innerHTML.includes('<img'),'no bank HTML execution');
 check($('recognizerExamples').innerHTML.includes('handmatig oordeel'),'owner protection visible');
 check($('recognizerCounts').textContent.includes('2 bijschrijvingen'),'missing evidence explained');
 const old=ui.load(),fresh=ui.load();pending[3].resolve({...result,total:81});await fresh;pending[2].resolve({...result,total:1});await old;
 check($('recognizerStatus').textContent.includes('81'),'late stale response ignored');
 const closing=ui.load();$('eventRecognizerDialog').close();pending[4].resolve(result);await closing;
 check($('recognizerExamples').innerHTML==='','closed dialog clears private examples');
 const failed=ui.show();pending[5].reject(Error('Synthetic network failure'));await failed;
 check($('recognizerStatus').textContent.includes('network failure'),'error feedback');
 const retry=$('recognizerRefresh').onclick();pending[6].resolve({rules:[rule]});await Promise.resolve();pending[7].resolve(result);await retry;
 check($('eventRecognizerDialog').open,'retry leaves dialog open');
 const locked=ui.load();ui.expire();pending[8].resolve(result);await locked;
 check(!$('eventRecognizerDialog').open&&$('recognizerExamples').innerHTML==='','lock closes and clears; late response ignored');
 const finance=fs.readFileSync(path.join(__dirname,'../dashboard/static/finance.js'),'utf8');
 check(finance.includes('clearEventRecognizer(true)'),'Finance lock invokes recognizer cleanup');
 const html=fs.readFileSync(path.join(__dirname,'../dashboard/static/finance.html'),'utf8');
 check(html.indexOf('assets/finance-recognizer.js')<html.indexOf('assets/finance.js'),'initializer loads before the isolated Finance closure');
 check(finance.includes('initializeFinanceRecognizer({$,api,esc,money,detail,refresh,reasons,getSessionEpoch:()=>sessionEpoch})'),'Finance passes its private helpers and live session getter');
 check(html.includes('id="showEventRecognizer"')&&html.includes('assets/finance-recognizer.js'),'entry point and script present');
 console.log('Eventherkenner UI: loading, escaping, counts, races, close, lock and retry passed');
}
run().catch(e=>{console.error(e);process.exitCode=1});
