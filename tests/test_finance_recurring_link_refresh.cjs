async function testRecurringLinkRefresh(source){
 const check=(v,m)=>{if(!v)throw Error(m)},elements=new Map(),calls=[],loads=[];
 const $=id=>{if(!elements.has(id))elements.set(id,{value:'proposed',textContent:''});return elements.get(id)};
 const fragment=source.slice(source.indexOf('async function saveRecurringLink('),source.indexOf('async function loadRecurringCandidates('));
 let fail=true;
 const run=new Function('$','api','loads',`let sessionEpoch=0,recurringEpoch=7,recurringPage=3,recurringFocus=null,recurringAttempt=null;const key=()=> 'stable-key',recurringControls=()=>{};async function loadRecurring(context){loads.push({context,page:recurringPage,focus:recurringFocus})}${fragment};return saveRecurringLink;`);
 const save=run($,async(path,body)=>{calls.push({path,body});if(fail)throw Error('retry')},loads);
 await save({id:'child',link_id:'old'},'root',7);fail=false;await save({id:'child',link_id:'old'},'root',7);
 check(calls[0].body.key===calls[1].body.key,'link retry must retain key');check(loads.length===1,'refresh exactly after saved link');
 check(loads[0].context.id==='root'&&loads[0].page===0&&loads[0].focus==='root','merged root must become visible without manual refresh');
 check($('recurringReviewStatus').value==='all','confirmed root must remain findable after linking');
 return 'link refresh: retry, root focus and all-status visibility passed';
}
if(typeof module!=='undefined'){module.exports=testRecurringLinkRefresh;if(require.main===module)testRecurringLinkRefresh(require('node:fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1})}
