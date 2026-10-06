async function testLLMToggleUI(source){
 const elements={llmEnabled:{disabled:false,checked:true},categorize:{},stopCategorize:{dataset:{}},categorizationStatus:{}};
 const state={jobs:[],llm_enabled:true},$=id=>elements[id],calls=[];
 let fail=false,finish;
 const api=async(path,body)=>{
  if(path!=='/classification-settings'||typeof body.llm_enabled!=='boolean')throw Error('incorrect toggle request');
  if(fail)throw Error('synthetic failure');
  await new Promise(resolve=>finish=resolve);
  calls.push(body.llm_enabled);state.llm_enabled=body.llm_enabled;
 };
 const action=async(fn)=>{try{await fn()}catch{}};
 const part=source.slice(source.indexOf('function renderCategorization()'),source.indexOf("$('categorize').onclick"));
 new Function('state','$','labels','reasons','api','action','sessionEpoch',part)(state,$,{}, {},api,action,0);
 const check=(ok,message)=>{if(!ok)throw Error(message)};
 elements.llmEnabled.checked=false;
 let pending=elements.llmEnabled.onchange();
 check(elements.llmEnabled.disabled,'disable repeated clicks during save');finish();await pending;
 check(!elements.llmEnabled.disabled&&!elements.llmEnabled.checked,'off persisted and control restored');
 elements.llmEnabled.checked=true;
 pending=elements.llmEnabled.onchange();finish();await pending;
 check(calls.join(',')==='false,true'&&elements.llmEnabled.checked,'off/on sends explicit booleans');
 fail=true;elements.llmEnabled.checked=false;await elements.llmEnabled.onchange();
 check(elements.llmEnabled.checked&&!elements.llmEnabled.disabled,'failed save restores server preference');
 return 'LLM toggle UI OK';
}
if(typeof require!=='undefined'&&require.main===module){testLLMToggleUI(require('fs').readFileSync('dashboard/static/finance.js','utf8')).then(console.log)}
