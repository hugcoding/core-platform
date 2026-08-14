// SCRUM-98: visible, advisory-only explanation for reused human judgments.
function renderSimilarDocumentProposals(){
  document.querySelectorAll('.document-card').forEach(card=>{
    if(card.querySelector('.similar-proposal'))return;
    const title=card.querySelector('.document-top strong')?.textContent||'';
    const doc=state.documents.find(item=>item.filename===title);
    const similar=doc?.similar_document_proposal;
    if(!similar)return;
    const peers=(similar.documents||[]).map(peer=>
      `<li><b>${wsEsc(peer.filename)}</b> <span>${wsEsc(peer.extension).toUpperCase()}${peer.human_reviewed?' · menselijk beoordeeld':''}</span></li>`
    ).join('');
    const conflict=similar.status==='conflicting_reviews_require_review';
    const box=document.createElement('aside');
    box.className=`similar-proposal${conflict?' conflict':''}`;
    box.innerHTML=conflict
      ? `<strong>Overeenkomstige documenten hebben verschillende beoordelingen</strong><p>CORE neemt daarom niets over.</p><ul>${peers}</ul>`
      : `<strong>Gebaseerd op een eerder beoordeeld, overeenkomstig document</strong><p>Dezelfde categorie en familie worden voorgesteld. Doelpad wordt apart opgebouwd; privacy blijft apart.</p><ul>${peers}</ul><small>Overeenkomst ${Math.round(Number(similar.score||0)*100)}% · nog steeds jouw keuze</small>`;
    const target=card.querySelector('.target-proposal');
    (target||card.querySelector('.document-main>code'))?.after(box);
  });
}

document.addEventListener('workset:rendered',renderSimilarDocumentProposals);
