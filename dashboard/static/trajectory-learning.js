// SCRUM-98: explain deterministic, proposal-only trajectory learning.
function renderTrajectoryLearning(){
  document.querySelectorAll('.document-card').forEach((card,index)=>{
    const doc=state.documents[index],evidence=doc?.trajectory_learning_proposal;
    if(!evidence||card.querySelector('.trajectory-learning'))return;
    const target=card.querySelector('.target-proposal');if(!target)return;
    const panel=document.createElement('div');panel.className='trajectory-learning';
    panel.innerHTML=`<strong>Geleerd van jouw doelpadkeuzes</strong><p><b>${wsEsc(evidence.trajectory_label)}</b> wordt voorgesteld omdat <b>${wsEsc(evidence.match_term)}</b> in dit document is herkend.</p><small>${wsNf.format(evidence.support)} consistente beoordelingen &middot; ${Math.round(evidence.agreement*100)}% overeenstemming &middot; ${wsNf.format(evidence.counterexample_count)} tegenvoorbeelden &middot; alleen voorstel</small><details><summary>Bronbeoordelingen</summary><code>${evidence.source_review_event_ids.map(wsEsc).join('<br>')}</code></details>`;
    target.after(panel);
  });
}
document.addEventListener('workset:rendered',renderTrajectoryLearning);
