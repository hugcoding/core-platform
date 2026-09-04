const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const source=fs.readFileSync('dashboard/static/workset-ai.js','utf8');
const fn=source.slice(source.indexOf('function prefillBackgroundAi'),source.indexOf('// Never replace edits'));
function setup(){
  const cat={},family={}, targetSpan={},targetCode={}, notices=[];
  const panel={dataset:{},querySelector:s=>s==='.review-category'?cat:family,prepend:n=>notices.push(n)};
  const card={querySelector:s=>s==='.review-panel'?panel:{querySelector:s=>s==='span'?targetSpan:targetCode}};
  const context=vm.createContext({state:{taxonomy:{categories:[{code:'finance'}],families:[{code:'bank',label:'Bank',categories:['finance']}]}},
    document:{createElement:()=>({})},wsEsc:x=>String(x||''),aiInfo:()=>'<info>'});
  vm.runInContext(fn,context);
  const doc={workset_status:'active',target_proposal:{category_code:'needs_review'}};
  const job={id:'job',proposal_id:'proposal',status:'ready',workset_available:true,category_code:'finance',family_code:'bank',reason:'bewijs',suggested_target_path:'/target'};
  return {panel,cat,family,notices,doc,job,run:()=>context.prefillBackgroundAi(card,doc,job)};
}
const good=setup();good.run();
assert.equal(good.cat.value,'finance');assert.equal(good.family.value,'bank');
assert.equal(good.panel.dataset.aiProposalId,'proposal');assert.equal(good.notices.length,1);
good.run();assert.equal(good.notices.length,1);
for(const modify of [s=>s.panel.dataset.userEdited='true',s=>s.doc.workset_status='inactive',
  s=>s.doc.latest_review_decision='accepted',s=>s.job.dismissed_at='today',
  s=>s.doc.target_proposal.category_code='finance',s=>s.job.family_code='invalid',
  s=>s.job.workset_available=false,s=>s.doc.is_similarity_redundant=true]){
  const s=setup();modify(s);s.run();assert.equal(s.notices.length,0);
}
console.log('AI prefill: provenance, no repeated fill, edits and scope guards passed');
