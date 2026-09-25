(() => {
  const form = document.querySelector('#activation-form');
  const status = document.querySelector('#activation-status');
  const mode = document.querySelector('#activation-mode');
  // Fragments do not reach the HTTP server or referrer. Remove the secret from
  // browser history immediately; opening a link does not consume it.
  const invitation = new URLSearchParams(window.location.hash.slice(1)).getAll('invitation');
  if (window.location.hash) history.replaceState(null, '', window.location.pathname);
  if (invitation.length === 1 && /^[A-Za-z0-9_-]{32,512}$/.test(invitation[0])) {
    document.querySelector('#activation-token').value = invitation[0];
    fetch('/api/accounts/invitation-details', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: invitation[0] }) }).then(async response => {
        const value = await response.json();
        if (response.ok && document.querySelector('#activation-token').value === invitation[0]) {
          document.querySelector('#activation-intro').textContent = `Join ${value.storeName} as @${value.username}. Your account starts as crew.`;
        }
      }).catch(() => {});
  }

  const clearSecrets = () => {
    document.querySelector('#activation-token').value = '';
    document.querySelector('#activation-password').value = '';
    document.querySelector('#activation-confirm').value = '';
  };
  mode.addEventListener('change', () => {
    clearSecrets();
    const recovery = mode.value === 'recovery';
    document.querySelector('#activation-token-label').textContent = recovery ? 'Recovery code' : 'Activation code';
    document.querySelector('#activation-submit-label').textContent = recovery ? 'Reset password' : 'Activate account';
    document.querySelector('#activation-intro').textContent = recovery ? 'Use the recovery code provided after your identity was verified by the account support operator.' : 'Use the private activation code from your manager to choose your own password.';
    document.querySelector('#activation-help').textContent = recovery ? 'Recovery codes are provided through account support after identity verification. A store manager cannot reset the password used across all your stores.' : 'Codes expire and can be used once. Ask your manager for a replacement invitation if yours has expired.';
    status.classList.add('hidden');
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    status.classList.add('hidden');
    const password = document.querySelector('#activation-password').value;
    if (password !== document.querySelector('#activation-confirm').value) {
      status.textContent = 'Passwords must match.';
      status.classList.remove('hidden');
      return;
    }
    const button = document.querySelector('#activate-button');
    button.disabled = true;
    const recovery = mode.value === 'recovery';
    try {
      const response = await fetch(recovery ? '/api/accounts/reset-password' : '/api/accounts/activate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: document.querySelector('#activation-token').value.trim(), password }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'This code could not be used. Check the code or request a replacement.');
      clearSecrets();
      if (recovery) {
        status.textContent = 'Password reset. Sign in with your new password.';
        status.classList.remove('hidden');
        window.location.replace('/');
      } else {
        const capabilities = payload.actor?.capabilities || [];
        window.location.replace(capabilities.includes('reports.view') ? '/manager.html' : capabilities.includes('reports.submit') ? '/crew.html' : '/accounts.html');
      }
    } catch (error) {
      status.textContent = error.message || 'Connection unavailable. Please try again.';
      status.classList.remove('hidden');
    } finally { button.disabled = false; }
  });
  window.addEventListener('pagehide', clearSecrets);
})();
