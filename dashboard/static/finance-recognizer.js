/* Uses the same owner-only API and session boundary as Finance. */
function initializeFinanceRecognizer({$,api,esc,money,detail,refresh,reasons,getSessionEpoch,key,getState}){
let recognizerEpoch=0,recognizerRules=[],directPreview=null,directSelected=new Set(),directAttempt=null,directBusy=false;
function clearEventRecognizer(close=false){
 recognizerEpoch++;recognizerRules=[];directPreview=null;directSelected.clear();directAttempt=null;directBusy=false;$('recognizerApprovalScope').value='selected';clearRuleEditor();$('recognizerApprovalActions').hidden=true;updateDirectControls();
 for(const id of ['recognizerSelect','recognizerDefinition','recognizerStatus','recognizerCounts','recognizerExamples'])$(id).replaceChildren();
 $('recognizerRefresh').disabled=false;
 if(close===true&&$('eventRecognizerDialog').open)$('eventRecognizerDialog').close();
}
function recognizerDefinition(rule){
 const conditions=rule.conditions.map(v=>`<li>${esc(v)}</li>`).join('');
 return `<h3>${esc(rule.name)}</h3><p class="muted">${esc(rule.origin)} · ${esc(rule.version)} · Regeldefinitie alleen-lezen</p><h4>Herkennen aan</h4><ul>${conditions}</ul>${rule.technical_pattern?`<details><summary>Exact herkenningspatroon</summary><code>${esc(rule.technical_pattern)}</code></details>`:''}<h4>CORE vult aan</h4><p>${esc(rule.result)}</p>${rule.source_url?`<p><a href="${esc(rule.source_url)}" target="_blank" rel="noopener noreferrer">${esc(rule.source_title)}</a><br><small>Gecontroleerd op ${esc(rule.verified_on)}</small></p>`:''}<p class="muted">${rule.issuer?'Issuer is de uitgever van de bankcode, niet op zichzelf de tegenpartij. ':''}De originele bankgegevens blijven bewaard.</p>`;
}
function recognizerCard(t){
 const statuses={eligible:'Te accorderen: bevestig deze voorgestelde indeling',aligned:'Huidige categorie komt overeen',manual:'Jouw bevestigde indeling blijft behouden',manual_conflict:'Afwijkend handmatig oordeel · blijft beschermd',protected:'Bestaande specifieke indeling blijft beschermd',applied:'Via deze CORE-herkenner ingedeeld'};
 return `<article class="duplicate-card"><div class="section-title"><label><input type="checkbox" data-recognizer-select="${esc(t.id)}" ${t.status!=='eligible'?'disabled':''}> <strong>${esc(t.booking_date)} · ${money(t.amount)}</strong></label><span>${esc(t.account_label)}</span></div><dl><dt>Banktegenpartij</dt><dd>${esc(t.bank_counterparty)}</dd><dt>Originele bankomschrijving</dt><dd>${esc(t.description||'Niet aangeleverd')}</dd>${t.recognized_counterparty?`<dt>Door CORE herkende tegenpartij</dt><dd>${esc(t.recognized_counterparty)}</dd>`:''}<dt>Huidige categorie</dt><dd>${esc(t.current_category)}</dd>${t.evidence.length?`<dt>Herkenningsbewijs</dt><dd>${t.evidence.map(e=>esc([e.issuer,e.proprietary,[e.domain,e.family,e.subfamily].filter(Boolean).join('/')].filter(Boolean).join(' · '))).join('<br>')}</dd>`:''}</dl><p>${esc(statuses[t.status]||t.status)}${t.applied?' · Regelversie geregistreerd bij deze indeling':''}</p>`+
 `<button type="button" data-recognizer-transaction="${esc(t.id)}">Bekijk transactie</button></article>`;
}
async function loadRecognizer(){
 const request=++recognizerEpoch,epoch=getSessionEpoch(),id=$('recognizerSelect').value;
 const rule=recognizerRules.find(r=>r.id===id);if(!rule)return;
 if(rule.definition){openRuleEditor(rule);return;}
 $('recognizerEdit').textContent='Als eigen regel bewerken';
 directPreview=null;directSelected.clear();directAttempt=null;$('recognizerApprovalActions').hidden=true;
 $('recognizerDefinition').innerHTML=recognizerDefinition(rule);
 $('recognizerStatus').textContent='Herkenning en voorbeelden ophalen…';$('recognizerCounts').textContent='';$('recognizerExamples').replaceChildren();$('recognizerRefresh').disabled=true;
 try{
  const data=await api('/recognizers/'+encodeURIComponent(id)+'/transactions');
  if(request!==recognizerEpoch||epoch!==getSessionEpoch()||!$('eventRecognizerDialog').open)return;
  $('recognizerStatus').textContent=data.mode==='matching'?`${data.total} betalingen passen bij deze herkenner. Voorbeeldselectie van maximaal 50, verspreid over de periode.`:`${data.total} huidige indelingen met deze regel. Voorbeeldselectie van maximaal 50, verspreid over de periode.`;
  const c=data.counts;
  $('recognizerCounts').textContent=(data.mode==='matching'?`${c.eligible} te accorderen · ${c.aligned} komen overeen · ${c.manual+c.manual_conflict} handmatig beschermd (${c.manual_conflict} afwijkend) · ${c.protected} overige indelingen beschermd. `:'')+(data.missing_evidence?`${data.missing_evidence} bijschrijvingen hebben geen bruikbare bankcodegegevens; hierover wordt niets aangenomen. `:'')+data.message;
  $('recognizerExamples').innerHTML=data.items.map(recognizerCard).join('')||'<p>Geen passende transacties beschikbaar. Bij oude imports kan de bestaande bankcode-aanvulverwerking nog nodig zijn.</p>';
  directPreview=data;directSelected.clear();directAttempt=null;$('recognizerApprovalActions').hidden=!data.approval;
  $('recognizerExamples').querySelectorAll('[data-recognizer-select]').forEach(el=>el.onchange=()=>{el.checked?directSelected.add(el.dataset.recognizerSelect):directSelected.delete(el.dataset.recognizerSelect);directAttempt=null;updateDirectControls();});updateDirectControls();
  $('recognizerExamples').querySelectorAll('[data-recognizer-transaction]').forEach(b=>b.onclick=async()=>{
   const original=b.dataset.recognizerTransaction;
   try{const t=await api('/transactions/'+encodeURIComponent(original));if(request===recognizerEpoch&&epoch===getSessionEpoch()&&$('eventRecognizerDialog').open)detail(t,async()=>{await refresh();if($('eventRecognizerDialog').open)await loadRecognizer()});}
   catch(e){if(epoch===getSessionEpoch()&&request===recognizerEpoch)$('recognizerStatus').textContent=e.message}
  });
 }catch(e){if(request===recognizerEpoch&&epoch===getSessionEpoch())$('recognizerStatus').textContent=e.message}
 finally{if(request===recognizerEpoch&&epoch===getSessionEpoch())$('recognizerRefresh').disabled=false}
}
async function showEventRecognizer(){
 clearEventRecognizer();$('eventRecognizerDialog').showModal();
 const request=++recognizerEpoch,epoch=getSessionEpoch();$('recognizerStatus').textContent='Herkenners ophalen…';
 try{const data=await api('/recognizers');if(request!==recognizerEpoch||epoch!==getSessionEpoch()||!$('eventRecognizerDialog').open)return;
  recognizerRules=data.rules;$('recognizerSelect').innerHTML=data.rules.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');await loadRecognizer();
 }catch(e){if(request===recognizerEpoch&&epoch===getSessionEpoch())$('recognizerStatus').textContent=e.message}
}
function updateDirectControls(){
 const items=directPreview?.items.filter(t=>t.status==='eligible')||[];
 const n=directPreview?($('recognizerApprovalScope').value==='all'?directPreview.counts.eligible:directSelected.size):0;
 $('recognizerApprove').textContent=`Selectie accorderen (${n})`;$('recognizerApprove').disabled=directBusy||!n;
 $('recognizerSelectVisible').checked=!!items.length&&items.every(t=>directSelected.has(t.id));
 $('recognizerSelectVisible').indeterminate=items.some(t=>directSelected.has(t.id))&&!$('recognizerSelectVisible').checked;
 $('recognizerSelectVisible').disabled=directBusy||!items.length;$('recognizerApprovalScope').disabled=directBusy;
 $('recognizerRefresh').disabled=directBusy;$('recognizerSelect').disabled=directBusy;$('recognizerNew').disabled=directBusy;$('recognizerEdit').disabled=directBusy;
 $('recognizerExamples').querySelectorAll('[data-recognizer-select]').forEach(el=>el.disabled=directBusy||!items.some(t=>t.id===el.dataset.recognizerSelect));
}
async function approveDirect(){
 if(!directPreview?.approval||directBusy)return;
 const request=++recognizerEpoch,epoch=getSessionEpoch(),id=$('recognizerSelect').value,scope=$('recognizerApprovalScope').value;
 const body={...directPreview.approval,scope,selection:scope==='selected'?[...directSelected].sort():[]};
 const encoded=JSON.stringify([id,body]);if(!directAttempt||directAttempt.encoded!==encoded)directAttempt={encoded,body:{...body,key:key()}};
 directBusy=true;updateDirectControls();$('recognizerStatus').textContent='Selectie accorderen…';
 try{const response=await api('/recognizers/'+encodeURIComponent(id)+'/approve',directAttempt.body);
  if(request!==recognizerEpoch||epoch!==getSessionEpoch()||!$('eventRecognizerDialog').open)return;
  directBusy=false;await refresh();if(request!==recognizerEpoch||epoch!==getSessionEpoch()||!$('eventRecognizerDialog').open)return;
  await loadRecognizer();if(epoch===getSessionEpoch()&&$('eventRecognizerDialog').open)$('recognizerStatus').textContent=`${response.applied} transacties geaccordeerd. De ingebouwde herkenner is behouden; er is geen eigen regel aangemaakt.`;
 }catch(e){if(request===recognizerEpoch&&epoch===getSessionEpoch())$('recognizerStatus').textContent=e.message;}
 finally{if(epoch===getSessionEpoch()){directBusy=false;updateDirectControls();}}
}
$('recognizerSelectVisible').onchange=()=>{for(const t of directPreview?.items||[])if(t.status==='eligible')$('recognizerSelectVisible').checked?directSelected.add(t.id):directSelected.delete(t.id);directAttempt=null;updateDirectControls();};
$('recognizerApprovalScope').onchange=()=>{directAttempt=null;updateDirectControls();};$('recognizerApprove').onclick=approveDirect;
$('showEventRecognizer').onclick=showEventRecognizer;
$('recognizerSelect').onchange=()=>{$('recognizerApprovalScope').value='selected';loadRecognizer();};
$('recognizerRefresh').onclick=()=>recognizerRules.length?loadRecognizer():showEventRecognizer();
$('eventRecognizerDialog').addEventListener('close',clearEventRecognizer);
reasons.recognizer_scan_limit='Te veel betalingen voor deze directe controle. Er is niets gewijzigd; de gewone indelingsjob blijft beschikbaar.';
reasons.recognizer_not_found='Deze herkenner is niet beschikbaar. Open Eventherkenner opnieuw.';

let editor=null,rulePreview=null,ruleSelected=new Set(),ruleAttempt=null,ruleBusy=false;
const ruleFields={description:'Omschrijving',counterparty:'Banktegenpartij',counteraccount:'Tegenrekening',account_id:'Rekening-ID',issuer:'Uitgever bankcode',bank_code:'Bankcode',direction:'Bij-/afschrijving (CRDT/DBIT)',currency:'Valuta',model_version:'Bronherkenner (regelversie)'};
function clearRuleEditor(){
 editor=null;rulePreview=null;ruleSelected.clear();ruleAttempt=null;ruleBusy=false;
 for(const id of ['ruleName','ruleParty','ruleCode'])$(id).value='';
 for(const id of ['ruleConditions','ruleExamples','ruleStatus','ruleCounts','ruleExcluded','ruleCategory','ruleSubcategory'])$(id).replaceChildren();
 $('recognizerEditor').hidden=true;$('recognizerReadOnly').hidden=false;
}
function changedRule(){
 recognizerEpoch++;rulePreview=null;ruleSelected.clear();ruleAttempt=null;
 $('ruleExamples').replaceChildren();$('ruleCounts').textContent='';$('ruleStatus').textContent='Regel gewijzigd. Controleer opnieuw vóór accorderen.';
 updateRuleControls();
}
function updateRuleControls(){
 $('ruleFields').disabled=ruleBusy;
 const n=rulePreview?($('ruleScope').value==='all'?rulePreview.counts.eligible:ruleSelected.size):0;
 $('ruleApprove').textContent=`Opslaan en accorderen (${n})`;$('ruleApprove').disabled=ruleBusy||!n;
 $('ruleSave').disabled=ruleBusy;$('rulePreview').disabled=ruleBusy;
 $('ruleParty').disabled=!$('rulePartyOn').checked||ruleBusy;
 $('ruleCategory').disabled=!$('ruleCategoryOn').checked||ruleBusy;$('ruleSubcategory').disabled=$('ruleCategory').disabled;
 $('ruleType').disabled=!$('ruleTypeOn').checked||ruleBusy;
 const eligible=rulePreview?.items.filter(t=>t.status==='eligible')||[];
 $('ruleSelectVisible').checked=!!eligible.length&&eligible.every(t=>ruleSelected.has(t.id));
 $('ruleSelectVisible').indeterminate=eligible.some(t=>ruleSelected.has(t.id))&&!$('ruleSelectVisible').checked;
 $('ruleSelectVisible').disabled=ruleBusy||!eligible.length;
 $('ruleExcluded').textContent=editor?.exclude?.length?`${editor.exclude.length} transacties blijvend uitgesloten van deze regel.`:'';
 $('ruleResetExcluded').hidden=!editor?.exclude?.length;
}
function ruleSubcategories(value=''){
 const categories=getState()?.categories||[],parent=categories.find(c=>c.code===$('ruleCategory').value);
 $('ruleSubcategory').innerHTML='<option value="">Geen subcategorie</option>'+categories.filter(c=>c.parent_id===parent?.id&&c.active!==false).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}</option>`).join('');$('ruleSubcategory').value=value;
}
function renderRuleConditions(){
 $('ruleConditions').innerHTML=editor.terms.map((t,i)=>`<div class="rule-condition"><select data-rule-field="${i}" aria-label="Veld">${Object.entries(ruleFields).map(([v,n])=>`<option value="${v}" ${v===t.field?'selected':''}>${esc(n)}</option>`).join('')}</select><select data-rule-op="${i}" aria-label="Vergelijking"><option value="equals" ${t.op==='equals'?'selected':''}>is gelijk aan</option><option value="contains" ${t.op==='contains'?'selected':''}>bevat</option></select><input data-rule-value="${i}" value="${esc(t.value)}" maxlength="400" aria-label="Waarde"><button data-rule-remove="${i}" type="button" aria-label="Voorwaarde verwijderen">Verwijderen</button></div>`).join('');
 for(const [attr,field] of [['field','field'],['op','op'],['value','value']])$('ruleConditions').querySelectorAll(`[data-rule-${attr}]`).forEach(el=>el.oninput=()=>{editor.terms[Number(el.dataset['rule'+attr[0].toUpperCase()+attr.slice(1)])][field]=el.value;changedRule();});
 $('ruleConditions').querySelectorAll('[data-rule-remove]').forEach(el=>el.onclick=()=>{if(editor.terms.length>1){editor.terms.splice(Number(el.dataset.ruleRemove),1);renderRuleConditions();changedRule();}});
}
function editorRule(){
 if(!$('ruleCodePanel').hidden){const r=JSON.parse($('ruleCode').value);if(r.module!=='finance')throw Error('Deze editor is voor Finance-regels.');return r;}
 const actions={};if($('rulePartyOn').checked)actions.counterparty=$('ruleParty').value;
 if($('ruleCategoryOn').checked){actions.category=$('ruleCategory').value;if($('ruleSubcategory').value)actions.subcategory=$('ruleSubcategory').value;}
 if($('ruleTypeOn').checked)actions.transaction_type=$('ruleType').value;
 return {name:$('ruleName').value,module:'finance',active:$('ruleActive').checked,when:{[$('ruleMode').value]:editor.terms},set:actions,...(editor.exclude.length?{exclude:editor.exclude}: {})};
}
function fillRuleForm(rule){
 if(!rule||rule.module!=='finance'||!rule.when||!['all','any'].includes(Object.keys(rule.when)[0])||!Array.isArray(Object.values(rule.when)[0])||!rule.set)throw Error('Controleer de regelcode: Finance, voorwaarden en acties zijn verplicht.');
 editor.terms=JSON.parse(JSON.stringify(Object.values(rule.when)[0]));editor.exclude=[...(rule.exclude||[])];
 $('ruleName').value=rule.name||'';$('ruleMode').value=Object.keys(rule.when)[0];$('ruleActive').checked=rule.active===true;
 $('rulePartyOn').checked='counterparty'in rule.set;$('ruleParty').value=rule.set.counterparty||'';
 $('ruleCategoryOn').checked='category'in rule.set;$('ruleCategory').value=rule.set.category||'';ruleSubcategories(rule.set.subcategory||'');
 $('ruleTypeOn').checked='transaction_type'in rule.set;$('ruleType').value=rule.set.transaction_type||'INCOME';renderRuleConditions();updateRuleControls();
}
function openRuleEditor(source=null){
 recognizerEpoch++;clearRuleEditor();
 const definition=source?.definition||{name:source?.name||'Nieuwe herkenningsregel',module:'finance',active:false,
  when:{all:source?.issuer?[{field:'issuer',op:'equals',value:source.issuer},{field:'bank_code',op:'equals',value:source.code}]:[{field:'description',op:'contains',value:''}]},
  set:{counterparty:source?.counterparty||''}};
 editor={rule_id:source?.rule_id||key(),previous:source?.event_id||null,terms:[],exclude:[]};
 const categories=getState()?.categories||[];$('ruleCategory').innerHTML='<option value="">Kies categorie</option>'+categories.filter(c=>!c.parent_id&&c.active!==false).map(c=>`<option value="${esc(c.code)}">${esc(c.name||c.label)}</option>`).join('');
 $('recognizerReadOnly').hidden=true;$('recognizerEditor').hidden=false;$('ruleForm').hidden=false;$('ruleCodePanel').hidden=true;
 $('ruleFormTab').setAttribute('aria-pressed','true');$('ruleCodeTab').setAttribute('aria-pressed','false');
 fillRuleForm(definition);$('ruleStatus').textContent=source?.definition?'Bewerk de opgeslagen regel. Controleer het effect voordat je accordeert.':'Nieuwe eigen regel. Ingebouwde herkenners blijven behouden.';
}
function ruleCategoryLabel(code){const c=getState()?.categories.find(c=>c.code===code);return c?.name||c?.label||code||'Geen categorie';}
function renderRulePreview(){
 const statuses={eligible:'Wijziging beschikbaar',aligned:'Komt al overeen',protected:'Handmatig oordeel of transactiesoort beschermd',invalid_category:'Categorie niet meer beschikbaar',needs_category:'Kies ook een categorie om deze nog ongecategoriseerde transactie te bevestigen'};
 $('ruleExamples').innerHTML=rulePreview.items.map(t=>`<article class="duplicate-card"><label><input type="checkbox" data-rule-select="${esc(t.id)}" ${t.status!=='eligible'?'disabled':''} ${ruleSelected.has(t.id)?'checked':''}> ${esc(t.booking_date)} · ${money(t.amount)}</label><p>${esc(t.account_label)}</p><p>${esc(t.description||'Geen omschrijving')}</p><dl><dt>Banktegenpartij</dt><dd>${esc(t.counterparty||'Niet aangeleverd')}</dd><dt>Bevestigde / ingedeelde tegenpartij</dt><dd>${esc(t.current_merchant||'Niet vastgelegd')}</dd><dt>Huidige indeling</dt><dd>${esc(ruleCategoryLabel(t.category_code))}${t.subcategory_code?' / '+esc(ruleCategoryLabel(t.subcategory_code)):''}</dd><dt>Wijzigingen</dt><dd>${Object.entries(t.changes).map(([k,v])=>esc(({counterparty:'Tegenpartij',category_code:'Categorie',subcategory_code:'Subcategorie',transaction_type:'Soort'})[k]||k)+': '+esc(k==='category_code'||k==='subcategory_code'?ruleCategoryLabel(v):v||'Geen')).join('<br>')||'Geen wijzigingen'}</dd></dl><p>${esc(statuses[t.status])}</p><button type="button" data-rule-detail="${esc(t.id)}">Bekijk / wijzig handmatig</button><button type="button" data-rule-exclude="${esc(t.id)}">Uitsluiten van regel</button></article>`).join('')||'<p>Geen passende transacties.</p>';
 $('ruleExamples').querySelectorAll('[data-rule-detail]').forEach(el=>el.onclick=async()=>{const request=recognizerEpoch,epoch=getSessionEpoch();try{const t=await api('/transactions/'+encodeURIComponent(el.dataset.ruleDetail));if(editor&&request===recognizerEpoch&&epoch===getSessionEpoch())detail(t,async()=>{await refresh();if(editor&&$('eventRecognizerDialog').open)await previewRule();});}catch(e){if(request===recognizerEpoch&&epoch===getSessionEpoch())$('ruleStatus').textContent=e.message;}});
 $('ruleExamples').querySelectorAll('[data-rule-select]').forEach(el=>el.onchange=()=>{el.checked?ruleSelected.add(el.dataset.ruleSelect):ruleSelected.delete(el.dataset.ruleSelect);ruleAttempt=null;updateRuleControls();});
 $('ruleExamples').querySelectorAll('[data-rule-exclude]').forEach(el=>el.onclick=()=>{const definition=editorRule();definition.exclude=[...new Set([...(definition.exclude||[]),el.dataset.ruleExclude])];if(!$('ruleCodePanel').hidden)$('ruleCode').value=JSON.stringify(definition,null,2);else editor.exclude=definition.exclude;changedRule();});
}
async function previewRule(){
 if(!editor)return;const request=++recognizerEpoch,epoch=getSessionEpoch();ruleBusy=true;updateRuleControls();$('ruleStatus').textContent='Effect controleren…';
 try{const rule=editorRule(),data=await api('/recognizer-rules/preview',{rule});if(epoch!==getSessionEpoch()||request!==recognizerEpoch||!editor)return;
  rulePreview=data;ruleSelected.clear();ruleAttempt=null;renderRulePreview();$('ruleCounts').textContent=`${data.total} passend · ${data.counts.eligible} wijzigbaar · ${data.counts.aligned} al correct · ${data.counts.protected} beschermd · ${data.counts.needs_category||0} hebben eerst een categorie nodig. Maximaal 50 voorbeelden verspreid over de periode.`;$('ruleStatus').textContent='Controleer de wijzigingen en selecteer wat je wilt accorderen.';
 }catch(e){if(epoch===getSessionEpoch()&&request===recognizerEpoch)$('ruleStatus').textContent=e.message;}
 finally{if(epoch===getSessionEpoch()&&request===recognizerEpoch){ruleBusy=false;updateRuleControls();}}
}
async function applyRule(scope){
 if(!editor||ruleBusy)return;
 const request=++recognizerEpoch,epoch=getSessionEpoch();
 try{
  const rule=editorRule(),body={rule,rule_id:editor.rule_id,previous:editor.previous,scope,snapshot:scope==='none'?null:rulePreview?.snapshot,selection:scope==='selected'?[...ruleSelected].sort():[]};
  const encoded=JSON.stringify(body);if(!ruleAttempt||ruleAttempt.encoded!==encoded)ruleAttempt={encoded,body:{...body,key:key()}};
  ruleBusy=true;updateRuleControls();$('ruleStatus').textContent='Regel en beoordelingen opslaan…';
  const response=await api('/recognizer-rules/apply',ruleAttempt.body);
  if(epoch!==getSessionEpoch()||request!==recognizerEpoch||!editor)return;
  editor.previous=response.event_id;ruleAttempt=null;rulePreview=null;ruleSelected.clear();$('ruleExamples').replaceChildren();$('ruleCounts').textContent='';
  $('ruleStatus').textContent=`Opgeslagen. ${response.applied} transacties geaccordeerd. Jouw overige beoordelingen en bankgegevens zijn behouden.`;
  const entry={id:editor.rule_id,rule_id:editor.rule_id,event_id:response.event_id,definition:rule,name:rule.name,origin:'Eigen regel',editable:true};
  recognizerRules=recognizerRules.filter(r=>r.id!==entry.id).concat(entry);
  $('recognizerSelect').innerHTML=recognizerRules.map(r=>`<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('');$('recognizerSelect').value=entry.id;
  await refresh();
 }catch(e){if(epoch===getSessionEpoch()&&request===recognizerEpoch)$('ruleStatus').textContent=e.message;}
 finally{if(epoch===getSessionEpoch()&&request===recognizerEpoch){ruleBusy=false;updateRuleControls();}}
}
$('recognizerNew').onclick=()=>openRuleEditor();$('recognizerEdit').onclick=()=>openRuleEditor(recognizerRules.find(r=>r.id===$('recognizerSelect').value));
$('ruleBack').onclick=()=>showEventRecognizer();
$('ruleCodeTab').onclick=()=>{try{$('ruleCode').value=JSON.stringify(editorRule(),null,2);$('ruleForm').hidden=true;$('ruleCodePanel').hidden=false;$('ruleFormTab').setAttribute('aria-pressed','false');$('ruleCodeTab').setAttribute('aria-pressed','true');}catch(e){$('ruleStatus').textContent=e.message;}};
$('ruleFormTab').onclick=()=>{try{fillRuleForm(editorRule());$('ruleForm').hidden=false;$('ruleCodePanel').hidden=true;$('ruleFormTab').setAttribute('aria-pressed','true');$('ruleCodeTab').setAttribute('aria-pressed','false');}catch(e){$('ruleStatus').textContent=e.message;}};
$('ruleAddCondition').onclick=()=>{if(editor.terms.length<12){editor.terms.push({field:'description',op:'contains',value:''});renderRuleConditions();changedRule();}};
$('ruleCategory').onchange=()=>{ruleSubcategories();changedRule();};
for(const id of ['ruleName','ruleMode','rulePartyOn','ruleParty','ruleCategoryOn','ruleSubcategory','ruleTypeOn','ruleType','ruleActive','ruleCode'])$(id).addEventListener('input',changedRule);
$('ruleResetExcluded').onclick=()=>{try{const rule=editorRule();delete rule.exclude;editor.exclude=[];if(!$('ruleCodePanel').hidden)$('ruleCode').value=JSON.stringify(rule,null,2);changedRule();}catch(e){$('ruleStatus').textContent=e.message;}};
$('ruleSelectVisible').onchange=()=>{for(const t of rulePreview?.items||[])if(t.status==='eligible')$('ruleSelectVisible').checked?ruleSelected.add(t.id):ruleSelected.delete(t.id);ruleAttempt=null;updateRuleControls();};
$('ruleScope').onchange=()=>{ruleAttempt=null;updateRuleControls();};$('rulePreview').onclick=previewRule;$('ruleSave').onclick=()=>applyRule('none');$('ruleApprove').onclick=()=>applyRule($('ruleScope').value);
Object.assign(reasons,{invalid_recognition_rule:'Controleer de regel: naam, minimaal één geldige voorwaarde en minimaal één actie zijn verplicht.',invalid_recognition_module:'Deze editor ondersteunt alleen Finance. De Werkset-koppeling volgt later.',invalid_recognition_selection:'Selecteer wijzigbare transacties of kies alle passende transacties.',recognition_rule_changed:'De regel is gewijzigd. Open hem opnieuw voordat je opslaat.',recognition_preview_changed:'De transacties of beoordelingen zijn gewijzigd. Controleer de voorbeelden opnieuw.'});
return {clear:clearEventRecognizer,show:showEventRecognizer,load:loadRecognizer,card:recognizerCard};
}
