// SCRUM-101: local AI on at most five explicitly selected visible documents.
function selectedAiDocuments(){
  return visibleBulkCheckboxes().filter(box=>box.checked).map(box=>{
    const panel=box.closest('.document-card').querySelector('.review-panel');
    return Number(panel.dataset.fileId);
  });
}
function aiFilterSnapshot(){return{
  status:ws('worksetStatus').value,review_state:ws('worksetReview').value,
  decision:ws('worksetDecision').value,extension:ws('worksetExtension').value,
  family:ws('worksetFamily').value,search:ws('worksetSearch').value.trim()
}}
function renderStoredAiProposals(){
  state.documents.forEach(doc=>{
    if(!doc.ai_proposal)return;
    const panel=document.querySelector(`.review-panel[data-file-id="${doc.file_id}"]`);
    if(panel&&!panel.closest('.document-card').querySelector('.ai-proposal'))applyAiProposal(doc.ai_proposal);
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
  let card=panel.closest('.document-card').querySelector('.ai-proposal');
  if(!card){card=document.createElement('aside');card.className='ai-proposal';panel.before(card)}
  card.innerHTML=proposal.status==='ready'
    ? `<strong>Lokale AI-voorstel</strong><span>${wsEsc(proposal.confidence)} · ${wsEsc(proposal.relation_kind)}</span><p>${wsEsc(proposal.reason)}</p><small>Privacyadvies ${wsEsc(proposal.privacy_advice)} blijft apart te bevestigen.</small>`
    : `<strong>Lokale AI onthoudt zich</strong><p>${wsEsc(proposal.reason)}</p>`;
}
async function analyzeSelectedWithAi(){
  const ids=selectedAiDocuments(),button=ws('worksetAiAnalyze'),hint=ws('worksetAiHint');
  if(!ids.length||ids.length>5)return;button.disabled=true;hint.textContent='Lokale AI analyseert; dit kan even duren…';
  try{
    const response=await fetch('/api/v1/workset/ai-runs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({idempotency_key:reviewId(),file_ids:ids,filter_snapshot:aiFilterSnapshot()})});
    if(!response.ok)throw Error(response.status);const data=await response.json();
    data.proposals.forEach(applyAiProposal);hint.textContent=`${data.proposals.length} AI-voorstellen klaar voor jouw beoordeling.`;
  }catch(error){hint.textContent='Lokale AI is niet beschikbaar of de selectie is verouderd.'}
  finally{button.disabled=false}
}
document.addEventListener('change',event=>{if(event.target.closest('.bulk-select'))updateAiButton()});
new MutationObserver(updateAiButton).observe(ws('worksetDocuments'),{childList:true,subtree:true});
ws('worksetAiAnalyze').addEventListener('click',analyzeSelectedWithAi);
