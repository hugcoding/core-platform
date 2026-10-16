// Fabricated state only; execute the actual background-refresh path.
async function testFinanceQuietRefresh(source){
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 const elements={},writes=[],$=id=>elements[id]??={value:'',disabled:false,setAttribute(){}};
 for(const id of ['transactions','filterStatus']){
   Object.defineProperty($(id),'innerHTML',{set:v=>writes.push([id,v]),get:()=>''});
   Object.defineProperty($(id),'textContent',{set:v=>writes.push([id,v]),get:()=>''});
 }
 let state={jobs:[{id:'job',status:'running',job_kind:'categorize',processed:1}],transactions:[{id:'t',category_code:null}],categories:[]};
 let next=JSON.parse(JSON.stringify(state));next.jobs[0].processed=2;
 const timers=[];let progress=0;
 const functions=source.slice(source.indexOf('let transactionMarkup='),source.indexOf('function renderCategorization()'));
 const api=async()=>JSON.parse(JSON.stringify(next));
 const ui=new Function('$','initial','api','AbortController','URLSearchParams','setTimeout','clearTimeout','renderCategorization',
   `let state=initial,sessionEpoch=0,refreshId=0,refreshController=null,timer=null;
    let activePeriod={},page=0,sort='booking_date',direction='desc';const labels={},reasons={};
    const message=e=>{throw Error(e)};${functions}
    return {refresh,overviewSignature,replaceTransactionRows,renderActivity,setState:v=>state=v};`)
   ($,state,api,class {signal={};abort(){}},class {},(callback,delay)=>{timers.push({callback,delay});return 1},()=>{},()=>progress++);
 await ui.refresh(true);
 check(progress===1,'progress updates without redrawing the overview');
 check(writes.every(([id,value])=>id!=='transactions'&&value!== 'Overzicht bijwerken...'),'background check is visually quiet');
 check(timers[0].delay===300000,'background checks are at least five minutes apart');
 check(ui.overviewSignature(state)===ui.overviewSignature(next),'job counters excluded from overview comparison');
 const changed={...next,transactions:[{id:'t',category_code:'income'}]};
 check(ui.overviewSignature(next)!==ui.overviewSignature(changed),'category changes invalidate overview');
 check(ui.replaceTransactionRows('synthetic')===true,'changed rows rendered');
 check(ui.replaceTransactionRows('synthetic')===false,'identical rows retained');
 check(ui.replaceTransactionRows('changed')===true,'new content rendered');
 next.jobs[0].status='done';
 check(ui.overviewSignature(state)!==ui.overviewSignature(next),'completion updates busy-dependent controls');
 ui.setState(next);ui.renderActivity();
 check(!elements.import.disabled&&timers.length===1,'completed job stops automatic checks');
 check(source.includes("$('refresh').onclick=manualRefresh;"),'manual refresh is explicit, not a background event');
 return 'quiet refresh UI OK';
}
