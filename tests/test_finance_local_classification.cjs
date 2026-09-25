function testFinanceLocalClassification(source){
  const elements={},$=id=>elements[id]??={dataset:{},disabled:false,hidden:false,textContent:''};
  const state={jobs:[]},calls=[];
  const api=async(path,body)=>calls.push(path),action=async fn=>fn();
  const fragment=source.slice(source.indexOf('function renderCategorization()'),source.indexOf('async function action('));
  const render=new Function('$','state','api','action',`const labels={running:'Bezig',failed:'Mislukt'},reasons={cancelled:'Gestopt door jou'};${fragment};return renderCategorization`)($,state,api,action);
  const assert=(ok,message)=>{if(!ok)throw Error(message)};
  render();assert(!$('categorize').disabled&&$('stopCategorize').hidden,'start enabled when idle');
  state.jobs=[{id:'synthetic',job_kind:'categorize',status:'running',processed:4,target_count:10,classified:3}];
  render();assert($('categorize').disabled&&!$('stopCategorize').hidden,'running controls');
  assert($('categorizationStatus').textContent.includes('4 van 10')&&$('categorizationStatus').textContent.includes('3 ingedeeld'),'progress');
  $('stopCategorize').onclick();assert(calls[0]==='/categorization/synthetic/stop','cancel exact job');
  state.jobs[0].status='failed';state.jobs[0].error_code='cancelled';render();
  assert(!$('categorize').disabled&&$('stopCategorize').hidden,'can start again after stop');
  assert($('categorizationStatus').textContent.includes('Gestopt door jou'),'explicit cancellation status');
  state.jobs=[{job_kind:'import',status:'pending'}];render();assert($('categorize').disabled,'existing import queue has priority');
}
if(typeof module!=='undefined'){
 module.exports=testFinanceLocalClassification;
 if(require.main===module)testFinanceLocalClassification(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8'));
}
