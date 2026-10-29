(() => {
  const $ = (selector) => document.querySelector(selector);
  const uuid = () => crypto.randomUUID();
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const state = { context: null, recipes: [], recipeNext: null, historyNext: null, query: '', draft: null, pending: null, preview: null, generation: 0, busy: false, opening: false };
  const draftKey = 'shiftly.production.draft.v2';
  const emptyDraft = () => ({ logId: uuid(), requestId: uuid(), businessDate: today(), entries: [] });
  const element = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node; };
  const actorKey = (payload) => `${payload.actor.userId}:${payload.actor.storeId}:${payload.actor.role}:${(payload.actor.capabilities || []).join(',')}`;

  function notice(message, error = false) {
    const node = $('#production-notice'); node.textContent = message; node.classList.toggle('hidden', !message); node.classList.toggle('error', error);
  }
  function clearPrivate() {
    state.generation += 1; state.context = null; state.draft = null; state.pending = null; state.recipes = []; state.preview = null; state.busy = false;
    $('#production-confirm-check').checked = false; $('#confirm-production').disabled = true;
    ['#production-recipes', '#production-entry-review', '#production-deductions', '#production-issues', '#recipe-book', '#production-history'].forEach((selector) => $(selector).replaceChildren());
    document.querySelector('main').style.visibility = 'hidden';
  }
  function scopedDraft(payload) {
    const scope = actorKey(payload); let stored = null;
    try { stored = JSON.parse(sessionStorage.getItem(draftKey)); } catch { sessionStorage.removeItem(draftKey); }
    if (!stored || stored.scope !== scope || !stored.draft || typeof stored.draft.logId !== 'string') return { scope, draft: emptyDraft() };
    return stored;
  }
  function saveDraft() { if (state.context && state.draft) sessionStorage.setItem(draftKey, JSON.stringify({ scope: actorKey(state.context), draft: state.draft, pending: state.pending })); }
  function resetDraft() { if (state.pending) return notice('Resolve the pending submission before clearing this draft.', true); state.draft = emptyDraft(); state.preview = null; saveDraft(); renderRun(); show('run'); }

  async function request(path, options = {}) {
    const response = await fetch(`/api/production${path}`, { cache: 'no-store', ...options,
      headers: options.body ? { 'Content-Type': 'application/json' } : undefined });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(payload.error || 'Production is temporarily unavailable.'); error.status = response.status; throw error; }
    return payload;
  }
  async function status() {
    const response = await fetch('/api/accounts/status', { cache: 'no-store' }); const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.authenticated || !payload.actor?.capabilities?.includes('production.view')) throw new Error('Production access is unavailable.');
    return payload;
  }
  async function refreshContext() {
    let payload; try { payload = await status(); } catch (error) { clearPrivate(); throw error; }
    if (state.context && actorKey(payload) !== actorKey(state.context)) { sessionStorage.removeItem(draftKey); clearPrivate(); throw new Error('Your account or store changed. Reload Production before continuing.'); }
    state.context = payload;
    if (!state.draft) { const saved = scopedDraft(payload); state.draft = saved.draft; state.pending = saved.pending || null; if (state.pending && !state.pending.payload) { state.pending.payload = { ...state.draft, entries: state.draft.entries.map(item => ({ ...item })), confirmed: true, expectedStoreId: payload.actor.storeId }; saveDraft(); } }
    $('#production-store').textContent = payload.stores?.find((store) => store.storeId === payload.actor.storeId)?.storeName || 'Your store';
    document.querySelector('main').style.visibility = 'visible'; return payload;
  }
  function show(name) {
    document.querySelectorAll('.production-view').forEach((node) => node.classList.add('hidden'));
    $(`#${name}-view`).classList.remove('hidden');
    document.querySelectorAll('[data-view]').forEach((node) => node.setAttribute('aria-current', node.dataset.view === name ? 'page' : 'false'));
  }
  function entry(recipe) { return state.draft.entries.find((item) => item.recipeId === recipe.id); }
  function setBatches(recipe, batches) {
    if (state.pending) return notice('Resolve the pending submission before changing this draft.', true);
    const rest = state.draft.entries.filter((item) => item.recipeId !== recipe.id);
    state.draft.entries = batches < 1 ? rest : [...rest, { recipeId: recipe.id, revisionId: recipe.revisionId, batches: Math.min(1000, batches) }];
    state.draft.requestId = uuid(); state.preview = null; saveDraft(); renderRun();
  }
  function recipeCard(recipe, selectable = false) {
    const card = element('article', 'production-card'); const selected = selectable && entry(recipe); if (selected) card.classList.add('selected');
    const button = element('button', 'recipe-select'); button.type = 'button'; button.append(element('h3', '', recipe.name), element('p', 'production-meta', `Makes ${recipe.yieldAmount} ${recipe.yieldUnit} per batch`));
    if (selectable) { button.setAttribute('role', 'checkbox'); button.setAttribute('aria-checked', String(Boolean(selected))); button.setAttribute('aria-label', `${selected ? 'Remove' : 'Add'} ${recipe.name}`); button.addEventListener('click', () => setBatches(recipe, selected ? 0 : 1)); }
    else {
      const details = element('div', 'recipe-details hidden');
      if (recipe.instructions) details.append(element('p', '', recipe.instructions));
      const list = element('ul'); recipe.ingredients.forEach((item) => list.append(element('li', '', `${item.amount} ${item.unit} ${item.name}`))); details.append(list);
      button.setAttribute('aria-expanded', 'false'); button.addEventListener('click', () => { const open = details.classList.toggle('hidden') === false; button.setAttribute('aria-expanded', String(open)); }); card.append(button, details); return card;
    }
    card.append(button);
    if (selected) { const row = element('div', 'batch-row'); const minus = element('button', 'batch-button', '−'); minus.type = 'button'; minus.setAttribute('aria-label', `Remove one batch of ${recipe.name}`); minus.addEventListener('click', () => setBatches(recipe, selected.batches - 1));
      const count = element('div', 'batch-count'); count.append(element('strong', '', String(selected.batches)), element('small', '', selected.batches === 1 ? 'batch' : 'batches'));
      const plus = element('button', 'batch-button', '+'); plus.type = 'button'; plus.setAttribute('aria-label', `Add one batch of ${recipe.name}`); plus.disabled = selected.batches >= 1000; plus.addEventListener('click', () => setBatches(recipe, selected.batches + 1)); row.append(minus, count, plus); card.append(row); }
    return card;
  }
  function renderRun() {
    $('#production-date').value = state.draft.businessDate; const list = $('#production-recipes'); list.replaceChildren(); state.recipes.forEach((recipe) => list.append(recipeCard(recipe, true)));
    const book = $('#recipe-book'); book.replaceChildren(); state.recipes.forEach((recipe) => book.append(recipeCard(recipe)));
    const count = state.draft.entries.length; $('#production-selection').textContent = state.pending ? `Submission ${state.pending.logId} is awaiting recovery.` : count ? `${count} flavor${count === 1 ? '' : 's'} selected.` : 'Choose each flavor the crew made.';
    $('#review-production').disabled = Boolean(state.pending) || !count || !/^\d{4}-\d{2}-\d{2}$/.test(state.draft.businessDate); $('#clear-production').disabled = Boolean(state.pending); $('#retry-production').classList.toggle('hidden', !state.pending);
    $('#more-recipes').classList.toggle('hidden', !state.recipeNext); $('#more-recipe-book').classList.toggle('hidden', !state.recipeNext);
  }
  async function loadRecipes(append = false) {
    const generation = state.generation, context = actorKey(state.context); const after = append && state.recipeNext ? `&after=${encodeURIComponent(state.recipeNext)}` : '';
    const payload = await request(`/recipes?q=${encodeURIComponent(state.query)}${after}`); if (generation !== state.generation || !state.context || actorKey(state.context) !== context) return;
    const items = Array.isArray(payload.items) ? payload.items : []; state.recipes = append ? [...state.recipes, ...items] : items; state.recipeNext = payload.nextCursor || null; renderRun();
    if (!state.recipes.length) $('#recipe-book').append(element('p', 'production-card', 'No recipes are available yet. A manager or owner can create the first recipe in the native app.'));
  }
  function renderPreview(preview) {
    const issues = $('#production-issues'); issues.replaceChildren(); (preview.issues || []).forEach((issue) => issues.append(element('p', 'production-issue', typeof issue === 'string' ? issue : issue.message)));
    const entries = $('#production-entry-review'); entries.replaceChildren(); (preview.entries || []).slice(0, 100).forEach((item) => { const card = element('article', 'production-card'); card.append(element('h3', '', item.name || 'Recipe'), element('p', 'production-meta', `${item.batches} batch${item.batches === 1 ? '' : 'es'} · makes ${item.yieldAmount} ${item.yieldUnit} per batch`)); entries.append(card); });
    const list = $('#production-deductions'); list.replaceChildren(); (preview.deductions || []).forEach((item) => { const card = element('article', 'production-card'); card.append(element('h3', '', item.name)); const lines = element('div', 'deduction-lines');
      lines.append(element('span', '', `Recipe amount: ${item.recipeAmount} ${item.baseUnit}`), element('span', '', `1% allowance: +${item.allowanceAmount} ${item.baseUnit}`), element('span', 'deduction-total', `Total deduction: ${item.quantity} ${item.baseUnit}`), element('small', '', item.balance === null ? 'Current stock is unknown.' : `On hand ${item.balance} ${item.baseUnit} · remaining ${item.remaining ?? 'unknown'} ${item.baseUnit}`)); card.append(lines); list.append(card); });
    $('#production-confirm-check').checked = false; $('#confirm-production').disabled = true;
  }
  async function review() {
    if (state.busy || state.pending) return; state.busy = true; notice('Checking stock and adding the 1% allowance…');
    const generation = state.generation, context = actorKey(state.context), storeId = state.context.actor.storeId;
    try { await refreshContext(); if (generation !== state.generation || actorKey(state.context) !== context) throw new Error('Production context changed.');
      const body = { businessDate: state.draft.businessDate, entries: state.draft.entries.map(item => ({ ...item })), expectedStoreId: storeId };
      const preview = await request('/preview', { method: 'POST', body: JSON.stringify(body) }); if (generation !== state.generation || !state.context || actorKey(state.context) !== context) return;
      state.preview = preview; renderPreview(preview); show('review'); notice('');
    } catch (error) { notice(error.message, true); } finally { state.busy = false; }
  }
  async function recover(logId, generation, context) { try { const log = await request(`/logs/${encodeURIComponent(logId)}`); return generation === state.generation && state.context && actorKey(state.context) === context ? { status: 'found', log } : { status: 'stale' }; } catch (error) { if (generation !== state.generation || !state.context || actorKey(state.context) !== context) return { status: 'stale' }; return error.status === 404 ? { status: 'missing' } : { status: 'unknown', error }; } }
  function success(log) { state.pending = null; state.draft = emptyDraft(); state.preview = null; saveDraft(); renderRun(); notice(`Production saved for ${log.businessDate}. Stock deductions are recorded in log ${log.id}.`); void loadHistory(); show('history'); }
  async function resolvePending() { if (!state.pending) return true; const generation = state.generation, context = actorKey(state.context); notice(`Checking production log ${state.pending.logId}…`); const result = await recover(state.pending.logId, generation, context); if (result.status === 'found') { success(result.log); return true; } if (result.status === 'missing') notice('The saved log is not visible yet. The original request may still finish; keep this draft locked or retry the exact saved submission.', true); if (result.status === 'unknown') notice('The pending submission could not be resolved. This draft remains locked.', true); renderRun(); show('run'); return false; }
  async function confirm() {
    if (state.busy || state.pending || !state.preview?.canConfirm || !$('#production-confirm-check').checked) return; state.busy = true; notice('Confirming production…'); const button = $('#confirm-production'); button.disabled = true;
    const generation = state.generation, context = actorKey(state.context), storeId = state.context.actor.storeId;
    const submitted = { ...state.draft, entries: state.draft.entries.map((item) => ({ ...item })) };
    const submittedPayload = { ...submitted, confirmed: true, expectedStoreId: storeId };
    state.pending = { logId: submitted.logId, submittedAt: new Date().toISOString(), payload: submittedPayload }; saveDraft(); renderRun();
    try { await refreshContext(); if (generation !== state.generation || actorKey(state.context) !== context) return;
      const saved = await request('/logs', { method: 'POST', body: JSON.stringify(submittedPayload) }); if (generation === state.generation && state.context && actorKey(state.context) === context) success(saved); }
    catch (error) { if ([400, 409].includes(error.status) && generation === state.generation && state.context && actorKey(state.context) === context) { state.pending = null; state.preview = null; saveDraft(); renderRun(); show('run'); notice(`${error.message} Nothing was recorded. Fix the issue and review this same draft again.`, true); } else { const result = state.context ? await recover(submitted.logId, generation, context) : { status: 'stale' }; if (result.status === 'found') success(result.log); else if (result.status === 'missing') { renderRun(); notice(`${error.message} The log is not visible yet; the draft remains locked. Retry the exact saved submission.`, true); } else if (result.status === 'unknown') notice(`${error.message} Recovery is pending; this draft cannot be cleared or changed.`, true); } }
    finally { state.busy = false; }
  }
  async function retryPending() { if (state.busy || !state.pending?.payload) return; state.busy = true; const generation = state.generation, context = actorKey(state.context), payload = JSON.parse(JSON.stringify(state.pending.payload)); notice('Retrying the exact saved submission…'); try { await refreshContext(); if (generation !== state.generation || actorKey(state.context) !== context || state.context.actor.storeId !== payload.expectedStoreId) throw new Error('Your account or store changed. The saved submission was not retried.'); const saved = await request('/logs', { method: 'POST', body: JSON.stringify(payload) }); if (generation === state.generation && state.context && actorKey(state.context) === context) success(saved); } catch (error) { if ([400, 409].includes(error.status) && generation === state.generation && state.context && actorKey(state.context) === context) { state.pending = null; state.preview = null; saveDraft(); renderRun(); show('run'); notice(`${error.message} Nothing was recorded. Fix the issue and review this same draft again.`, true); } else { const result = state.context ? await recover(payload.logId, generation, context) : { status: 'stale' }; if (result.status === 'found') success(result.log); else if (result.status !== 'stale') notice(`${error.message} The saved submission remains locked with the same log and request IDs.`, true); } } finally { state.busy = false; } }
  function logCard(log) {
    const card = element('article', 'production-card'); const heading = element('h3', '', log.businessDate); const pill = element('span', `log-state ${log.state}`, log.state); card.append(heading, pill, element('p', 'production-meta', `Recorded by ${log.createdBy}`));
    const details = element('div', 'recipe-details'); (log.entries || []).forEach((item) => details.append(element('p', '', `${item.name || 'Recipe'} · ${item.batches} batch${item.batches === 1 ? '' : 'es'}`))); (log.ingredients || []).forEach((item) => details.append(element('small', '', `${item.name}: ${item.quantity} ${item.baseUnit} deducted`))); card.append(details); return card;
  }
  async function loadHistory(append = false) {
    const generation = state.generation, context = actorKey(state.context), after = append && state.historyNext ? `?after=${encodeURIComponent(state.historyNext)}` : ''; try { const payload = await request(`/logs${after}`); if (generation !== state.generation || !state.context || actorKey(state.context) !== context) return; const list = $('#production-history'); if (!append) list.replaceChildren(); const items = Array.isArray(payload.items) ? payload.items : [];
      if (!append && !items.length) list.append(element('p', 'production-card', 'No production has been recorded yet.')); items.forEach((log) => list.append(logCard(log))); state.historyNext = payload.nextCursor || null; $('#more-history').classList.toggle('hidden', !state.historyNext);
    } catch (error) { notice(error.message, true); }
  }
  async function open() { if (state.opening) return; state.opening = true; try { await refreshContext(); if (state.pending && !await resolvePending()) return; await loadRecipes(); await loadHistory(); renderRun(); show(state.context.actor.capabilities.includes('production.submit') ? 'run' : 'recipes'); document.querySelectorAll('[data-view="run"]').forEach(node => node.classList.toggle('hidden', !state.context.actor.capabilities.includes('production.submit'))); } catch (error) { clearPrivate(); window.location.replace('/'); } finally { state.opening = false; } }

  document.querySelectorAll('[data-view]').forEach((node) => node.addEventListener('click', () => show(node.dataset.view)));
  $('#production-date').addEventListener('change', (event) => { if (state.pending) return; state.draft.businessDate = event.target.value; state.draft.requestId = uuid(); saveDraft(); renderRun(); });
  $('#production-search-button').addEventListener('click', () => { state.query = $('#production-search').value.trim(); state.recipeNext = null; void loadRecipes(); }); $('#more-recipes').addEventListener('click', () => void loadRecipes(true)); $('#more-recipe-book').addEventListener('click', () => void loadRecipes(true));
  $('#review-production').addEventListener('click', review); $('#retry-production').addEventListener('click', retryPending); $('#clear-production').addEventListener('click', resetDraft); $('#refresh-history').addEventListener('click', () => { state.historyNext = null; void loadHistory(); }); $('#more-history').addEventListener('click', () => void loadHistory(true));
  $('#production-confirm-check').addEventListener('change', () => { $('#confirm-production').disabled = !state.preview?.canConfirm || !$('#production-confirm-check').checked; }); $('#confirm-production').addEventListener('click', confirm);
  $('#production-logout').addEventListener('click', async () => { try { await fetch('/api/accounts/logout', { method: 'POST' }); } finally { sessionStorage.removeItem(draftKey); clearPrivate(); window.location.replace('/'); } });
  window.addEventListener('focus', () => { if (state.context) void refreshContext().catch(() => { clearPrivate(); window.location.replace('/'); }); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state.context) void refreshContext().catch(() => { clearPrivate(); window.location.replace('/'); }); });
  window.addEventListener('pagehide', clearPrivate); void open();
  window.addEventListener('pageshow', () => { if (!state.context) void open(); });
})();
