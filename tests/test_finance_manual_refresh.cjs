async function testFinanceManualRefresh(source){
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 const elements={refresh:{disabled:false,textContent:'Vernieuwen',setAttribute(){}},filterStatus:{textContent:''}};
 const $=id=>elements[id];let finish,calls=0;
 const fetch=()=>{calls++;return new Promise(resolve=>finish=resolve)};
 const part=source.slice(source.indexOf('async function manualRefresh()'),source.indexOf('function renderCategorization()'));
 const ui=new Function('$','fetch',`let sessionEpoch=0,refreshId=0;
   async function refresh(){refreshId++;return await fetch()}
   ${part};return {run:manualRefresh,supersede:()=>refreshId++,lock:()=>sessionEpoch++};`)($,fetch);
 let pending=ui.run();
 check(elements.refresh.disabled&&elements.refresh.textContent==='Bezig...','busy feedback visible immediately');
 await ui.run();check(calls===1,'duplicate clicks cannot start another refresh');
 finish(true);await pending;
 check(!elements.refresh.disabled&&elements.refresh.textContent==='Vernieuwen','button restored after completion');
 check(elements.filterStatus.textContent.startsWith('Overzicht gecontroleerd om '),'success feedback remains even without changed rows');
 pending=ui.run();finish(false);await pending;
 check(elements.filterStatus.textContent.includes('niet gelukt'),'failure reported without false success');
 check(!elements.refresh.disabled,'failed requests can retry');
 pending=ui.run();ui.supersede();elements.filterStatus.textContent='New filter request';finish(true);await pending;
 check(elements.filterStatus.textContent==='New filter request','older request does not overwrite new filter status');
 pending=ui.run();ui.lock();elements.filterStatus.textContent='';finish(true);await pending;
 check(elements.filterStatus.textContent==='','locked session never receives stale success');
 check(source.includes("$('refresh').onclick=manualRefresh;"),'button uses explicit manual feedback handler');
 return 'manual refresh feedback OK';
}
