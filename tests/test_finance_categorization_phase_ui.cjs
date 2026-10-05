function testCategorizationPhaseUI(source){
 const elements={categorize:{},stopCategorize:{dataset:{}},categorizationStatus:{}};
 const state={jobs:[]},$=id=>elements[id];
 const labels={pending:'Wacht',running:'Bezig',failed:'Mislukt'};
 const reasons={waiting_for_local_llm:'Wacht op je lokale LLM',retry_wait:'nieuwe poging volgt'};
 const part=source.slice(source.indexOf('function renderCategorization()'),source.indexOf("$('categorize').onclick"));
 const render=new Function('state','$','labels','reasons',part+';return renderCategorization;')(state,$,labels,reasons);
 const check=(x,m)=>{if(!x)throw Error(m)};
 state.jobs=[{id:'synthetic',job_kind:'categorize',status:'running',categorization_phase:'core',processed:12,target_count:100,classified:12}];
 render();check(elements.categorizationStatus.textContent.includes('CORE-herkenning'),'CORE phase visible');
 state.jobs[0]={...state.jobs[0],status:'pending',categorization_phase:'llm',waiting_reason:'waiting_for_local_llm'};
 render();check(elements.categorizationStatus.textContent.includes('Lokale LLM'),'LLM phase visible');
 check(elements.categorizationStatus.textContent.includes('Wacht op je lokale LLM'),'offline waiting visible');
 check(elements.categorize.disabled&&!elements.stopCategorize.hidden,'waiting job remains stoppable');
 state.jobs[0]={...state.jobs[0],status:'failed',waiting_reason:'retry_wait'};
 render();check(!elements.categorizationStatus.textContent.includes('nieuwe poging volgt'),'failed job does not promise a retry');
 check(!elements.categorize.disabled&&elements.stopCategorize.hidden,'failed job can be restarted');
 return 'categorization phase UI OK';
}
if(typeof require!=='undefined'&&require.main===module){console.log(testCategorizationPhaseUI(require('fs').readFileSync('dashboard/static/finance.js','utf8')))}
