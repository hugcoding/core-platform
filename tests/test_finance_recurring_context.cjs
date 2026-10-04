async function testRecurringContext(source){
 const elements=new Map(),opened=[];let scrolled=0;
 const $=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',replaceChildren(){this.innerHTML=''}});return elements.get(id)};
 const fragment=source.slice(source.indexOf('async function loadRecurring('),source.indexOf('async function saveRecurring('));
 const pattern={id:'same',account_id:'a',merchant:'Synthetic',cadence:'monthly',status:'proposed',proposed_type:'subscription',classifications:[{category_code:'abonnementen',count:3,confirmed_count:3}]};
 const edits=new Map();
 const run=new Function('$','document','api','opened','edits',`
 let sessionEpoch=0,recurringEpoch=0,recurringPage=2,recurringFocus=null,recurringTimer=null,state={accounts:[]};const recurringKindEdits=edits,recurringLabels={subscription:'Abonnement',fixed_cost:'Vaste last'},esc=x=>String(x??''),classificationLabel=c=>c.category_code,recurringControls=()=>{};
 async function loadRecurringMembers(p,i,page){opened.push({id:p.id,page})}
 ${fragment};return loadRecurring;`);
 const load=run($,{querySelectorAll:()=>[],querySelector:()=>({scrollIntoView(){scrolled++},querySelector:()=>({focus(){}})})},async()=>({patterns:[pattern],has_more:false}),opened,edits);
 await load({id:'same',memberPage:3});
 if(opened[0].id!=='same'||opened[0].page!==3||scrolled!==1)throw Error('review context lost');
 if(!$('recurringBody').innerHTML.includes('abonnementen')||!$('recurringBody').innerHTML.includes('value="subscription" selected'))throw Error('updated classification/advice missing');
 edits.set('same','fixed_cost');await load({id:'same',memberPage:3});
 if(!$('recurringBody').innerHTML.includes('value="fixed_cost" selected'))throw Error('manual type draft overwritten');
 return 'same pattern/page, updated classification and manual type preservation passed';
}
if(typeof module!=='undefined'){module.exports=testRecurringContext;if(require.main===module)testRecurringContext(require('node:fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1})}
