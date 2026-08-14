// SCRUM-101: local AI on at most five explicitly selected visible documents.
function aiReasonInDutch(reason){
  const known={invalid_confidence_or_relation:'Confidence of documentrelatie was niet betrouwbaar.',reason_not_dutch:'De AI-toelichting voldeed niet aan de verplichte Nederlandse taal.',model_abstained:'De AI vond onvoldoende bewijs.',provider_response_not_valid_json:'De AI gaf geen geldig voorstel terug.',unknown_taxonomy_value:'Het voorstel paste niet binnen de CORE-taxonomie.'};
  if(known[reason])return known[reason];
  const english=(String(reason).toLowerCase().match(/\b(the|this|are|for|from|with|contains|because|and|human|aligns|related|current|offer)\b/g)||[]).length;
  return english>=2?'Deze historische AI-toelichting was niet Nederlandstalig; de oorspronkelijke lineage blijft auditbaar bewaard.':reason;
}
function selectedAiDocuments(){
  return visibleBulkCheckboxes().filter(box=>box.checked).map(box=>{
    const panel=box.closest('.document-card').querySelector('.review-panel');
    return Number(panel.dataset.fileId);
  });
}
function aiFilterSnapshot(){return{
  status:ws('worksetStatus').value,review_state:ws('worksetReview').value,
  decision:ws('worksetDecision').value,extension:ws('worksetExtension').value,
  family:ws('worksetFamily').value,sort:ws('worksetSort').value,search:ws('worksetSearch').value.trim()
}}
function renderStoredAiProposals(){
  state.documents.forEach(doc=>{
    if(!doc.ai_proposal)return;
    const panel=document.querySelector(`.review-panel[data-file-id="${doc.file_id}"]`);
    if(panel&&!panel.closest('.document-card').querySelector('.ai-info'))applyAiProposal(doc.ai_proposal);
  });
}
function updateAiButton(){
  const ids=selectedAiDocuments(),button=ws('worksetAiAnalyze');
  button.hidden=!state.reviewEnabled;button.disabled=!ids.length||ids.length>5;
  ws('worksetAiHint').textContent=ids.length>5?'Selecteer maximaal 5 documenten':
    ids.length?`${ids.length} geselecteerd voor lokale AI`:'Selecteer 1–5 documenten';
  renderStoredAiProposals();
}
function applyAiProposal(proposal){
  const doc=state.documents.find(item=>Number(item.file_id)===Number(proposal.file_id));
  const panel=document.querySelector(`.review-panel[data-file-id="${proposal.file_id}"]`);
  if(!doc||!panel)return;
  doc.ai_proposal=proposal;panel.dataset.aiProposalId=proposal.id||'';
  if(proposal.status==='ready'){
    const category=panel.querySelector('.review-category');category.value=proposal.category_code;
    updatePanelCategory(panel);const family=panel.querySelector('.review-family');
    if(![...family.options].some(option=>option.value===proposal.family_code)){
      const known=state.taxonomy.families.find(item=>item.code===proposal.family_code);
      family.insertAdjacentHTML('afterbegin',`<option value="${wsEsc(proposal.family_code)}">${wsEsc(known?.label||proposal.family_code)}</option>`);
    }
    family.value=proposal.family_code;refreshTargetPathPreview(panel);
  }
  const documentCard=panel.closest('.document-card'),top=documentCard.querySelector('.document-top');
  let info=top.querySelector('.ai-info');
  if(!info){info=document.createElement('span');info.className='ai-info';top.querySelector('.status-pill').before(info)}
  const ready=proposal.status==='ready',category=state.taxonomy.categories.find(item=>item.code===proposal.category_code),
    family=state.taxonomy.families.find(item=>item.code===proposal.family_code),
    relations={none:'Geen documentrelatie',source_document:'Brondocument',exported_representation:'Geëxporteerde uitvoering',version:'Versie',related_document:'Verwant document'},
    reason=aiReasonInDutch(proposal.reason);
  info.className=`ai-info ${ready?'ready':'abstained'}`;
  info.innerHTML=`<button type="button" class="ai-info-button" aria-expanded="false" aria-label="AI-informatie voor ${wsEsc(doc.filename)}">AI</button>
    <section class="ai-info-popover" role="tooltip" hidden>
      <strong>${ready?'AI-voorstel beschikbaar':'AI heeft zich onthouden'}</strong>
      <dl><dt>Status</dt><dd>${wsEsc(proposal.status)}</dd>${ready?`<dt>Categorie</dt><dd>${wsEsc(category?.label||proposal.category_code)}</dd><dt>Familie</dt><dd>${wsEsc(family?.label||proposal.family_code)}</dd>`:''}<dt>Confidence</dt><dd>${wsEsc(proposal.confidence)}</dd><dt>Reden</dt><dd>${wsEsc(reason)}</dd>${ready?`<dt>Privacyadvies</dt><dd>${wsEsc(proposal.privacy_advice)}</dd><dt>Relatie</dt><dd>${wsEsc(relations[proposal.relation_kind]||proposal.relation_kind)}</dd>`:''}<dt>Model</dt><dd>${wsEsc(proposal.model_id)}</dd><dt>Prompt</dt><dd>${wsEsc(proposal.prompt_version)}</dd><dt>Analyse</dt><dd>${wsEsc(wsDt(proposal.created_at))}</dd></dl>
      <small>AI-advies; niets is automatisch bevestigd.</small>
    </section>`;
}
async function analyzeSelectedWithAi(){
  const ids=selectedAiDocuments(),button=ws('worksetAiAnalyze'),hint=ws('worksetAiHint');
  if(!ids.length||ids.length>5)return;button.disabled=true;hint.textContent='Lokale AI analyseert; dit kan even duren…';
  try{
    const response=await fetch('/api/v1/workset/ai-runs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({idempotency_key:reviewId(),file_ids:ids,filter_snapshot:aiFilterSnapshot()})});
    if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.detail||`HTTP ${response.status}`)}const data=await response.json();
    data.proposals.forEach(applyAiProposal);hint.textContent=`${data.proposals.length} AI-voorstellen klaar voor jouw beoordeling.`;
  }catch(error){hint.textContent=`AI-analyse mislukt: ${error.message}`}
  finally{button.disabled=false}
}
document.addEventListener('change',event=>{if(event.target.closest('.bulk-select'))updateAiButton()});
document.addEventListener('click',event=>{
  const button=event.target.closest('.ai-info-button');
  document.querySelectorAll('.ai-info-button[aria-expanded="true"]').forEach(open=>{
    if(open!==button){open.setAttribute('aria-expanded','false');open.nextElementSibling.hidden=true}
  });
  if(!button)return;
  const popover=button.nextElementSibling,open=button.getAttribute('aria-expanded')!=='true';
  button.setAttribute('aria-expanded',String(open));popover.hidden=!open;
});
document.addEventListener('keydown',event=>{
  if(event.key!=='Escape')return;
  document.querySelectorAll('.ai-info-button[aria-expanded="true"]').forEach(button=>{
    button.setAttribute('aria-expanded','false');button.nextElementSibling.hidden=true;button.focus();
  });
});
document.addEventListener('workset:rendered',updateAiButton);
ws('worksetAiAnalyze').addEventListener('click',analyzeSelectedWithAi);
