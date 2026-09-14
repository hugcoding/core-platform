// SCRUM-146: visible, advisory-only explanation for reused human judgments.
function renderSimilarDocumentProposals(){
  document.querySelectorAll('.document-card').forEach(card=>{
    if(card.querySelector('.similar-proposal'))return;
    const title=card.querySelector('.document-top strong')?.textContent||'';
    const doc=state.documents.find(item=>item.filename===title);
    const similar=doc?.similar_document_proposal;
    if(!similar)return;
    const peers=(similar.documents||[]).map(peer=>
      `<li><b>${wsEsc(peer.filename)}</b> <span>${wsEsc(peer.extension).toUpperCase()}${peer.human_reviewed?` · menselijk beoordeeld · review ${wsEsc(peer.source_review_event_id||'onbekend')}`:''}</span></li>`
    ).join('');
    const conflict=similar.status==='conflicting_reviews_require_review';
    const box=document.createElement('aside');
    box.className=`similar-proposal${conflict?' conflict':''}`;
    box.innerHTML=conflict
      ? `<strong>Overeenkomstige documenten hebben verschillende beoordelingen</strong><p>CORE neemt daarom niets over. Beoordeel dit document afzonderlijk.</p><ul>${peers}</ul>`
      : `<strong>Gebaseerd op eerder beoordeelde, overeenkomstige documenten</strong><p>${Number(similar.support_count||0)} van ${Number(similar.review_count||0)} beoordelingen ondersteunen dit voorstel. Doelpad en privacy worden apart bepaald.</p><ul>${peers}</ul><small>Overeenkomst ${Math.round(Number(similar.score||0)*100)}% · regel ${wsEsc(similar.rule_version||'onbekend')} · nog steeds jouw keuze</small>`;
    const target=card.querySelector('.target-proposal');
    (target||card.querySelector('.document-main>code'))?.after(box);
  });
}

document.addEventListener('workset:rendered',renderSimilarDocumentProposals);
