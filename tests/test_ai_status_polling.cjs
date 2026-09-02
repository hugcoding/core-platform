const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../dashboard/static/workset-ai.js'), 'utf8');
function setup() {
  const requests = [], timers = new Map(), listeners = {};
  let timerId = 0;
  const context = vm.createContext({
    document: {hidden:false, querySelector:()=>null, addEventListener:(name,fn)=>listeners[name]=fn},
    fetch:()=>new Promise((resolve,reject)=>requests.push({resolve,reject})),
    setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},
    clearTimeout:id=>timers.delete(id), renderAiBell:()=>{}, decorateAiActions:()=>{}
  });
  vm.runInContext(source.slice(0, source.indexOf('function ensureAiBell')), context);
  const visibility = source.slice(source.indexOf("document.addEventListener('visibilitychange'"));
  vm.runInContext(visibility.slice(0, visibility.indexOf('\n});')+4), context);
  return {context, requests, timers, listeners, refresh:()=>vm.runInContext('refreshAiQueue()',context)};
}
const ok = {ok:true,json:async()=>({jobs:[],summary:{}})};
(async()=>{
  const s=setup();
  const first=s.refresh();
  assert.equal(s.refresh(),first);
  assert.equal(s.requests.length,2);
  assert.equal(s.timers.size,0);
  s.requests[0].resolve(ok);s.requests[1].resolve(ok);await first;
  assert.equal(s.timers.size,1);
  s.context.document.hidden=true;s.listeners.visibilitychange();
  assert.equal(s.timers.size,0);
  await s.refresh();assert.equal(s.requests.length,2);
  s.context.document.hidden=false;s.listeners.visibilitychange();
  const resumed=s.refresh();assert.equal(s.requests.length,4);
  s.requests[2].resolve(ok);s.requests[3].resolve(ok);await resumed;
  const failure=setup();const pending=failure.refresh();
  failure.requests[0].reject(new Error('offline'));await Promise.resolve();
  assert.equal(failure.refresh(),pending);
  assert.equal(failure.requests.length,2);
  failure.context.document.hidden=true;
  failure.requests[1].resolve(ok);await pending;
  assert.equal(failure.timers.size,0);
  console.log('PASS: single-flight, completion-based retry, hidden tab, visibility resume, partial failure');
})().catch(error=>{console.error(error);process.exitCode=1;});
