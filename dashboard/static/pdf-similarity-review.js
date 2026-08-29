(() => {
  const section=document.getElementById('pdfSimilaritySection'), list=document.getElementById('pdfSimilarityGroups');
  const count=document.getElementById('pdfSimilarityPendingCount'), summary=document.getElementById('pdfSimilaritySummary');
  const state=document.getElementById('pdfSimilarityState');
  if(!section||!list||!count||!summary||!state)return;
  const esc=value=>String(value??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const id=()=>{
    if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
    const randomByte=()=>globalThis.crypto?.getRandomValues?globalThis.crypto.getRandomValues(new Uint8Array(1))[0]:Math.floor(Math.random()*256);
    const values=Array.from({length:16},randomByte);values[6]=(values[6]&15)|64;values[8]=(values[8]&63)|128;
    const hex=values.map(value=>value.toString(16).padStart(2,'0'));
    return `${hex.slice(0,4).join('')}-${hex.slice(4,6).join('')}-${hex.slice(6,8).join('')}-${hex.slice(8,10).join('')}-${hex.slice(10).join('')}`;
  };
  function card(group){
    const reviewed=['same_document_version','keep_separate'].includes(group.latest_review_action);
    const members=group.members.map(m=>`<div class="duplicate-member"><span><strong>${esc(m.filename)}</strong><small>${esc(m.path)}</small><em>File ${Number(m.file_id)} · SHA-256 ${esc(m.content_sha256).slice(0,16)}…</em></span></div>`).join('');
    return `<article class="duplicate-group" data-key="${esc(group.group_key)}"><header><div><strong>${Number(group.available_documents)} inhoudelijk vergelijkbare pdf's</strong><small>Genormaliseerde tekst ${esc(group.group_key).slice(0,16)}… · ${Number(group.page_count)} pagina('s)</small></div><span class="duplicate-state ${reviewed?'reviewed':''}">${reviewed?'beoordeeld':'te beoordelen'}</span></header><div class="duplicate-members">${members}</div><label class="duplicate-notes">Toelichting<input maxlength="2000" value="${esc(group.review_notes||'')}" placeholder="Optioneel"></label><div class="duplicate-actions"><button type="button" data-action="same_document_version">Zelfde documentversie</button><button type="button" data-action="keep_separate">Bewust apart bewaren</button>${reviewed?'<button type="button" data-action="withdrawn">Oordeel intrekken</button>':''}<span class="duplicate-message"></span></div></article>`;
  }
  async function load(){
    list.innerHTML='<div class="empty-state">PDF-vergelijkingen laden…</div>';
    try{const response=await fetch(`/api/v1/workset/pdf-similarity?review_state=${encodeURIComponent(state.value)}&limit=100`,{cache:'no-store'});const data=await response.json();if(!response.ok)throw Error(data.detail||response.status);section.dataset.writes=data.review_writes_enabled?'true':'false';count.textContent=`${Number(data.summary.pending)} te beoordelen`;summary.innerHTML=`<span>${Number(data.summary.total)} groepen</span><span>${Number(data.summary.reviewed)} beoordeeld</span>`;list.innerHTML=data.groups.length?data.groups.map(card).join(''):'<div class="empty-state">Geen inhoudelijk vergelijkbare pdf-groepen.</div>';}catch(error){list.innerHTML=`<div class="empty-state error">Laden mislukt: ${esc(error.message)}</div>`;}
  }
  list.addEventListener('click',async event=>{const button=event.target.closest('[data-action]'), article=event.target.closest('.duplicate-group');if(!button||!article)return;const message=article.querySelector('.duplicate-message');if(section.dataset.writes!=='true'){message.textContent='Interactieve beoordeling staat uit.';return;}article.querySelectorAll('button,input').forEach(el=>el.disabled=true);try{const response=await fetch('/api/v1/workset/pdf-similarity-reviews',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({group_key:article.dataset.key,action:button.dataset.action,idempotency_key:id(),review_notes:article.querySelector('input').value.trim()})});const data=await response.json();if(!response.ok)throw Error(data.detail||response.status);message.textContent='Oordeel append-only opgeslagen; bestanden blijven ongewijzigd.';setTimeout(load,400);}catch(error){message.textContent=`Opslaan mislukt: ${error.message}`;article.querySelectorAll('button,input').forEach(el=>el.disabled=false);}});
  state.addEventListener('change',load);section.addEventListener('toggle',()=>{if(section.open)load();});load();
})();
