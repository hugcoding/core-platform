/* Uses the same owner-only API and session boundary as Finance. */
function initializeFinanceRecognizer({$,api,esc,money,detail,refresh,reasons,getSessionEpoch}){
let recognizerEpoch=0,recognizerRules=[];
function clearEventRecognizer(close=false){
 recognizerEpoch++;recognizerRules=[];
 for(const id of ['recognizerSelect','recognizerDefinition','recognizerStatus','recognizerCounts','recognizerExamples'])$(id).replaceChildren();
 $('recognizerRefresh').disabled=false;
 if(close===true&&$('eventRecognizerDialog').open)$('eventRecognizerDialog').close();
}
function recognizerDefinition(rule){
 const conditions=rule.conditions.map(v=>`<li>${esc(v)}</li>`).join('');
 return `<h3>${esc(rule.name)}</h3><p class="muted">${esc(rule.origin)} · ${esc(rule.version)} · Alleen bekijken</p><h4>Herkennen aan</h4><ul>${conditions}</ul>${rule.technical_pattern?`<details><summary>Exact herkenningspatroon</summary><code>${esc(rule.technical_pattern)}</code></details>`:''}<h4>CORE vult aan</h4><p>${esc(rule.result)}</p>${rule.source_url?`<p><a href="${esc(rule.source_url)}" target="_blank" rel="noopener noreferrer">${esc(rule.source_title)}</a><br><small>Gecontroleerd op ${esc(rule.verified_on)}</small></p>`:''}<p class="muted">${rule.issuer?'Issuer is de uitgever van de bankcode, niet op zichzelf de tegenpartij. ':''}De originele bankgegevens blijven bewaard.</p>`;
}
function recognizerCard(t){
 const statuses={eligible:'Kan worden ingedeeld via de bestaande indelingsjob',aligned:'Huidige categorie komt overeen',manual:'Jouw bevestigde indeling blijft behouden',manual_conflict:'Afwijkend handmatig oordeel · blijft beschermd',protected:'Bestaande specifieke indeling blijft beschermd',applied:'Via deze CORE-herkenner ingedeeld'};
 return `<article class="duplicate-card"><div class="section-title"><strong>${esc(t.booking_date)} · ${money(t.amount)}</strong><span>${esc(t.account_label)}</span></div><dl><dt>Banktegenpartij</dt><dd>${esc(t.bank_counterparty)}</dd><dt>Originele bankomschrijving</dt><dd>${esc(t.description||'Niet aangeleverd')}</dd>${t.recognized_counterparty?`<dt>Door CORE herkende tegenpartij</dt><dd>${esc(t.recognized_counterparty)}</dd>`:''}<dt>Huidige categorie</dt><dd>${esc(t.current_category)}</dd>${t.evidence.length?`<dt>Herkenningsbewijs</dt><dd>${t.evidence.map(e=>esc([e.issuer,e.proprietary,[e.domain,e.family,e.subfamily].filter(Boolean).join('/')].filter(Boolean).join(' · '))).join('<br>')}</dd>`:''}</dl><p>${esc(statuses[t.status]||t.status)}${t.applied?' · Regelversie geregistreerd bij deze indeling':''}</p>`+
 `<button type="button" data-recognizer-transaction="${esc(t.id)}">Bekijk transactie</button></article>`;
}
async function loadRecognizer(){
 const request=++recognizerEpoch,epoch=getSessionEpoch(),id=$('recognizerSelect').value;
 const rule=recognizerRules.find(r=>r.id===id);if(!rule)return;
 $('recognizerDefinition').innerHTML=recognizerDefinition(rule);
 $('recognizerStatus').textContent='Herkenning en voorbeelden ophalen…';$('recognizerCounts').textContent='';$('recognizerExamples').replaceChildren();$('recognizerRefresh').disabled=true;
 try{
  const data=await api('/recognizers/'+encodeURIComponent(id)+'/transactions');
  if(request!==recognizerEpoch||epoch!==getSessionEpoch()||!$('eventRecognizerDialog').open)return;
  $('recognizerStatus').textContent=data.mode==='matching'?`${data.total} betalingen passen bij deze herkenner. Voorbeeldselectie van maximaal 50, verspreid over de periode.`:`${data.total} huidige indelingen met deze regel. Voorbeeldselectie van maximaal 50, verspreid over de periode.`;
  const c=data.counts;
  $('recognizerCounts').textContent=(data.mode==='matching'?`${c.eligible} kunnen worden ingedeeld · ${c.aligned} komen overeen · ${c.manual+c.manual_conflict} handmatig beschermd (${c.manual_conflict} afwijkend) · ${c.protected} overige indelingen beschermd. `:'')+(data.missing_evidence?`${data.missing_evidence} bijschrijvingen hebben geen bruikbare bankcodegegevens; hierover wordt niets aangenomen. `:'')+data.message;
  $('recognizerExamples').innerHTML=data.items.map(recognizerCard).join('')||'<p>Geen passende transacties beschikbaar. Bij oude imports kan de bestaande bankcode-aanvulverwerking nog nodig zijn.</p>';
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
$('showEventRecognizer').onclick=showEventRecognizer;
$('recognizerSelect').onchange=loadRecognizer;
$('recognizerRefresh').onclick=()=>recognizerRules.length?loadRecognizer():showEventRecognizer();
$('eventRecognizerDialog').addEventListener('close',clearEventRecognizer);
reasons.recognizer_scan_limit='Te veel betalingen voor deze directe controle. Er is niets gewijzigd; de gewone indelingsjob blijft beschikbaar.';
reasons.recognizer_not_found='Deze herkenner is niet beschikbaar. Open Eventherkenner opnieuw.';

return {clear:clearEventRecognizer,show:showEventRecognizer,load:loadRecognizer,card:recognizerCard};
}
