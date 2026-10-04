async function testRecurringBulk(source){
 const check=(x,m)=>{if(!x)throw Error(m)};
 const controls=Object.fromEntries(['category','subcategory','type','overwrite','all','apply','feedback','scope','scope-summary'].map(k=>[k,{value:'',checked:false,disabled:false,textContent:'',innerHTML:''}]));
 controls.scope.value='none';
 const boxes=[0,1,2].map(i=>({checked:false,disabled:i===2,dataset:{pick:String(i)}}));
 const allControls=[...Object.values(controls),...boxes],kind={value:'subscription'};
 const card={querySelector:()=>kind,querySelectorAll:()=>allControls};
 const target={querySelector:s=>controls[s.slice(6,-1)],querySelectorAll:s=>s==='[data-pick]'?boxes:allControls,closest:()=>card};
 const transactions=boxes.map((b,i)=>({id:'t'+i,review_id:i===2?'owner-review':null,confirmed:i===2}));
 const helper=source.slice(source.indexOf('function updateSelectionControls('),source.indexOf('function updateSuggestionSelection('));
 const code=source.slice(source.indexOf('function bindRecurringClassification('),source.indexOf('async function saveRecurringLink('));
 const requests=[];let fail=true,seq=0,reloads=0;
 const bind=new Function('api','key',`const state={categories:[{code:'cat',id:'cat-id',active:true,transaction_type:'EXPENSE'}]},esc=x=>x;${helper}${code};return bindRecurringClassification;`)(async(path,body)=>{requests.push({path,body});if(fail)throw Error('retry')},()=>String(++seq));
 bind(target,{id:'pattern',detection_id:'d',review_id:null},{transactions,total:103,protected_count:3,snapshot:'snapshot'},()=>true,async()=>{reloads++});
 check(!controls.apply.disabled&&boxes.every(b=>!b.checked),'type-only agreement starts without implicit transaction selection');
 controls.scope.value='selected';controls.scope.onchange();check(controls.apply.disabled,'empty selection must not confirm pattern');
 controls.category.value='cat';controls.category.onchange();controls.all.checked=true;controls.all.onchange();
 check(boxes[0].checked&&boxes[1].checked&&!boxes[2].checked,'protect manual review');
 boxes[1].checked=false;boxes[1].onchange();check(controls.all.indeterminate,'partial selection');
 await controls.apply.onclick();const selected=requests[0].body;
 check(requests[0].path.endsWith('/approve')&&selected.classification.items.length===1&&selected.classification.items[0].id==='t0','one atomic approval with only explicit IDs');
 check(selected.recurring_type==='subscription'&&selected.snapshot==='snapshot','same request carries kind and reviewed snapshot');
 fail=false;await controls.apply.onclick();check(selected.key===requests[1].body.key,'retry uses same key');check(reloads===1,'reload after success');
 controls.scope.value='all';controls.scope.onchange();check(controls['scope-summary'].textContent.includes('100 van 103'),'total includes payments beyond preview');
 await controls.apply.onclick();check(requests[2].body.classification.scope==='all'&&!('items' in requests[2].body.classification),'all scope is explicit, not preview IDs');
 check(!requests[2].body.classification.overwrite,'manual decisions protected by default');
 controls.overwrite.checked=true;controls.overwrite.onchange();await controls.apply.onclick();check(requests[3].body.classification.overwrite,'overwrite opt-in explicit');
 controls.scope.value='none';controls.scope.onchange();await controls.apply.onclick();check(requests[4].body.classification===null,'keep categories means no silent classification');
 return 'joint approval: selection, all-total scope, snapshot, owner protection and retry passed';
}
if(typeof module!=='undefined'){module.exports=testRecurringBulk;if(require.main===module)testRecurringBulk(require('node:fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1})}
