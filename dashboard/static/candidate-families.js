// SCRUM-98: show repeated human family proposals without activating taxonomy rules.
function renderCandidateFamilies(){
  document.querySelectorAll('.document-card').forEach((card,index)=>{
    const panel=card.querySelector('.review-panel');if(!panel||panel.querySelector('.candidate-families'))return;
    const category=panel.querySelector('.review-category')?.value;
    const candidates=(state.documents[index]?.review_options?.candidate_families||[]).filter(item=>item.category_code===category);
    if(!candidates.length)return;
    const box=document.createElement('div');box.className='candidate-families';
    box.innerHTML=`<strong>Geleerde kandidaatfamilies</strong>${candidates.map((item,candidateIndex)=>`<div><button type="button" data-candidate-index="${candidateIndex}">Gebruik ${wsEsc(item.family_label)}</button><span>${wsNf.format(item.support)} bevestigingen &middot; alleen kandidaat</span><details><summary>Bronnen</summary><code>${item.source_review_event_ids.map(wsEsc).join('<br>')}</code></details></div>`).join('')}`;
    panel.querySelector('.review-family')?.closest('label')?.after(box);
    box.addEventListener('click',event=>{
      const button=event.target.closest('[data-candidate-index]');if(!button)return;
      const candidate=candidates[Number(button.dataset.candidateIndex)],details=panel.querySelector('.new-proposal');
      details.open=true;panel.querySelector('.proposed-family').value=candidate.family_label;
      panel.querySelector('.review-message').textContent=`${candidate.family_label} is ingevuld als nieuw familievoorstel; bevestig nog met jouw oordeel.`;
    });
  });
}
document.addEventListener('workset:rendered',renderCandidateFamilies);
document.addEventListener('change',event=>{
  if(!event.target.matches('.review-category'))return;
  document.querySelectorAll('.candidate-families').forEach(item=>item.remove());renderCandidateFamilies();
});
