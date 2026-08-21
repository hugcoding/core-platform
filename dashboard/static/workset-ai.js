// SCRUM-106: individual, asynchronous and human-controlled AI requests.
const aiQueue={
  jobs:new Map(),
  summary:{},
  refreshTimer:null,
  loaded:false
};
const ocrQueue={jobs:new Map(),loaded:false};
function aiStatusLabel(status){return({pending:'Wachtend',running:'Bezig',ready:'Voorstel gereed',failed:'Mislukt',abstained:'Onvoldoende bewijs',cancelled:'Vervallen'})[status]||status}
function aiReasonInDutch(reason){const known={waiting_for_cpu:'Wacht op lagere CPU-belasting',waiting_for_memory:'Wacht op voldoende vrij geheugen',core_pipeline_priority:'CORE-verwerking heeft voorrang',ai_worker_busy:'De lokale AI-worker is bezig',provider_unavailable:'De lokale AI-provider is niet bereikbaar',ocr_required_from_existing_evidence:'OCR was al door CORE vastgesteld voor deze bestandsinhoud',ocr_recommended_no_extractable_text:'Geen herkenbare tekst gevonden; OCR wordt aanbevolen',no_extractable_text:'Geen uitleesbare tekst gevonden'};return known[reason]||reason||''}
async function refreshAiQueue(){try{const [response,ocrResponse]=await Promise.all([fetch('/api/v1/workset/ai-jobs',{cache:'no-store'}),fetch('/api/v1/workset/ocr-jobs',{cache:'no-store'})]);if(!response.ok)throw Error(response.status);const data=await response.json();aiQueue.summary=data.summary;aiQueue.jobs=new Map(data.jobs.map(job=>[Number(job.file_id),job]));aiQueue.loaded=true;if(ocrResponse.ok){const ocr=await ocrResponse.json();ocrQueue.jobs=new Map(ocr.jobs.map(job=>[Number(job.file_id),job]));ocrQueue.loaded=true}renderAiBell(data.jobs);decorateAiActions()}catch(error){const bell=document.querySelector('.ai-notification');if(bell)bell.title='AI- of OCR-wachtrij niet beschikbaar'}}
function ensureAiBell(){let bell=document.querySelector('.ai-notification');if(bell)return bell;bell=document.createElement('div');bell.className='ai-notification';bell.innerHTML=`<button type="button" class="ai-bell" aria-expanded="false" aria-label="AI-voorstellen"><span aria-hidden="true">&#128276;</span><b>0</b></button><section class="ai-ready-list" hidden><strong>AI-voorstellen gereed</strong><div></div></section>`;document.querySelector('.workset-page header').append(bell);bell.querySelector('.ai-bell').addEventListener('click',()=>{const list=bell.querySelector('.ai-ready-list'),open=list.hidden;list.hidden=!open;bell.querySelector('.ai-bell').setAttribute('aria-expanded',String(open))});bell.addEventListener('click',event=>{const item=event.target.closest('[data-ai-ready-file]');if(!item)return;ws('worksetSearch').value=item.dataset.filename;bell.querySelector('.ai-ready-list').hidden=true;loadWorkset(true)});return bell}
function isOcrAdvice(job){return job?.status==='abstained'&&['ocr_required_from_existing_evidence','ocr_recommended_no_extractable_text'].includes(job.reason)}
function renderAiBell(jobs){const bell=ensureAiBell(),ready=jobs.filter(job=>(job.status==='ready'&&job.awaiting_human_review)||isOcrAdvice(job));bell.querySelector('.ai-bell b').textContent=ready.length;bell.classList.toggle('has-ready',ready.length>0);bell.querySelector('.ai-ready-list div').innerHTML=ready.length?ready.map(job=>`<button type="button" data-ai-ready-file="${job.file_id}" data-filename="${wsEsc(job.filename)}"><span>${wsEsc(job.filename)}</span><small>${wsEsc(isOcrAdvice(job)?'OCR aanbevolen':aiStatusLabel(job.status))}</small></button>`).join(''):'<p>Geen nieuwe voorstellen of OCR-adviezen.</p>'}
function aiInfo(proposal){if(!proposal)return'';return`<span class="ai-info"><button type="button" class="ai-info-button" aria-expanded="false" aria-label="AI-informatie">AI</button><span class="ai-info-popover" role="tooltip" hidden><strong>AI-analyse</strong><dl><dt>Status</dt><dd>${wsEsc(aiStatusLabel(proposal.status))}</dd><dt>Confidence</dt><dd>${wsEsc(proposal.confidence)}</dd><dt>Reden</dt><dd>${wsEsc(aiReasonInDutch(proposal.reason))}</dd><dt>Privacy</dt><dd>${wsEsc(proposal.privacy_advice)}</dd><dt>Model</dt><dd>${wsEsc(proposal.model_id)}</dd><dt>Prompt</dt><dd>${wsEsc(proposal.prompt_version)}</dd></dl><small>${wsEsc(proposal.created_at||proposal.proposal_created_at)}</small></span></span>`}
function ocrStatusLabel(status){return({pending:'OCR wacht',running:'OCR bezig',ready:'OCR gereed',failed:'OCR mislukt',cancelled:'OCR vervallen'})[status]||status}
function aiAction(job,doc,ocrJob){if(!job)return`<button type="button" class="request-ai" data-ai-file="${doc.file_id}">Vraag AI-voorstel aan</button><span class="ai-job-message"></span>`;const ocrRecommended=isOcrAdvice(job),knownOcr=job.reason==='ocr_required_from_existing_evidence',retry=['failed','cancelled'].includes(job.status)||job.status==='abstained'&&!ocrRecommended||ocrJob?.status==='ready'?`<button type="button" class="request-ai" data-ai-file="${doc.file_id}">${ocrJob?.status==='ready'?'Vraag AI na OCR':'Opnieuw aanvragen'}</button>`:'',ocrButton=!ocrJob?`<button type="button" class="request-ocr" data-ocr-file="${doc.file_id}">OCR starten</button>`:'',ocrState=ocrJob?`<span class="ocr-job-status ${wsEsc(ocrJob.status)}">${wsEsc(ocrStatusLabel(ocrJob.status))}${ocrJob.waiting_reason?` — ${wsEsc(aiReasonInDutch(ocrJob.waiting_reason))}`:''}${ocrJob.status==='ready'?` · ${wsEsc(ocrJob.pages)} pagina's`:''}</span>`:'',ocr=ocrRecommended?`<span class="ai-ocr-advice" role="status"><strong>${knownOcr?'OCR vereist — reeds vastgesteld':'OCR aanbevolen'}</strong><small>${knownOcr?'CORE hergebruikte actuele extractie-evidence voor dezelfde bestandsinhoud.':'CORE vond geen herkenbare tekst.'} ${ocrJob?.status==='ready'?'OCR is gereed; vraag nu opnieuw een AI-voorstel aan.':'Het originele bestand blijft ongewijzigd.'}</small>${ocrState}${ocrButton}</span>`:'',accept=job.status==='ready'
  ? `<button type="button" class="review-ai" data-ai-file="${doc.file_id}">Bekijk AI-voorstel</button>`
  : '';return`<span class="ai-job-status ${wsEsc(job.status)}">AI: ${wsEsc(ocrRecommended?'OCR aanbevolen':aiStatusLabel(job.status))}${job.waiting_reason?` - ${wsEsc(aiReasonInDutch(job.waiting_reason))}`:''}</span>${aiInfo(job)}${ocr}${accept}${retry}<span class="ai-job-message"></span>`}
