(() => {
  const section = document.getElementById('taxonomyProposalSection');
  const list = document.getElementById('taxonomyProposalList');
  const count = document.getElementById('taxonomyProposalCount');
  const state = document.getElementById('taxonomyProposalState');
  if (!section || !list || !count || !state) return;

  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
  const uuid = () => globalThis.crypto?.randomUUID?.()
    || 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
      const random = Math.random() * 16 | 0;
      return (char === 'x' ? random : (random & 3 | 8)).toString(16);
    });

  function render(items, writesEnabled) {
    count.textContent = `${items.length} voorstel${items.length === 1 ? '' : 'len'}`;
    if (!items.length) {
      list.innerHTML = '<p class="taxonomy-empty">Geen taxonomievoorstellen in deze weergave.</p>';
      return;
    }
    list.innerHTML = items.map(item => {
      const kind = item.proposal_type === 'category' ? 'Categorie' : 'Familie';
      const parent = item.proposal_type === 'family' && item.category_label
        ? `<span>Onder categorie <strong>${esc(item.category_label)}</strong></span>` : '';
      const status = item.decision === 'pending' ? 'Te beoordelen'
        : item.decision === 'accepted' ? 'Geaccepteerd' : 'Afgewezen';
      const actions = item.decision === 'pending' && writesEnabled ? `
        <label>Toelichting <input class="taxonomy-note" maxlength="2000" placeholder="Optioneel"></label>
        <div class="taxonomy-actions">
          <button type="button" class="accept" data-taxonomy-decision="accepted">Goedkeuren</button>
          <button type="button" class="reject" data-taxonomy-decision="rejected">Afwijzen</button>
        </div>` : '';
      return `<article class="taxonomy-proposal" data-proposal-key="${esc(item.proposal_key)}">
        <header><span class="taxonomy-kind">${kind}</span><strong>${esc(item.proposed_label)}</strong><i>${status}</i></header>
        <div class="taxonomy-evidence">${parent}<span>${item.support} menselijke beoordeling${item.support === 1 ? '' : 'en'}</span><span>Code: <code>${esc(item.taxonomy_code)}</code></span></div>
        ${actions}<p class="taxonomy-message" aria-live="polite"></p>
      </article>`;
    }).join('');
  }

  async function load() {
    list.innerHTML = '<p class="taxonomy-empty">Taxonomievoorstellen laden…</p>';
    try {
      const response = await fetch(`/api/v1/workset/taxonomy-proposals?decision=${encodeURIComponent(state.value)}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data.proposals, data.writes_enabled);
    } catch (error) {
      count.textContent = 'niet beschikbaar';
      list.innerHTML = '<p class="taxonomy-empty error">Taxonomievoorstellen laden mislukt.</p>';
    }
  }

  async function decide(card, decision) {
    const message = card.querySelector('.taxonomy-message');
    const buttons = card.querySelectorAll('button');
    buttons.forEach(button => { button.disabled = true; });
    message.textContent = 'Oordeel opslaan…';
    try {
      const response = await fetch('/api/v1/workset/taxonomy-proposals/reviews', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          proposal_key: card.dataset.proposalKey, decision,
          review_notes: card.querySelector('.taxonomy-note')?.value.trim() || '',
          idempotency_key: uuid()
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      message.textContent = decision === 'accepted'
        ? 'Goedgekeurd en beschikbaar in de keuzelijsten.' : 'Voorstel afgewezen.';
      setTimeout(async () => {
        await load();
        if (typeof globalThis.loadWorkset === 'function') globalThis.loadWorkset(true);
      }, 450);
    } catch (error) {
      message.textContent = `Opslaan mislukt: ${error.message}`;
      buttons.forEach(button => { button.disabled = false; });
    }
  }

  section.addEventListener('toggle', () => { if (section.open) load(); });
  state.addEventListener('change', load);
  list.addEventListener('click', event => {
    const button = event.target.closest('[data-taxonomy-decision]');
    if (button) decide(button.closest('.taxonomy-proposal'), button.dataset.taxonomyDecision);
  });
  load();
})();
