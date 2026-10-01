async function testRecurringBulk(source){
 const check=(x,m)=>{if(!x)throw Error(m)};
 const controls=Object.fromEntries(['category','subcategory','type','overwrite','all','apply','feedback'].map(k=>[k,{value:'',checked:false,disabled:false,textContent:'',innerHTML:''}]));
 const boxes=[0,1,2].map(i=>({checked:false,disabled:i===2,dataset:{pick:String(i)}}));
 const target={querySelector:s=>controls[s.slice(6,-1)],querySelectorAll:s=>s==='[data-pick]'?boxes:[...Object.values(controls),...boxes]};
 const transactions=boxes.map((b,i)=>({id:'t'+i,review_id:i===2?'owner-review':null,confirmed:i===2}));
 const helper=source.slice(source.indexOf('function updateSelectionControls('),source.indexOf('function updateSuggestionSelection('));
 const code=source.slice(source.indexOf('function bindRecurringClassification('),source.indexOf('async function saveRecurringLink('));
 const requests=[];let fail=true,seq=0,reloads=0;
 const bind=new Function('api','key',`const state={categories:[{code:'cat',id:'cat-id',active:true,transaction_type:'EXPENSE'}]},esc=x=>x,refresh=async()=>{};${helper}${code};return bindRecurringClassification;`)(async(path,body)=>{requests.push({path,body});if(fail)throw Error('retry')},()=>String(++seq));
 bind(target,{id:'pattern'},transactions,()=>true,async()=>{reloads++});
 check(controls.apply.disabled,'no implicit selection');controls.category.value='cat';controls.category.onchange();
 controls.all.checked=true;controls.all.onchange();check(boxes[0].checked&&boxes[1].checked&&!boxes[2].checked,'protect manual review');
 boxes[1].checked=false;boxes[1].onchange();check(controls.all.indeterminate,'partial selection');
 await controls.apply.onclick();check(requests[0].body.items.length===1&&requests[0].body.items[0].id==='t0','send only explicit IDs');
 fail=false;await controls.apply.onclick();check(requests[0].body.key===requests[1].body.key,'retry uses same key');check(reloads===1,'reload after success');
 controls.overwrite.checked=true;controls.overwrite.onchange();controls.all.checked=true;controls.all.onchange();
 await controls.apply.onclick();check(requests[2].body.items.length===3&&requests[2].body.overwrite,'manual changes require opt-in');
 controls.overwrite.checked=false;controls.overwrite.onchange();check(!boxes[2].checked&&boxes[2].disabled,'withdraw overwrite clears protected selection');
 return 'recurring bulk: explicit selection, deselection, owner protection and replay passed';
}
if(typeof module!=='undefined'){module.exports=testRecurringBulk;if(require.main===module)testRecurringBulk(require('node:fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log).catch(e=>{console.error(e);process.exitCode=1})}