function decorateAiActions(){document.querySelectorAll('.document-card').forEach((card,index)=>{const doc=state.documents[index];if(!doc)return;let actions=card.querySelector('.ai-document-actions');if(!actions){actions=document.createElement('div');actions.className='ai-document-actions';const lifecycle=card.querySelector('.lifecycle-review'),privacy=card.querySelector('.privacy-review');if(lifecycle)lifecycle.before(actions);else if(privacy)privacy.before(actions);else card.querySelector('.document-main').append(actions)}actions.dataset.fileId = doc.file_id;

const job = aiQueue.jobs.get(Number(doc.file_id));
const ocrJob = ocrQueue.jobs.get(Number(doc.file_id));

actions.innerHTML = !aiQueue.loaded
  ? `<span class="ai-job-status">AI laden…</span>`
  : aiAction(job, doc, ocrJob);})}
async function requestAi(fileId,actions){const message=actions.querySelector('.ai-job-message');message.textContent='Aanvraag toevoegen...';actions.querySelectorAll('button').forEach(button=>button.disabled=true);try{const response=await fetch('/api/v1/workset/ai-jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:Number(fileId),idempotency_key:reviewId()})});const data=await response.json();if(!response.ok)throw Error(data.detail||response.status);message.textContent='AI-aanvraag staat in de wachtrij';await refreshAiQueue()}catch(error){message.textContent=`Aanvraag mislukt: ${error.message}`;actions.querySelectorAll('button').forEach(button=>button.disabled=false)}}
async function requestOcr(fileId,actions){const message=actions.querySelector('.ai-job-message');message.textContent='OCR-aanvraag toevoegen...';actions.querySelectorAll('button').forEach(button=>button.disabled=true);try{const response=await fetch('/api/v1/workset/ocr-jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_id:Number(fileId),idempotency_key:reviewId()})});const body=await response.text();let data={};try{data=body?JSON.parse(body):{}}catch(parseError){data={detail:body||`HTTP ${response.status}`}}if(!response.ok)throw Error(data.detail||response.status);message.textContent='OCR staat in de wachtrij';await refreshAiQueue()}catch(error){message.textContent=`OCR-aanvraag mislukt: ${error.message}`;actions.querySelectorAll('button').forEach(button=>button.disabled=false)}}
function ensureAiDialog(){
  let dialog=document.getElementById('aiProposalDialog');
  if(dialog)return dialog;

  dialog=document.createElement('dialog');
  dialog.id='aiProposalDialog';
  dialog.className='ai-proposal-dialog';

  dialog.innerHTML=`
    <form method="dialog">
      <header>
        <div>
          <p class="eyebrow">LOKAAL AI-ADVIES</p>
          <h2>AI-voorstel gebruiken?</h2>
        </div>
        <button value="cancel" aria-label="Sluiten">x</button>
      </header>

      <p>
        Neem het voorstel over als startpunt. Je kunt categorie, familie,
        privacy en lifecycle daarna nog aanpassen voordat je bevestigt.
      </p>

      <dl class="ai-proposal-diff"></dl>

      <p class="ai-accept-message" aria-live="polite"></p>

    <footer>
    <button value="cancel">Terug</button>
    <button type="button" class="dismiss-ai-proposal" value="dismiss">
    Negeren
    </button>
    <button type="button" class="apply-ai-proposal">
        Gebruik als beoordeling
    </button>
    </footer>
    </form>`;

  document.body.append(dialog);
  return dialog;
}
function reviewAi(fileId){const job=aiQueue.jobs.get(Number(fileId));if(!job||job.status!=='ready')return;const dialog=ensureAiDialog(),labels={low:'Laag',medium:'Middel',high:'Hoog',active:'Actief',archive:'Inactief / archief',needs_review:'Later beoordelen'},category=state.taxonomy.categories.find(item=>item.code===job.category_code)?.label||job.category_code,family=state.taxonomy.families.find(item=>item.code===job.family_code)?.label||job.family_code;dialog.dataset.jobId=job.id;dialog.querySelector('.ai-proposal-diff').innerHTML=`<dt>Document</dt><dd>${wsEsc(job.filename)}</dd><dt>Bestandsnaam</dt><dd>${wsEsc(job.suggested_filename||job.filename)} (ongewijzigd)</dd><dt>Doelpad</dt><dd>${wsEsc(job.suggested_target_path)}</dd><dt>Categorie</dt><dd>${wsEsc(category)}</dd><dt>Familie</dt><dd>${wsEsc(family)}</dd><dt>Privacy</dt><dd>${wsEsc(labels[job.privacy_advice]||job.privacy_advice)}</dd><dt>Lifecycle</dt><dd>${wsEsc(labels[job.lifecycle]||job.lifecycle)}</dd><dt>Confidence</dt><dd>${wsEsc(job.confidence)}</dd><dt>Reden</dt><dd>${wsEsc(job.reason)}</dd><dt>Model</dt><dd>${wsEsc(job.model_id)}</dd><dt>Prompt</dt><dd>${wsEsc(job.prompt_version)}</dd>`;dialog.querySelector('.ai-accept-message').textContent='';dialog.showModal()}
async function acceptCompleteAi(dialog){const button=dialog.querySelector('.accept-complete-ai'),message=dialog.querySelector('.ai-accept-message');button.disabled=true;message.textContent='Menselijke beoordelingen opslaan...';try{const response=await fetch(`/api/v1/workset/ai-jobs/${dialog.dataset.jobId}/accept`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({idempotency_key:reviewId()})});const data=await response.json();if(!response.ok)throw Error(data.detail||response.status);message.textContent='Volledig voorstel is als menselijk oordeel opgeslagen';setTimeout(()=>{dialog.close();
refreshAiQueue();loadWorkset(true)},700)}catch(error){message.textContent=`Overnemen mislukt: ${error.message}`;button.disabled=false}}
document.addEventListener('click', event => {
  const info = event.target.closest('.ai-info-button');

  if (info) {
    const popover = info.nextElementSibling;
    const open = popover.hidden;

    popover.hidden = !open;
    info.setAttribute('aria-expanded', String(open));
    return;
  }

  const request = event.target.closest('.request-ai');

  if (request) {
    requestAi(
      request.dataset.aiFile,
      request.closest('.ai-document-actions')
    );
    return;
  }

  const ocrRequest = event.target.closest('.request-ocr');
  if (ocrRequest) {
    requestOcr(
      ocrRequest.dataset.ocrFile,
      ocrRequest.closest('.ai-document-actions')
    );
    return;
  }

const review = event.target.closest('.review-ai');

if (review) {
  reviewAi(review.dataset.aiFile);
  return;
}

if (event.target.closest('.dismiss-ai-proposal')) {
  event.preventDefault();
  event.stopPropagation();
  dismissAiProposal(event.target.closest('dialog'));
  return;
}

if (event.target.closest('.apply-ai-proposal')) {
  event.preventDefault();
  event.stopPropagation();
  applyAiProposalToForm(event.target.closest('dialog'));
  return;
}
});

document.addEventListener('workset:rendered', () => {
  decorateAiActions();
});

// Meteen AI-status ophalen zodra het script geladen is.
refreshAiQueue();

// Daarna periodiek verversen.
aiQueue.refreshTimer = setInterval(refreshAiQueue, 15000);

async function applyAiProposalToForm(dialog) {
  const jobId = dialog.dataset.jobId;

  const job = [...aiQueue.jobs.values()]
    .find(item => String(item.id) === String(jobId));

  if (!job) {
    dialog.querySelector('.ai-accept-message').textContent =
      'AI-voorstel niet meer beschikbaar.';
    return;
  }

  const card = [...document.querySelectorAll('.document-card')]
    .find(card => {
      const actions = card.querySelector('.ai-document-actions');
      return Number(actions?.dataset.fileId) === Number(job.file_id);
    });

  if (!card) {
    dialog.querySelector('.ai-accept-message').textContent =
      'Documentkaart niet meer zichtbaar.';
    return;
  }

  // Categorie + familie
  const reviewPanel = card.querySelector('.review-panel');

  if (reviewPanel) {
    const categorySelect = reviewPanel.querySelector('.review-category');

    if (categorySelect && job.category_code) {
      categorySelect.value = job.category_code;

      // Laat bestaande CORE-logica de family dropdown opnieuw opbouwen.
      categorySelect.dispatchEvent(
        new Event('change', { bubbles: true })
      );
    }

    const familySelect = reviewPanel.querySelector('.review-family');

if (familySelect && job.family_code) {
  const validFamilies = state.taxonomy.families.filter(
    item => item.categories.includes(job.category_code)
  );

  // AI-familie eerst.
  const orderedFamilies = [];

  const addFamily = family => {
    if (
      family &&
      !orderedFamilies.some(item => item.code === family.code)
    ) {
      orderedFamilies.push(family);
    }
  };

  addFamily(
    validFamilies.find(item => item.code === job.family_code)
  );

  // Voeg families toe waarvan keywords letterlijk in de AI-redenering voorkomen.
  const reason = String(job.reason || '').toLowerCase();

  for (const family of validFamilies) {
    const matched = (family.keywords || []).some(
      keyword => reason.includes(String(keyword).toLowerCase())
    );

    if (matched) {
      addFamily(family);
    }
  }

  // Daarna bestaande opties behouden.
  for (const option of [...familySelect.options]) {
    addFamily(
      state.taxonomy.families.find(
        item => item.code === option.value
      )
    );
  }

  familySelect.innerHTML = orderedFamilies
    .map(
      family =>
        `<option value="${wsEsc(family.code)}">` +
        `${wsEsc(family.label)}</option>`
    )
    .join('');

  familySelect.value = job.family_code;
}

    const reviewMessage = reviewPanel.querySelector('.review-message');

    if (reviewMessage) {
      reviewMessage.textContent =
        'AI-voorstel toegepast. Controleer categorie en familie vóór akkoord.';
    }
  }

  // Privacy
  const privacySelect = card.querySelector('.privacy-classification');

  if (
    privacySelect &&
    ['low', 'medium', 'high'].includes(job.privacy_advice)
  ) {
    privacySelect.value = job.privacy_advice;

    const privacyMessage = card.querySelector('.privacy-message');
    if (privacyMessage) {
      privacyMessage.textContent =
        'AI-privacyvoorstel ingevuld; nog niet opgeslagen.';
    }
  }

  // Lifecycle:
  // alleen visueel selecteren, NIET submitLifecycle() aanroepen.
  if (
    ['active', 'archive', 'needs_review'].includes(job.lifecycle)
  ) {
    const lifecycle = card.querySelector('.lifecycle-review');

    if (lifecycle) {
      lifecycle.querySelectorAll('[data-lifecycle]')
        .forEach(button => {
          button.classList.toggle(
            'selected',
            button.dataset.lifecycle === job.lifecycle
          );
        });

      lifecycle.dataset.aiLifecycle = job.lifecycle;

      const lifecycleMessage =
        lifecycle.querySelector('.lifecycle-message');

      if (lifecycleMessage) {
        lifecycleMessage.textContent =
          'AI-lifecyclevoorstel gemarkeerd; nog niet opgeslagen.';
      }
    }
  }
    try {
    await fetch(
        `/api/v1/workset/ai-jobs/${job.id}/dismiss`,
        {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
        }
    );
    } catch (error) {
    console.warn('AI voorstel kon niet als afgehandeld worden gemarkeerd', error);
    }
  dialog.close();

  card.scrollIntoView({
    behavior: 'smooth',
    block: 'center'
  });
  await refreshAiQueue();
}
  
async function dismissAiProposal(dialog) {
  const jobId = dialog?.dataset?.jobId;
  const message = dialog?.querySelector('.ai-accept-message');
  const button = dialog?.querySelector('.dismiss-ai-proposal');

  if (!jobId) {
    if (message) {
      message.textContent = 'AI-job niet beschikbaar.';
    }
    return;
  }

  if (button) {
    button.disabled = true;
  }

  if (message) {
    message.textContent = 'Voorstel negeren…';
  }

  try {
    const response = await fetch(
      `/api/v1/workset/ai-jobs/${jobId}/dismiss`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw Error(data.detail || response.status);
    }

    dialog.close();

    await refreshAiQueue();
  } catch (error) {
    if (message) {
      message.textContent = `Negeren mislukt: ${error.message}`;
    }

    if (button) {
      button.disabled = false;
    }
  }
}
