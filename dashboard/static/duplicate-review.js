(() => {
  const section = document.getElementById('duplicateReviewSection');
  const list = document.getElementById('duplicateReviewGroups');
  const summary = document.getElementById('duplicateReviewSummary');
  const count = document.getElementById('duplicatePendingCount');
  const state = document.getElementById('duplicateReviewState');
  if (!section || !list || !summary || !count || !state) return;

  const esc = value => String(value ?? '').replace(/[&<>"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const bytes = value => new Intl.NumberFormat('nl-NL', {style:'unit', unit:'megabyte', maximumFractionDigits:1}).format(Number(value || 0) / 1048576);
  const reviewId = () => {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const randomByte = () => {
      if (globalThis.crypto?.getRandomValues) {
        const value = new Uint8Array(1);
        globalThis.crypto.getRandomValues(value);
        return value[0];
      }
      return Math.floor(Math.random() * 256);
    };
    const bytes = Array.from({length: 16}, randomByte);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = bytes.map(value => value.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`;
  };

  function memberRow(member, group) {
    const checked = Number(group.selected_file_id || group.golden_file_id) === Number(member.file_id);
    return `<label class="duplicate-member ${member.is_current_golden ? 'golden' : ''} ${member.deleted_at ? 'unavailable' : ''}">
      <input type="radio" name="leader-${esc(group.content_group_id)}" value="${Number(member.file_id)}" ${checked ? 'checked' : ''} ${member.deleted_at ? 'disabled' : ''}>
      <span><strong>${esc(member.filename)}</strong><small>${esc(member.path)}</small>
      <em>File ${Number(member.file_id)} · ${esc(member.workset_status || 'buiten werkset')}${member.is_current_golden ? ' · huidig golden record' : ''}</em></span>
    </label>`;
  }

  function groupCard(group) {
    const reviewed = group.latest_review_id && group.latest_review_action === 'selected_leader';
    const blocked = (group.handoff || []).find(item => !item.eligible_for_executor);
    return `<article class="duplicate-group" data-group-id="${esc(group.content_group_id)}">
      <header><div><strong>${Number(group.available_copies)} identieke kopieën</strong>
      <small>SHA-256 ${esc(group.content_sha256).slice(0, 16)}… · ${bytes(group.potential_savings_bytes)} potentiële besparing</small></div>
      <span class="duplicate-state ${reviewed ? 'reviewed' : ''}">${reviewed ? 'beoordeeld' : 'te beoordelen'}</span></header>
      <div class="duplicate-members">${group.members.map(member => memberRow(member, group)).join('')}</div>
      <label class="duplicate-notes">Toelichting<input maxlength="2000" value="${esc(group.review_notes || '')}" placeholder="Optioneel"></label>
      ${blocked ? `<p class="duplicate-handoff blocked">Overdracht geblokkeerd: ${esc(blocked.handoff_reason)}</p>` : reviewed ? '<p class="duplicate-handoff ready">Veilige overdracht staat klaar voor migratie en retentie.</p>' : ''}
      <div class="duplicate-actions"><button type="button" class="duplicate-save">Leidende kopie bevestigen</button>
      ${reviewed ? '<button type="button" class="duplicate-withdraw">Oordeel intrekken</button>' : ''}<span class="duplicate-message"></span></div>
    </article>`;
  }

  async function load() {
    list.innerHTML = '<div class="empty-state">Duplicaten laden…</div>';
    try {
      const response = await fetch(`/api/v1/workset/duplicates?review_state=${encodeURIComponent(state.value)}&limit=100&offset=0`, {cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || response.status);
      count.textContent = `${Number(data.summary.pending)} te beoordelen`;
      summary.innerHTML = `<span>${Number(data.summary.total)} groepen</span><span>${Number(data.summary.reviewed)} beoordeeld</span><span>${bytes(data.summary.potential_savings_bytes)} potentieel</span>`;
      list.innerHTML = data.groups.length ? data.groups.map(groupCard).join('') : '<div class="empty-state">Geen duplicategroepen in deze selectie.</div>';
      section.dataset.writesEnabled = data.review_writes_enabled ? 'true' : 'false';
    } catch (error) {
      list.innerHTML = `<div class="empty-state error">Duplicaten laden mislukt: ${esc(error.message)}</div>`;
    }
  }

  async function submit(card, action) {
    const message = card.querySelector('.duplicate-message');
    const selected = card.querySelector('input[type="radio"]:checked');
    if (!selected) { message.textContent = 'Kies eerst één leidende kopie.'; return; }
    if (section.dataset.writesEnabled !== 'true') { message.textContent = 'Interactieve beoordeling staat uit.'; return; }
    card.querySelectorAll('button,input').forEach(control => control.disabled = true);
    message.textContent = 'Oordeel opslaan…';
    try {
      const response = await fetch('/api/v1/workset/duplicate-reviews', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
          content_group_id:card.dataset.groupId, selected_file_id:Number(selected.value),
          action, idempotency_key:reviewId(), review_notes:card.querySelector('.duplicate-notes input').value.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.detail || response.status);
      message.textContent = data.selected_is_current_golden ? 'Oordeel opgeslagen; veilige overdracht wordt opnieuw gecontroleerd.' : 'Oordeel opgeslagen; eerst is een golden-recordwissel vereist.';
      setTimeout(load, 450);
    } catch (error) {
      message.textContent = `Opslaan mislukt: ${error.message}`;
      card.querySelectorAll('button,input').forEach(control => control.disabled = false);
    }
  }

  list.addEventListener('click', event => {
    const card = event.target.closest('.duplicate-group');
    if (!card) return;
    if (event.target.closest('.duplicate-save')) submit(card, 'selected_leader');
    if (event.target.closest('.duplicate-withdraw')) submit(card, 'withdrawn');
  });
  state.addEventListener('change', load);
  section.addEventListener('toggle', () => { if (section.open) load(); });
  load();
})();
