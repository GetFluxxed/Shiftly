const $ = (selector) => document.querySelector(selector);
const notes = $('#notes');
const generateButton = $('#generate-button');
const emptyResult = $('#empty-result');
const resultContent = $('#result-content');
const loadingState = $('#loading-state');
const toast = $('#toast');
const MAX_CHARS = 2000;
const formatLocalDate = (value, options = { month: 'short', day: 'numeric', year: 'numeric' }) => value ? new Date(value).toLocaleDateString('en-US', options) : '';
let crewContext = null;
let contextGeneration = 0;
let checkingContext = null;

function clearCrewPrivate() {
  contextGeneration += 1;
  notes.value = '';
  $('#employee').value = '';
  $('#shift').value = 'opening';
  $('#character-count').textContent = '0 / 2,000';
  $('#result-summary').textContent = '';
  $('#result-date').textContent = '';
  $('#heads-up-message').textContent = 'No manager notes have been posted yet.';
  $('#heads-up-date').textContent = '';
  resultContent.classList.add('hidden');
  loadingState.classList.add('hidden');
  loadingState.style.display = '';
  emptyResult.classList.remove('hidden');
  generateButton.disabled = false;
}
function contextKey(payload) {
  return payload.actor ? `${payload.actor.userId}:${payload.actor.storeId}:${payload.actor.capabilities.join(',')}` : `legacy:${payload.role}`;
}
async function loadHeadsUp() {
  const generation = contextGeneration;
  try {
    const response = await fetch('/api/heads-up', { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || generation !== contextGeneration) return;
    $('#heads-up-message').textContent = payload.message || 'No manager notes have been posted yet.';
    $('#heads-up-date').textContent = payload.updatedAt ? `Updated ${formatLocalDate(payload.updatedAt)} ${new Date(payload.updatedAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}` : '';
  } catch { /* The report form remains usable when a notice is unavailable. */ }
}
async function refreshCrewContext() {
  if (checkingContext) return checkingContext;
  checkingContext = (async () => {
    const response = await fetch('/api/accounts/status', { cache: 'no-store' });
    let payload = await response.json();
    if (!response.ok) throw new Error('Please sign in again.');
    if (!payload.authenticated && payload.reauthenticationRequired) {
      const legacy = await fetch('/api/auth/status', { cache: 'no-store' });
      payload = await legacy.json();
      if (!legacy.ok) throw new Error('Please sign in again.');
    }
    if (!payload.authenticated) throw new Error('Please sign in again.');
    if (payload.actor && !payload.actor.capabilities.includes('reports.submit')) {
      clearCrewPrivate();
      window.location.replace('/accounts.html');
      throw new Error('Shift reporting is not available with your current access.');
    }
    const changed = crewContext && contextKey(crewContext) !== contextKey(payload);
    if (changed) { clearCrewPrivate(); showToast('Your store or account changed. The previous draft was cleared.'); }
    crewContext = payload;
    const capabilities = payload.actor?.capabilities || [];
    $('#management-link').classList.toggle('hidden', payload.actor ? !capabilities.includes('reports.view') : payload.role !== 'manager');
    $('#crew-account-link').classList.toggle('hidden', !payload.actor);
    $('#crew-inventory-link').classList.toggle('hidden', !capabilities.includes('inventory.view'));
    $('#crew-store-name').textContent = payload.actor ? payload.stores?.find((store) => store.storeId === payload.actor.storeId)?.storeName || 'Your selected store' : '';
    document.querySelector('main').style.visibility = 'visible';
    if (changed) loadHeadsUp();
    return !changed;
  })();
  try { return await checkingContext; }
  catch (error) {
    clearCrewPrivate();
    document.querySelector('main').style.visibility = 'hidden';
    window.location.replace('/');
    throw error;
  } finally { checkingContext = null; }
}
$('#crew-logout-button').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/accounts/logout', { method: 'POST' });
    if (!response.ok) throw new Error('Log out could not be completed. Please try again.');
    clearCrewPrivate();
    window.location.replace('/');
  } catch (error) { showToast(error.message); }
});
$('#today').textContent = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).toUpperCase();
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  window.setTimeout(() => toast.classList.remove('show'), 3500);
}
notes.addEventListener('input', () => {
  if (notes.value.length > MAX_CHARS) notes.value = notes.value.slice(0, MAX_CHARS);
  $('#character-count').textContent = `${notes.value.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`;
});
async function createBriefing() {
  const renderedStoreId = crewContext?.actor?.storeId;
  try { if (!await refreshCrewContext()) return; }
  catch (error) { showToast(error.message); return; }
  const expectedStoreId = renderedStoreId || crewContext?.actor?.storeId;
  const input = notes.value.trim();
  const employee = $('#employee').value.trim();
  const shift = $('#shift').value;
  if (!employee || !input) { showToast('Enter your name and meaningful shift notes.'); notes.focus(); return; }
  const generation = contextGeneration;
  emptyResult.classList.add('hidden');
  resultContent.classList.add('hidden');
  loadingState.classList.remove('hidden');
  loadingState.style.display = 'flex';
  generateButton.disabled = true;
  try {
    const response = await fetch('/api/reports', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ employee, shift, notes: input, ...(expectedStoreId ? { expectedStoreId } : {}) }),
    });
    const payload = await response.json();
    if (!response.ok) { const error = new Error(payload.error || 'The report could not be submitted.'); error.status = response.status; throw error; }
    if (generation !== contextGeneration) return;
    $('#result-date').textContent = formatLocalDate(payload.date).toUpperCase();
    $('#result-summary').textContent = `${employee ? `${employee} · ` : ''}Your report was reviewed and submitted successfully for manager review.`;
    loadingState.classList.add('hidden');
    loadingState.style.display = '';
    resultContent.classList.remove('hidden');
  } catch (error) {
    if (generation !== contextGeneration) return;
    loadingState.classList.add('hidden');
    loadingState.style.display = '';
    emptyResult.classList.remove('hidden');
    if (error.status === 422) { notes.focus(); notes.select(); }
    if (error.status === 409) { clearCrewPrivate(); refreshCrewContext().catch(() => {}); }
    showToast(error.message);
  } finally { generateButton.disabled = false; }
}
generateButton.addEventListener('click', createBriefing);
$('#new-button').addEventListener('click', () => { clearCrewPrivate(); loadHeadsUp(); $('#employee').focus(); });
window.addEventListener('focus', () => refreshCrewContext().catch(() => {}));
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshCrewContext().catch(() => {}); });
window.addEventListener('pageshow', () => refreshCrewContext().then(loadHeadsUp).catch(() => {}));
window.addEventListener('pagehide', () => { clearCrewPrivate(); document.querySelector('main').style.visibility = 'hidden'; });
refreshCrewContext().then(loadHeadsUp).catch(() => {});
