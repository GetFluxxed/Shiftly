(() => {
  async function load() {
    try {
      const response = await fetch('/api/accounts/status', { cache: 'no-store' });
      const payload = await response.json();
      if (!response.ok || !payload.authenticated) return window.location.replace('/');
      const capabilities = payload.actor.capabilities;
      if (!capabilities.includes('inventory.view')) return window.location.replace('/accounts.html');
      const home = capabilities.includes('reports.view') ? '/manager.html' : capabilities.includes('reports.submit') ? '/crew.html' : '/accounts.html';
      document.querySelectorAll('.inventory-home').forEach((link) => { link.href = home; });
      document.querySelector('#inventory-store').textContent = payload.stores.find((store) => store.storeId === payload.actor.storeId)?.storeName || 'Your store';
      document.querySelector('main').style.visibility = 'visible';
    } catch { document.querySelector('#inventory-empty-state').textContent = 'Your account access could not be checked. Please try again.'; }
  }
  window.addEventListener('focus', load);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  window.addEventListener('pageshow', load);
  window.addEventListener('pagehide', () => { document.querySelector('main').style.visibility = 'hidden'; });
  load();
})();
