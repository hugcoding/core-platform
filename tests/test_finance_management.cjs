// Synthetic UI regression: node tests/test_finance_management.cjs
async function testFinanceManagement(source) {
  const assert=(ok,message)=>{if(!ok)throw Error(message)};
  const elements={};
  const $=id=>elements[id]??=(Object.assign({value:'',hidden:false,disabled:false,open:true,textContent:'',
    replaceChildren(){this.innerHTML=''},showModal(){this.open=true},addEventListener(){}},{}));
  const accounts=[{id:'a',label:'Synthetic account',default_label:'Account *0000',display_name:null,
    group_id:null,relationship:'UNASSIGNED',group_event_id:null,name_event_id:null}];
  const data={accounts,groups:[{id:'g',name:'Synthetic group',event_id:'event'}],relationships:{UNASSIGNED:'Nog indelen',OWN:'Van mij'}};
  let fail=true,defer=false,resolveLoad,requests=[];
  const api=async(path,body)=>{
    if(body){requests.push(body);if(fail)throw Error('Synthetic network error');return {status:'saved'}}
    if(path==='/account-management')return defer?await new Promise(resolve=>resolveLoad=resolve):data;
    return {events:[]};
  };
  const document={querySelectorAll:()=>Object.values(elements)};
  const fragment=source.slice(source.indexOf('function clearManagement()'),source.indexOf('function clearAccountName()'));
  const ui=new Function('$','api','document',`
    let sessionEpoch=0,managementEpoch=0,managementHistoryEpoch=0,managementState=null,managementAttempt=null,managementBusy=false;
    const esc=String,key=()=>String(Math.random()),refresh=async()=>{};
    ${fragment}
    return {loadManagement,saveManagementRequest,clearManagement};
  `)($,api,document);
  $('managedAccount').value='a';
  await ui.loadManagement('a');
  assert(!$('managementBody').hidden,'management loaded');
  assert($('managedRelationship').disabled,'unassigned relationship disabled');
  const payload={name:'Synthetic',group_id:'g',relationship:'OWN',previous:null,previous_name:null};
  await ui.saveManagementRequest('/accounts/a/management',payload,'saved');
  assert($('managementStatus').textContent==='Synthetic network error','request error is visible');
  assert(!$('saveManagement').disabled,'retry enabled');
  fail=false;await ui.saveManagementRequest('/accounts/a/management',payload,'saved');
  assert(requests.length===2&&requests[0].key===requests[1].key,'retry keeps same idempotency key');
  assert($('managementStatus').textContent==='saved','success shown');
  defer=true;const pending=ui.loadManagement('a');ui.clearManagement();resolveLoad(data);await pending;
  assert($('managementBody').hidden,'stale response after closing stays hidden');
  assert($('managedName').value===''&&$('managementStatus').textContent==='','private data cleared');
}
if(typeof module!=='undefined') {
  module.exports=testFinanceManagement;
  if(require.main===module)testFinanceManagement(require('node:fs').readFileSync(require('node:path').join(__dirname,'../dashboard/static/finance.js'),'utf8'))
    .then(()=>console.log('Finance management regression passed')).catch(e=>{console.error(e);process.exitCode=1});
}
