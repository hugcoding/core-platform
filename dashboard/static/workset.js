// SCRUM-98 controlled path assistance. Suggestions are advisory until clicked.
let activePathReviewPanel = null, pathSuggestionTimer = null, pathSuggestionController = null, pathSuggestionSequence = 0;
const nativeFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = (resource, options = {}) => {
  if (String(resource) === '/api/v1/workset/reviews' && activePathReviewPanel && options.body) {
    const payload = JSON.parse(options.body), input = activePathReviewPanel.querySelector('.proposed-path');
    const filenameInput = activePathReviewPanel.querySelector('.proposed-filename');
    const doc = state.documents.find(item => String(item.file_id) === String(payload.file_id));
    if (doc?.similar_document_proposal?.status === 'consensus_proposal') payload.similarity_evidence = doc.similar_document_proposal;
    if (activePathReviewPanel.dataset.aiProposalId) payload.ai_proposal_id = activePathReviewPanel.dataset.aiProposalId;
    if (filenameInput && payload.review_type !== 'privacy_classification') payload.proposed_filename = filenameInput.value.trim();
    if (input && payload.review_type !== 'privacy_classification') {
      payload.proposed_target_path_original = input.dataset.originalValue || input.value;
      payload.target_path_suggestion = input.dataset.suggestion || '';
      payload.target_path_suggestion_decision = input.dataset.suggestionDecision || 'no_suggestion';
      options = { ...options, body: JSON.stringify(payload) };
    }
  }
  return nativeFetch(resource, options);
};
function pathSuggestionBox(input) {
  let box = input.parentElement.querySelector('.path-suggestion');
  if (!box) {
    box = document.createElement('div'); box.className = 'path-suggestion'; box.hidden = true;
    box.innerHTML = '<span>Bedoel je <code></code>?</span><button type="button" class="use-path-suggestion">Gebruik dit pad</button><button type="button" class="keep-new-path">Bewust nieuw pad</button>';
    input.parentElement.append(box);
  }
  return box;
}
async function requestPathSuggestion(input) {
  const panel = input.closest('.review-panel'), value = input.value.trim(), box = pathSuggestionBox(input);
  const sequence = ++pathSuggestionSequence;
  if (pathSuggestionController) pathSuggestionController.abort();
  pathSuggestionController = new AbortController();
  input.dataset.originalValue = value; input.dataset.suggestion = ''; input.dataset.suggestionDecision = 'no_suggestion';
  if (!value.startsWith('/')) { box.hidden = true; return }
  input.setAttribute('aria-busy', 'true');
  try {
    const response = await nativeFetch(`/api/v1/workset/${panel.dataset.fileId}/target-path-suggestion?value=${encodeURIComponent(value)}`, { cache: 'no-store', signal: pathSuggestionController.signal });
    if (sequence !== pathSuggestionSequence) return;
    if (!response.ok) { box.hidden = true; return }
    const data = await response.json();
    if (sequence !== pathSuggestionSequence) return;
    if (data.technical_normalization) { input.value = data.suggestion; input.dataset.suggestion = data.suggestion; input.dataset.suggestionDecision = 'accepted'; box.hidden = true; return }
    if (!data.requires_confirmation) { box.hidden = true; return }
    input.dataset.suggestion = data.suggestion; box.querySelector('code').textContent = data.suggestion; box.hidden = false;
  } catch (error) { if (error.name !== 'AbortError' && sequence === pathSuggestionSequence) box.hidden = true }
  finally { if (sequence === pathSuggestionSequence) input.removeAttribute('aria-busy') }
}
async function refreshTargetPathPreview(panel) {
  const category = panel.querySelector('.review-category').value, family = panel.querySelector('.review-family').value;
  const filename = panel.querySelector('.proposed-filename')?.value.trim() || '';
  const manual = panel.querySelector('.proposed-path').value.trim();
  if (!category || !family) return;
  let note = panel.querySelector('.live-path-preview'); if (!note) { note = document.createElement('small'); note.className = 'live-path-preview'; panel.prepend(note) }
  note.textContent = 'Doelpad wordt bijgewerkt...'; note.classList.remove('path-conflict');
  try {
    const response = await nativeFetch(`/api/v1/workset/${panel.dataset.fileId}/target-path-preview?category=${encodeURIComponent(category)}&family=${encodeURIComponent(family)}&filename=${encodeURIComponent(filename)}&target_path=${encodeURIComponent(manual)}`, { cache: 'no-store' });
    if (!response.ok) { note.textContent = 'Doelpad kon niet worden bijgewerkt.'; return }
    const data = await response.json(), card = panel.closest('.document-card'), target = card.querySelector('.target-proposal');
    if (target) { target.querySelector('span').innerHTML = `<i class="source-badge">CORE-preview</i>${wsEsc(data.proposal_confidence)}`; target.querySelector('code').textContent = data.suggested_target_path }
    note.classList.toggle('path-conflict', data.target_path_conflict);
    note.textContent = data.target_path_conflict ? 'Let op: dit volledige doelpad bestaat al of is al geaccepteerd. Het blijft alleen een voorstel.' : manual ? 'Nieuw CORE-voorstel berekend; jouw handmatige doelpad blijft leidend.' : 'Doelpad live herberekend; wordt pas opgeslagen bij jouw beoordeling.';
  } catch (error) { note.textContent = 'Doelpad kon niet worden bijgewerkt.' }
}
document.addEventListener('change', event => {
  if (!event.target.matches('.review-category,.review-family,.all-families')) return;
  const panel = event.target.closest('.review-panel'); setTimeout(() => refreshTargetPathPreview(panel), 0);
});
document.addEventListener('input', event => {
  if (event.target.matches('.proposed-path')) { clearTimeout(pathSuggestionTimer); pathSuggestionTimer = setTimeout(() => requestPathSuggestion(event.target), 300); return }
  if (event.target.matches('.proposed-filename')) { clearTimeout(pathSuggestionTimer); pathSuggestionTimer = setTimeout(() => refreshTargetPathPreview(event.target.closest('.review-panel')), 300) }
});
document.addEventListener('click', event => {
  const reviewButton = event.target.closest('[data-decision]');
  if (reviewButton) activePathReviewPanel = reviewButton.closest('.review-panel');
  const use = event.target.closest('.use-path-suggestion');
  if (use) {
    const box = use.closest('.path-suggestion'), input = box.parentElement.querySelector('.proposed-path');
    input.dataset.originalValue = input.dataset.originalValue || input.value;
    input.value = input.dataset.suggestion; input.dataset.suggestionDecision = 'accepted'; box.hidden = true; return;
  }
  const keep = event.target.closest('.keep-new-path');
  if (keep) {
    const box = keep.closest('.path-suggestion'), input = box.parentElement.querySelector('.proposed-path');
    input.dataset.suggestionDecision = 'new_path'; box.hidden = true;
  }
}, true);
const ws = id => document.getElementById(id), wsNf = new Intl.NumberFormat('nl-NL');
const wsEsc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
const wsDt = value => value ? new Date(value).toLocaleString('nl-NL', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Onbekend';
const wsBytes = value => { let size = Number(value || 0), unit = 0; while (size >= 1024 && unit < 4) { size /= 1024; unit++ } return `${size.toFixed(unit ? 1 : 0)} ${['B', 'KB', 'MB', 'GB', 'TB'][unit]}` };
const reasonLabels = { source_metadata_modified_within_configured_window: 'Recent gewijzigd in documentmetadata', source_metadata_created_within_configured_window: 'Recent aangemaakt volgens documentmetadata', filesystem_mtime_within_configured_window: 'Recent gewijzigd op de opslag', conflicting_temporal_evidence: 'Datums moeten worden beoordeeld', no_qualifying_activity_within_configured_window: 'Geen activiteit binnen het ingestelde venster', invalid_or_missing_activity_timestamp: 'Activiteitsdatum ontbreekt of is ongeldig' };
const decisionLabels = { accepted: 'Akkoord', rejected: 'Niet akkoord', needs_review: 'Uitgesteld', passed: 'Niet beoordelen' };
const privacyReasonLabels = { high_impact_privacy_signal: 'Identiteit of zeer gevoelige inhoud herkend', personal_or_financial_signal: 'Persoonlijke of financiële informatie herkend', existing_normal_classification: 'Geen verhoogd privacyrisico herkend', insufficient_privacy_evidence: 'Nog onvoldoende bewijs; controle gewenst' };
const state = { offset: 0, limit: 50, loading: false, documents: [], families: [], reviewEnabled: false, privacyReviewEnabled: false, lifecycleReviewEnabled: false, nominationEnabled: false, llmEnabled: false, filteredTotal: 0, reviewSummary: {}, nominationSummary: { archive: 0, deletion: 0 }, worksetSummary: {}, taxonomy: { categories: [], families: [] } };
ws('worksetDecision').querySelector('[value="needs_review"]').textContent = 'Uitgesteld';
ws('worksetDecision').querySelector('[value="passed"]').textContent = 'Niet beoordelen';
let bulkPreviewPayload = null;
function visibleBulkCheckboxes() { return [...document.querySelectorAll('.document-card .bulk-select input')] }
function updateBulkControls() {
  const bar = ws('bulkReviewBar'), boxes = visibleBulkCheckboxes(), selected = boxes.filter(box => box.checked);
  bar.hidden = !state.reviewEnabled || !boxes.length; ws('bulkSelectedCount').textContent = `${selected.length} geselecteerd`;
  ws('bulkReviewOpen').disabled = !selected.length; ws('bulkSelectAll').checked = boxes.length > 0 && selected.length === boxes.length;
  ws('bulkSelectAll').indeterminate = selected.length > 0 && selected.length < boxes.length;
}
function decorateBulkCards() {
  document.querySelectorAll('.document-card').forEach(card => {
    if (card.querySelector('.bulk-select')) return;
    const label = document.createElement('label'); label.className = 'bulk-select';
    label.innerHTML = '<input type="checkbox" aria-label="Document selecteren"><span>Selecteer</span>';
    card.prepend(label);
  });
  updateBulkControls();
}
function collectBulkItems() {
  return visibleBulkCheckboxes().filter(box => box.checked).map(box => {
    const card = box.closest('.document-card'), panel = card.querySelector('.review-panel');
    const doc = state.documents.find(item => String(item.file_id) === panel.dataset.fileId);
    return {
      file_id: Number(panel.dataset.fileId), category: panel.querySelector('.review-category').value,
      family: panel.querySelector('.review-family').value, privacy: card.querySelector('.privacy-classification').value,
      manual_target_path: panel.querySelector('.proposed-path').value.trim(),
      similarity_evidence: doc?.similar_document_proposal?.status === 'consensus_proposal' ? doc.similar_document_proposal : null
    };
  })
}
async function openBulkReview() {
  const message = ws('bulkReviewMessage'); message.textContent = 'Voorstellen controleren…';
  const items = collectBulkItems(); if (!items.length) return;
  ws('bulkReviewDialog').showModal();
  try {
    const response = await fetch('/api/v1/workset/reviews/bulk/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) });
    if (!response.ok) throw Error(response.status); const data = await response.json();
    bulkPreviewPayload = { items, idempotency_key: reviewId() };
    const labels = { low: 'Laag', medium: 'Middel', high: 'Hoog' };
    ws('bulkReviewSummary').innerHTML = data.items.map(item => `<tr><td>${wsEsc(item.filename)}</td><td><code>${wsEsc(item.target_path)}</code></td><td><b class="privacy-${wsEsc(item.privacy)}">${wsEsc(labels[item.privacy])}</b></td></tr>`).join('');
    message.textContent = `${data.document_count} documenten klaar voor expliciete bevestiging.`; ws('bulkReviewConfirm').disabled = false;
  } catch (error) { bulkPreviewPayload = null; message.textContent = 'De selectie bevat een ongeldig of niet meer actueel voorstel.'; ws('bulkReviewConfirm').disabled = true }
}
async function confirmBulkReview() {
  if (!bulkPreviewPayload) return; const button = ws('bulkReviewConfirm'), message = ws('bulkReviewMessage'); button.disabled = true; message.textContent = 'Oordelen auditbaar opslaan…';
  try {
    const response = await fetch('/api/v1/workset/reviews/bulk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bulkPreviewPayload) });
    if (!response.ok) throw Error(response.status); const data = await response.json(); message.textContent = `${data.document_count} documenten, doelpaden en privacylabels bevestigd.`;
    setTimeout(() => { ws('bulkReviewDialog').close(); bulkPreviewPayload = null; loadWorkset(true) }, 650);
  } catch (error) { message.textContent = 'Bulkbeoordeling is niet opgeslagen. Er zijn geen bestanden gewijzigd.'; button.disabled = false }
}
document.addEventListener('workset:rendered', decorateBulkCards);
function decorateFilenameProposals() {
  document.querySelectorAll('.review-panel').forEach(panel => {
    const details = panel.querySelector('.new-proposal'); if (!details || details.querySelector('.proposed-filename')) return;
    const pathLabel = details.querySelector('.proposed-path')?.closest('label');
    const doc = state.documents.find(item => String(item.file_id) === String(panel.dataset.fileId));
    const label = document.createElement('label'); label.innerHTML = `Nieuwe bestandsnaam<input class="proposed-filename" maxlength="255" placeholder="${wsEsc(doc?.filename || 'Nieuwe naam')}"><small>De huidige extensie blijft behouden.</small>`;
    details.insertBefore(label, pathLabel || details.lastElementChild);
    const summary = details.querySelector('summary'); if (summary) summary.textContent = 'Nieuwe categorie, familie, bestandsnaam of doelpad voorstellen';
  });
}
document.addEventListener('workset:rendered', decorateFilenameProposals);
function decorateOriginalDocumentLinks() {
  document.querySelectorAll('.document-card').forEach(card => {
    const main = card.querySelector('.document-main'), source = main?.querySelector(':scope>code');
    if (!source || main.querySelector('.original-path-row')) return;
    const doc = state.documents.find(item => item.path === source.getAttribute('title')); if (!doc) return;
    const row = document.createElement('div'); row.className = 'original-path-row';
    const visiblePath = doc.smb_path || doc.path, openUrl = documentOpenUrl(doc, visiblePath);
    row.innerHTML = `<a href="${wsEsc(openUrl)}"${openUrl.startsWith('/api/') ? ' target="_blank" rel="noopener noreferrer"' : ''} title="Origineel document openen">${wsEsc(visiblePath)}</a><button type="button" class="copy-original-path" data-path="${wsEsc(visiblePath)}" aria-label="Pad kopiëren" title="Pad kopiëren">⧉</button>`;
    source.replaceWith(row); card.querySelector(':scope>.copy-path')?.remove();
  });
}
function documentOpenUrl(doc, smbPath) {
  const extension = String(doc.extension || '').toLowerCase();
  const officeProtocol = { doc: 'ms-word', docx: 'ms-word', xls: 'ms-excel', xlsx: 'ms-excel', ppt: 'ms-powerpoint', pptx: 'ms-powerpoint' }[extension];
  if (!officeProtocol || !String(smbPath).startsWith('\\\\')) return `/api/v1/workset/${encodeURIComponent(doc.file_id)}/content`;
  const fileUrl = 'file://' + String(smbPath).slice(2).split('\\').map(encodeURIComponent).join('/');
  return `${officeProtocol}:ofe|u|${fileUrl}`;
}
document.addEventListener('workset:rendered', decorateOriginalDocumentLinks);
document.addEventListener('click', async event => {
  const button = event.target.closest('.copy-original-path'); if (!button) return;
  try { await copyText(button.dataset.path); button.classList.add('copied'); button.title = 'Pad gekopieerd'; button.setAttribute('aria-label', 'Pad gekopieerd'); setTimeout(() => { button.classList.remove('copied'); button.title = 'Pad kopiëren'; button.setAttribute('aria-label', 'Pad kopiëren') }, 1400) } catch (error) { button.title = 'Kopiëren mislukt' }
});
ws('bulkSelectAll').addEventListener('change', event => { visibleBulkCheckboxes().forEach(box => box.checked = event.target.checked); updateBulkControls() });
ws('bulkReviewOpen').addEventListener('click', openBulkReview); ws('bulkReviewConfirm').addEventListener('click', confirmBulkReview);
ws('worksetDocuments').addEventListener('change', event => { if (event.target.closest('.bulk-select')) updateBulkControls() });
ws('worksetSort').addEventListener('change', () => loadWorkset(true));
const reviewId = () => globalThis.crypto?.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 3 | 8); return v.toString(16) });
const selected = (value, current) => value === current ? ' selected' : '';
function categoryOptions(current) { const known = state.taxonomy.categories.some(item => item.code === current), placeholder = known ? '' : '<option value="" selected disabled>Geen betrouwbaar voorstel — kies categorie</option>'; return placeholder + state.taxonomy.categories.map(item => `<option value="${wsEsc(item.code)}"${selected(item.code, current)}>${wsEsc(item.label)}</option>`).join('') }
function compactFamilyOptions(doc, current, category) {
    const options = [];

    const add = item => {
        if (
            item &&
            item.categories.includes(category) &&
            !options.some(value => value.code === item.code)
        ) {
            options.push(item);
        }
    };

    // 1. Huidige/voorgestelde familie altijd zichtbaar.
    add(
        state.taxonomy.families.find(
            item => item.code === current
        )
    );

    // 2. Eerder vaak menselijk gekozen families voor deze categorie.
    const learned = (doc.review_options.learned_families || [])
        .filter(item => item.category_code === category)
        .sort((a, b) => b.support - a.support);

    for (const learnedFamily of learned) {
        add(
            state.taxonomy.families.find(
                item => item.code === learnedFamily.family_code
            )
        );
    }

    // 3. Bestaande contextuele CORE-shortlist.
    for (const item of doc.review_options.compact_families || []) {
        add(item);
    }

    // 4. Aanvullen met overige geldige families tot maximaal 5.
    for (const item of state.taxonomy.families) {
        add(item);

        if (options.length >= 5) {
            break;
        }
    }

    return options
        .slice(0, 5)
        .map(
            item =>
                `<option value="${wsEsc(item.code)}"${selected(item.code, current)}>` +
                `${wsEsc(item.label)}</option>`
        )
        .join('');
}
function allFamilyOptions(category, query = '', current = '') { const needle = query.trim().toLocaleLowerCase('nl-NL'); const items = state.taxonomy.families.filter(item => (item.categories.includes(category) || item.code === current) && (!needle || item.label.toLocaleLowerCase('nl-NL').includes(needle))); return items.map(item => `<option value="${wsEsc(item.code)}"${selected(item.code, current)}>${wsEsc(item.label)}</option>`).join('') }
function privacyCard(doc) { const proposal = doc.privacy_proposal; if (!proposal) return ''; const labels = { low: 'Laag', medium: 'Middel', high: 'Hoog' }, current = doc.effective_privacy_classification || proposal.classification, reviewed = doc.latest_privacy_review_id ? `<span class="privacy-reviewed">Vastgesteld: ${wsEsc(labels[doc.current_privacy_classification])} · ${wsDt(doc.latest_privacy_review_at)}</span>` : ''; const controls = state.privacyReviewEnabled ? `<div class="privacy-controls"><select class="privacy-classification" aria-label="Privacyclassificatie"><option value="low"${selected('low', current)}>Laag</option><option value="medium"${selected('medium', current)}>Middel</option><option value="high"${selected('high', current)}>Hoog</option></select><button type="button" data-privacy-decision="accepted" class="privacy-save">Privacy bevestigen</button><button type="button" data-privacy-decision="needs_review" class="privacy-later">Later</button></div><span class="privacy-message" aria-live="polite"></span>` : ''; return `<div class="privacy-review privacy-${wsEsc(proposal.classification)}" data-file-id="${doc.file_id}"><div class="privacy-summary"><span class="privacy-shield">◆</span><div><span class="privacy-title">Privacy <b>${wsEsc(labels[proposal.classification])}</b><em>${wsEsc(proposal.confidence)} confidence</em></span><small>${wsEsc(privacyReasonLabels[proposal.reason_code] || proposal.reason_code)}</small>${reviewed}</div></div>${controls}</div>` }
function documentCard(doc) {
  const proposal = doc.target_proposal, classification = doc.classification_status === 'accepted' ? `${wsEsc(doc.category)} · ${wsEsc(doc.document_family || 'familie onbekend')}` : 'Nog niet inhoudelijk beoordeeld', path = doc.smb_path || doc.path; const target = proposal ? `<div class="target-proposal"><span><i class="source-badge">CORE-voorstel</i>${wsEsc(proposal.proposal_confidence)}</span><code>${wsEsc(proposal.suggested_target_path)}</code></div>` : ''; const latest = doc.latest_review_decision ? `<div class="latest-review"><i class="source-badge">Menselijk oordeel</i><b>${wsEsc(decisionLabels[doc.latest_review_decision] || doc.latest_review_decision)}</b> · ${wsDt(doc.latest_review_at)} <button class="history-button" data-history-file="${doc.file_id}">Historie</button><div class="review-history" hidden></div></div>` : ''; let review = ''; if (state.reviewEnabled && proposal) {
    const similar = doc.similar_document_proposal || {};
    const useSimilar = similar.status === 'consensus_proposal';

    const category = useSimilar
      ? similar.proposed_category_code
      : proposal.category_code;

    const family = useSimilar
      ? similar.proposed_document_family_code
      : proposal.document_family_code; const learnedHint = useSimilar
        ? `<div class="similar-classification-hint">
         Voorstel uit vergelijkbare documenten ·
         ${wsEsc(similar.support_count || 0)} van
         ${wsEsc(similar.review_count || 0)} menselijke beoordelingen
       </div>`
        : ''; review = `${learnedHint}<div class="review-panel" data-file-id="${doc.file_id}" data-previous-decision="${wsEsc(doc.latest_review_decision || '')}"><label>Categorie<select class="review-category">${categoryOptions(category)}</select></label><label>Familie<select class="review-family">${compactFamilyOptions(doc, family, category)}</select></label><button type="button" class="more-families">Meer…</button><div class="family-browser" hidden><label>Zoek familie<input class="family-search" type="search" placeholder="Zoeken"></label><label>Alle passende families<select class="all-families" size="6">${allFamilyOptions(category, '', family)}</select></label></div><label>Notitie<input class="review-note" maxlength="2000" placeholder="Toelichting voor CORE"></label><details class="new-proposal"><summary>Nieuwe categorie, familie of doelpad voorstellen</summary><label>Nieuwe categorie<input class="proposed-category" maxlength="120" placeholder="Bijv. Wonen"></label><label>Nieuwe familie<input class="proposed-family" maxlength="120" placeholder="Bijv. VvE-document"></label><label>Nieuw doelpad<input class="proposed-path" maxlength="500" placeholder="Bijv. Wonen/VvE/Eksterlaan"></label><small>Wordt apart beoordeeld en wijzigt de CORE-regels niet automatisch.</small></details><div class="review-actions"><button data-decision="accepted" class="accept">Classificatie akkoord</button><button data-decision="needs_review">Later</button><button data-decision="rejected" class="reject">Niet akkoord</button><button data-decision="passed">Overslaan</button></div><span class="review-message" aria-live="polite"></span></div>`
  } return `<article class="document-card"><div class="document-icon ${wsEsc(doc.extension)}">${wsEsc(doc.extension).toUpperCase()}</div><div class="document-main"><div class="document-top"><strong title="${wsEsc(doc.filename)}">${wsEsc(doc.filename)}</strong><span class="status-pill ${wsEsc(doc.workset_status)}">${wsEsc(doc.workset_status.replace('_', ' '))}</span></div><p>${wsEsc(reasonLabels[doc.reason_code] || doc.reason_code)} · ${wsDt(doc.last_qualifying_activity_at)}</p><div class="document-meta">
  <span>${wsBytes(doc.size_bytes)}</span>
  <span>File ID: ${wsEsc(doc.file_id)}</span>
  <span>${classification}</span>
  <span>Confidence: ${wsEsc(doc.activity_confidence)}</span>
</div><code title="${wsEsc(doc.path)}">${wsEsc(doc.path)}</code>${target}${latest}${privacyCard(doc)}${review}</div><button class="copy-path" type="button" data-path="${wsEsc(path)}">Kopieer SMB-pad</button></article>`
}
function lifecycleCard(doc) { if (!state.lifecycleReviewEnabled) return ''; const labels = { active: 'Actief', archive: 'Inactief / archief', needs_review: 'Later beoordelen' }, current = doc.effective_lifecycle || doc.calculated_lifecycle, reviewed = doc.latest_lifecycle_review_id ? `<small>Menselijk vastgesteld: ${wsEsc(labels[current] || current)}${doc.lifecycle_active_until ? ` tot ${wsDt(doc.lifecycle_active_until)}` : ''}</small>` : '<small>Alleen een auditbaar oordeel; er wordt niets verplaatst.</small>'; return `<div class="lifecycle-review" data-file-id="${doc.file_id}"><div class="lifecycle-summary"><b>Lifecycle</b><span>CORE: ${wsEsc(labels[doc.calculated_lifecycle] || doc.calculated_lifecycle)}</span>${reviewed}</div><div class="lifecycle-controls"><button type="button" data-lifecycle="active" class="${current === 'active' ? 'selected' : ''}">Actief maken</button><label>voor <input class="active-months" type="number" min="1" max="120" placeholder="∞"> maanden</label><button type="button" data-lifecycle="archive" class="${current === 'archive' ? 'selected' : ''}">Inactief / archief</button><button type="button" data-lifecycle="needs_review" class="${current === 'needs_review' ? 'selected' : ''}">Later</button></div><span class="lifecycle-message" aria-live="polite"></span></div>` }
function decorateLifecycleCards() { if (!state.lifecycleReviewEnabled) return; document.querySelectorAll('.document-card').forEach((card, index) => { const doc = state.documents[index]; if (!doc || card.querySelector('.lifecycle-review')) return; const holder = document.createElement('div'); holder.innerHTML = lifecycleCard(doc); const lifecycle = holder.firstElementChild, privacy = card.querySelector('.privacy-review'); lifecycle.querySelectorAll('[data-lifecycle]').forEach(button => button.addEventListener('click', event => { event.stopPropagation(); submitLifecycle(lifecycle, button.dataset.lifecycle) })); if (privacy) privacy.before(lifecycle); else card.querySelector('.document-main').append(lifecycle) }) }
function nominationActions(doc) {
  const archive = doc.nominations?.archive, deletion = doc.nominations?.deletion;
  return `<div class="nomination-actions" data-file-id="${doc.file_id}"><button type="button" class="nomination-button${archive ? ' active' : ''}" aria-pressed="${archive ? 'true' : 'false'}" data-nomination-type="archive" data-nomination-action="${archive ? 'withdrawn' : 'nominated'}" title="${archive ? 'Archiefnominatie intrekken' : 'Nomineren voor archiefreview'}"><span aria-hidden="true">&#128230;</span>${archive ? 'Archief genomineerd' : 'Archiveren'}</button><button type="button" class="nomination-button deletion${deletion ? ' active' : ''}" aria-pressed="${deletion ? 'true' : 'false'}" data-nomination-type="deletion" data-nomination-action="${deletion ? 'withdrawn' : 'nominated'}" title="${deletion ? 'Verwijdernominatie intrekken' : 'Nomineren voor toekomstige verwijderreview'}"><span aria-hidden="true">&#128465;</span>${deletion ? 'Verwijderreview ' + wsDt(deletion.review_at) : 'Nomineren voor verwijderen'}</button><span class="nomination-message" aria-live="polite"></span></div>`;
}
function decorateNominationCards() {
  if (!state.nominationEnabled) return;
  document.querySelectorAll('.document-card').forEach((card, index) => {
    const doc = state.documents[index]; if (!doc || card.querySelector('.nomination-actions')) return;
    const holder = document.createElement('div'); holder.innerHTML = nominationActions(doc);
    const actions = holder.firstElementChild, privacy = card.querySelector('.privacy-review');
    if (privacy) privacy.before(actions); else card.querySelector('.document-main').append(actions);
  });
}
document.addEventListener('workset:rendered', decorateNominationCards);
document.addEventListener('workset:rendered', () => { state.lifecycleReviewEnabled = state.reviewEnabled; decorateLifecycleCards() });
function params() { return new URLSearchParams({ status: ws('worksetStatus').value, review_state: ws('worksetReview').value, review_decision: ws('worksetDecision').value, nomination: ws('worksetNomination').value, extension: ws('worksetExtension').value, family: ws('worksetFamily').value, sort: ws('worksetSort').value, search: ws('worksetSearch').value.trim(), limit: state.limit, offset: state.offset }) }
function renderReviewStats() { const s = state.reviewSummary; ws('worksetReviewStats').innerHTML = [['Lifecycle beoordelen', state.worksetSummary.needs_review], ['Open', s.pending], ['Beoordeeld', s.reviewed], ['Akkoord', s.accepted], ['Uitgesteld', s.needs_review], ['Niet akkoord', s.rejected], ['Niet beoordelen', s.passed]].map(([label, value]) => `<span class="review-stat">${label}<b>${wsNf.format(value || 0)}</b></span>`).join('') }
function renderNominationStats() { const s = state.nominationSummary; ws('worksetNominationStats').innerHTML = `<span class="review-stat nomination-archive">Voor archief<b>${wsNf.format(s.archive || 0)}</b></span><span class="review-stat nomination-deletion">Voor verwijderreview<b>${wsNf.format(s.deletion || 0)}</b></span><small>Nominaties veranderen de actieve werkset en bestanden niet.</small>` }
function renderWorksetOverview() {
  const review = ws('worksetReview').value, label = review === 'pending' ? 'Te beoordelen' : review === 'reviewed' ? 'Beoordeeld' : 'In huidige selectie', s = state.worksetSummary;
  ws('worksetStats').innerHTML = [['Actief', s.active, 'active', ''], [label, state.filteredTotal, 'review', 'huidige filters'], ['Inactief', s.inactive, 'inactive', ''], ['Totaal', s.total, 'total', '']].map(([name, value, kind, note]) => `<article class="panel ${kind}"><span>${name}</span><b>${wsNf.format(value || 0)}</b>${note ? `<small>${note}</small>` : ''}</article>`).join('');
}
document.addEventListener('workset:rendered', () => {
  const cards = [...ws('worksetStats').querySelectorAll('article b')].map(item => Number(item.textContent.replace(/\D/g, '')) || 0);
  if (cards.length === 4) state.worksetSummary = { active: cards[0], needs_review: cards[1], inactive: cards[2], total: cards[3] };
  renderReviewStats(); renderWorksetOverview();
});
function updateFamilyFilter(items) { const select = ws('worksetFamily'), current = select.value; state.families = items; select.innerHTML = '<option value="all">Alle families</option>' + items.map(item => `<option value="${wsEsc(item.code)}">${wsEsc(item.label)} (${item.count})</option>`).join(''); select.value = items.some(item => item.code === current) ? current : 'all' }
async function loadWorkset(reset = true) { if (state.loading) return; state.loading = true; if (reset) { state.offset = 0; state.documents = []; ws('worksetDocuments').innerHTML = '<div class="empty-state">Werkset laden…</div>' } try { const response = await fetch(`/api/v1/workset?${params()}`, { cache: 'no-store' }); if (!response.ok) throw Error(response.status); const data = await response.json(); state.reviewEnabled = data.review_writes_enabled; state.privacyReviewEnabled = data.privacy_review_enabled; state.nominationEnabled = data.nomination_writes_enabled; state.filteredTotal = data.filtered_total; state.reviewSummary = data.review_summary; state.nominationSummary = data.nomination_summary; state.taxonomy = data.review_taxonomy; renderReviewStats(); renderNominationStats(); updateFamilyFilter(data.families); state.documents.push(...data.documents); state.offset = state.documents.length; ws('worksetUpdated').textContent = wsDt(data.generated_at); ws('worksetMode').textContent = state.reviewEnabled ? 'REVIEW ACTIEF' : 'READ ONLY'; ws('worksetCount').textContent = `${wsNf.format(state.filteredTotal)} documenten`; ws('worksetStats').innerHTML = [['Actief', data.summary.active, 'active'], ['Beoordelen', data.summary.needs_review, 'review'], ['Inactief', data.summary.inactive, 'inactive'], ['Totaal', data.summary.total, 'total']].map(([label, value, kind]) => `<article class="panel ${kind}"><span>${label}</span><b>${wsNf.format(value)}</b></article>`).join(''); ws('worksetDocuments').innerHTML = state.documents.length ? state.documents.map(documentCard).join('') : '<div class="empty-state">Geen documenten gevonden met deze filters.</div>'; ws('worksetMore').hidden = state.documents.length >= state.filteredTotal; document.dispatchEvent(new CustomEvent('workset:rendered')) } catch (error) { ws('worksetDocuments').innerHTML = '<div class="empty-state error">De werkset kan nu niet worden geladen.</div>' } finally { state.loading = false } }
async function toggleHistory(button) { const container = button.parentElement.querySelector('.review-history'); if (!container.hidden) { container.hidden = true; return } container.hidden = false; container.innerHTML = 'Historie laden…'; try { const response = await fetch(`/api/v1/workset/${button.dataset.historyFile}/reviews`, { cache: 'no-store' }); if (!response.ok) throw Error(response.status); const data = await response.json(); container.innerHTML = data.events.length ? data.events.map(event => `<div class="history-event"><b>${wsEsc(decisionLabels[event.decision] || event.decision)}</b> · ${wsDt(event.created_at)} · ${wsEsc(event.reviewer)}<br>Categorie: ${wsEsc(event.corrected_category_code || event.proposal_category_code || 'onbekend')} · Familie: ${wsEsc(event.corrected_document_family_code || event.proposal_document_family_code || 'onbekend')}${event.review_type === 'privacy_classification' ? ` · Privacy: ${wsEsc(event.corrected_privacy_classification || event.proposal_privacy_classification)}` : ''}${event.review_notes ? `<code>${wsEsc(event.review_notes)}</code>` : ''}</div>`).join('') : 'Geen eerdere beoordelingen' } catch (error) { container.innerHTML = 'Historie laden mislukt' } }
async function submitReview(panel, decision) {
  const message = panel.querySelector('.review-message'), buttons = [...panel.querySelectorAll('button')]; buttons.forEach(button => button.disabled = true); message.textContent = 'Opslaan…'; try {
    const response = await fetch('/api/v1/workset/reviews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id: Number(panel.dataset.fileId), idempotency_key: reviewId(), decision, corrected_category_code: panel.querySelector('.review-category').value, corrected_document_family_code: panel.querySelector('.review-family').value, review_notes: panel.querySelector('.review-note').value.trim(), proposed_category_label: panel.querySelector('.proposed-category').value.trim(), proposed_family_label: panel.querySelector('.proposed-family').value.trim(), proposed_target_path: panel.querySelector('.proposed-path').value.trim() }) });
    const data = await response.json();

    if (!response.ok) {
      throw Error(data.detail || response.status);
    }

    const card = panel.closest('.document-card');
    const proposal = data.effective_target_proposal;
    const previous = panel.dataset.previousDecision;

    let latest = card.querySelector('.latest-review');; if (!latest) { latest = document.createElement('div'); latest.className = 'latest-review'; panel.before(latest) } latest.innerHTML = `<i class="source-badge">Menselijk oordeel</i><b>${wsEsc(decisionLabels[data.decision] || data.decision)}</b> · ${wsDt(data.created_at)} <button class="history-button" data-history-file="${panel.dataset.fileId}">Historie</button><div class="review-history" hidden></div>`; if (proposal) { const target = card.querySelector('.target-proposal'); target.querySelector('span').innerHTML = `<i class="source-badge">CORE-voorstel</i>${wsEsc(proposal.proposal_confidence)}`; target.querySelector('code').textContent = proposal.suggested_target_path } if (previous) { state.reviewSummary[previous] = Math.max(0, (state.reviewSummary[previous] || 0) - 1) } else { state.reviewSummary.pending = Math.max(0, (state.reviewSummary.pending || 0) - 1); state.reviewSummary.reviewed = (state.reviewSummary.reviewed || 0) + 1 } state.reviewSummary[data.decision] = (state.reviewSummary[data.decision] || 0) + 1; panel.dataset.previousDecision = data.decision; renderReviewStats(); message.textContent = (data.proposed_category_label || data.proposed_family_label || data.proposed_target_path) ? 'Oordeel en nieuw voorstel opgeslagen' : 'Oordeel opgeslagen'; if (ws('worksetReview').value === 'pending') { card.classList.add('review-complete'); setTimeout(() => { card.remove(); state.documents = state.documents.filter(doc => String(doc.file_id) !== String(panel.dataset.fileId)); state.offset = state.documents.length; state.filteredTotal = Math.max(0, state.filteredTotal - 1); ws('worksetCount').textContent = `${wsNf.format(state.filteredTotal)} documenten`; if (!state.documents.length) ws('worksetDocuments').innerHTML = '<div class="empty-state">Alles in deze selectie is beoordeeld.</div>' }, 240) }
  } catch (error) {
    message.textContent = `Opslaan mislukt: ${error.message}`;
    console.error('submitReview failed:', error);
  } finally { buttons.forEach(button => button.disabled = false) }
}
async function submitPrivacy(panel, decision) { const message = panel.querySelector('.privacy-message'), buttons = [...panel.querySelectorAll('button')]; buttons.forEach(button => button.disabled = true); message.textContent = 'Privacy opslaan…'; try { const response = await fetch('/api/v1/workset/reviews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id: Number(panel.dataset.fileId), idempotency_key: reviewId(), review_type: 'privacy_classification', decision, privacy_classification: panel.querySelector('.privacy-classification').value }) }); if (!response.ok) throw Error(response.status); const data = await response.json(); message.textContent = `Privacy ${data.privacy_classification} is auditbaar opgeslagen`; panel.querySelector('div').insertAdjacentHTML('beforeend', `<small>Menselijk vastgesteld: ${wsEsc(data.privacy_classification)} · ${wsDt(data.created_at)}</small>`) } catch (error) { message.textContent = `Opslaan mislukt: ${error.message}` } finally { buttons.forEach(button => button.disabled = false) } }
async function submitLifecycle(panel, lifecycle) { const message = panel.querySelector('.lifecycle-message'), buttons = [...panel.querySelectorAll('button')], months = panel.querySelector('.active-months').value; buttons.forEach(button => button.disabled = true); message.textContent = 'Lifecycle opslaan…'; try { const payload = { file_id: Number(panel.dataset.fileId), idempotency_key: reviewId(), review_type: 'lifecycle', decision: lifecycle === 'needs_review' ? 'needs_review' : 'accepted', corrected_lifecycle: lifecycle }; if (lifecycle === 'active' && months) payload.active_months = Number(months); const response = await fetch('/api/v1/workset/reviews', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); const data = await response.json(); if (!response.ok) throw Error(data.detail || response.status); panel.querySelectorAll('[data-lifecycle]').forEach(button => button.classList.toggle('selected', button.dataset.lifecycle === lifecycle)); message.textContent = lifecycle === 'active' ? (data.lifecycle_active_until ? `Actief vastgelegd tot ${wsDt(data.lifecycle_active_until)}` : 'Actief zonder einddatum vastgelegd') : lifecycle === 'archive' ? 'Inactief / archief vastgelegd' : 'Later beoordelen vastgelegd' } catch (error) { message.textContent = `Lifecycle opslaan mislukt: ${error.message}` } finally { buttons.forEach(button => button.disabled = false) } }
async function submitNomination(button) {
  const panel = button.closest('.nomination-actions'), type = button.dataset.nominationType, action = button.dataset.nominationAction, label = type === 'archive' ? 'archief' : 'verwijderreview';
  const card = panel.closest('.document-card'), note = card.querySelector('.review-note')?.value.trim();
  const reason = action === 'withdrawn' ? `Handmatig ingetrokken: ${label}` : (note || `Handmatig genomineerd voor ${label} via CORE-portaal`);
  const message = panel.querySelector('.nomination-message'); panel.querySelectorAll('button').forEach(item => item.disabled = true); message.textContent = 'Nominatie opslaan…';
  try {
    const response = await fetch('/api/v1/workset/nominations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_id: Number(panel.dataset.fileId), idempotency_key: reviewId(), nomination_type: type, action, reason }) }); if (!response.ok) throw Error(response.status); const data = await response.json();
    const doc = state.documents.find(item => String(item.file_id) === String(panel.dataset.fileId));
    if (action === 'nominated') { doc.nominations[type] = { id: data.nomination_id, review_at: data.review_at, reason }; state.nominationSummary[type] = (state.nominationSummary[type] || 0) + 1 } else { doc.nominations[type] = null; state.nominationSummary[type] = Math.max(0, (state.nominationSummary[type] || 0) - 1) }
    const holder = document.createElement('div'); holder.innerHTML = nominationActions(doc); const updated = holder.firstElementChild; panel.replaceWith(updated); updated.querySelector('.nomination-message').textContent = action === 'nominated' ? `${label} is gemarkeerd.` : 'Markering ingetrokken.'; renderNominationStats();
  } catch (error) { message.textContent = 'Nominatie kon niet worden opgeslagen.'; panel.querySelectorAll('button').forEach(item => item.disabled = false) }
}
async function copyText(value) { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(value); return } const area = document.createElement('textarea'); area.value = value; area.setAttribute('readonly', ''); area.style.position = 'fixed'; area.style.opacity = '0'; document.body.appendChild(area); area.select(); const copied = document.execCommand('copy'); area.remove(); if (!copied) throw Error('copy failed') }
function updatePanelCategory(panel) { const doc = state.documents.find(item => String(item.file_id) === panel.dataset.fileId), category = panel.querySelector('.review-category').value, family = panel.querySelector('.review-family'), current = family.value; family.innerHTML = compactFamilyOptions(doc, current, category); if (!family.value) family.selectedIndex = 0; panel.querySelector('.all-families').innerHTML = allFamilyOptions(category, '', family.value) }
let timer; ws('worksetSearch').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => loadWorkset(true), 300) });['worksetStatus', 'worksetReview', 'worksetNomination', 'worksetExtension', 'worksetFamily'].forEach(id => ws(id).addEventListener('change', () => loadWorkset(true))); ws('worksetDecision').addEventListener('change', () => { if (ws('worksetDecision').value !== 'all') ws('worksetReview').value = 'reviewed'; loadWorkset(true) }); ws('worksetMore').addEventListener('click', () => loadWorkset(false)); ws('worksetDocuments').addEventListener('change', event => { const panel = event.target.closest('.review-panel'); if (!panel) return; if (event.target.matches('.review-category')) updatePanelCategory(panel); if (event.target.matches('.all-families')) { panel.querySelector('.review-family').innerHTML = `<option value="${wsEsc(event.target.value)}" selected>${wsEsc(event.target.options[event.target.selectedIndex].text)}</option>`; panel.querySelector('.family-browser').hidden = true } }); ws('worksetDocuments').addEventListener('input', event => { if (!event.target.matches('.family-search')) return; const panel = event.target.closest('.review-panel'); panel.querySelector('.all-families').innerHTML = allFamilyOptions(panel.querySelector('.review-category').value, event.target.value, panel.querySelector('.review-family').value) }); ws('worksetDocuments').addEventListener('click', async event => { const nominationButton = event.target.closest('[data-nomination-type]'); if (nominationButton) { await submitNomination(nominationButton); return } const panel = event.target.closest('.review-panel'); if (event.target.closest('.more-families')) { const browser = panel.querySelector('.family-browser'); browser.hidden = !browser.hidden; if (!browser.hidden) panel.querySelector('.family-search').focus(); return } const privacyButton = event.target.closest('[data-privacy-decision]'); if (privacyButton) { await submitPrivacy(privacyButton.closest('.privacy-review'), privacyButton.dataset.privacyDecision); return } const historyButton = event.target.closest('[data-history-file]'); if (historyButton) { await toggleHistory(historyButton); return } const reviewButton = event.target.closest('[data-decision]'); if (reviewButton) { await submitReview(reviewButton.closest('.review-panel'), reviewButton.dataset.decision); return } const button = event.target.closest('.copy-path'); if (!button) return; try { await copyText(button.dataset.path); button.textContent = 'Gekopieerd'; setTimeout(() => button.textContent = 'Kopieer SMB-pad', 1400) } catch (error) { button.textContent = 'Kopiëren mislukt' } }); loadWorkset(true);
