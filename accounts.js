(() => {
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const labels = {
    'reports.submit': 'Submit shift reports', 'reports.view': 'Read reports and briefings', 'reports.manage': 'Update store notices',
    'inventory.view': 'View inventory', 'counts.submit': 'Submit stock counts', 'counts.approve': 'Approve stock counts',
    'receipts.draft': 'Prepare deliveries', 'receipts.post': 'Post deliveries', 'stock.adjust': 'Adjust stock',
    'configuration.manage': 'Manage store setup', 'catalog.propose': 'Suggest product changes', 'catalog.manage': 'Manage shared products',
    'memberships.manage': 'Manage team access',
  };
  const roleLabels = { owner: 'Business owner', admin: 'Delegated admin', manager: 'Store manager', crew: 'Crew member' };
  const crewOptions = ['inventory.view', 'counts.submit', 'receipts.draft', 'catalog.propose'];
  const managerDefaults = ['reports.submit', 'reports.view', 'reports.manage', 'inventory.view', 'counts.submit', 'counts.approve', 'receipts.draft', 'receipts.post', 'stock.adjust', 'configuration.manage', 'catalog.propose'];
  let state = null;
  let members = [];
  let busy = false;
  let refreshing = false;
  let contextGeneration = 0;
  const home = (actor) => actor.capabilities.includes('reports.view') ? '/manager.html' : actor.capabilities.includes('reports.submit') ? '/crew.html' : '/accounts.html';
  const can = (permission) => Boolean(state?.actor.capabilities.includes(permission));
  const message = (selector, text, failure = false) => {
    const element = $(selector);
    element.textContent = text;
    element.classList.toggle('hidden', !text);
    element.classList.toggle('is-error', failure);
  };
  function clearSecret() {
    $('#invitation-code').value = '';
    $('#invitation-message').textContent = '';
    $('#invitation-result').classList.add('hidden');
  }
  function clearPrivateForms() {
    clearSecret();
    document.querySelectorAll('form').forEach((form) => form.reset());
    $('#membership-editor').classList.add('hidden');
  }
  function protectPrivateView(text, redirect = false) {
    contextGeneration += 1;
    clearPrivateForms();
    state = null;
    members = [];
    $('#account-profile').textContent = 'Account details are hidden until your access can be checked.';
    $('#account-name').textContent = 'Your account';
    $('#team-list').replaceChildren();
    ['store-select', 'business-user', 'ownership-user', 'suspension-user'].forEach((id) => $(`#${id}`).replaceChildren());
    $('#membership-heading').textContent = 'Edit store access';
    $('#team-content').classList.add('hidden');
    $('#owner-section').classList.add('hidden');
    $('#store-form').classList.add('hidden');
    $('#refresh-team').classList.add('hidden');
    message('#account-status', text, true);
    document.querySelector('main').style.visibility = 'visible';
    $('#account-retry').classList.toggle('hidden', redirect);
    if (redirect) window.location.replace('/');
  }
  async function request(path, fields) {
    const response = await fetch(`/api/accounts/${path}`, fields === undefined ? { cache: 'no-store' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...fields, ...(state && path !== 'logout' ? { expectedStoreId: state.actor.storeId } : {}) }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || 'This action could not be completed. Please try again.');
      error.status = response.status;
      throw error;
    }
    return payload;
  }
  async function verifyContext() {
    let current;
    try { current = await request('status'); }
    catch (error) { protectPrivateView(error.message || 'Connection unavailable. Retry to check your account.', [401, 403].includes(error.status)); throw error; }
    if (!current.authenticated) {
      protectPrivateView('Please sign in again.', true);
      throw new Error('Please sign in again.');
    }
    if (state && (state.actor.userId !== current.actor.userId || state.actor.storeId !== current.actor.storeId || state.actor.role !== current.actor.role || state.actor.capabilities.join('|') !== current.actor.capabilities.join('|'))) {
      contextGeneration += 1;
      clearPrivateForms();
      state = current;
      await render();
      const changed = new Error('Your account or selected store changed in another tab. Review the current store before trying again.');
      changed.contextChanged = true;
      throw changed;
    }
    const needsRender = !state;
    state = current;
    if (needsRender) await render();
    $('#account-retry').classList.add('hidden');
    return current;
  }
  async function action(selector, operation) {
    if (busy) return;
    busy = true;
    message(selector, '');
    document.querySelectorAll('button').forEach((button) => { button.disabled = true; });
    try {
      await verifyContext();
      await operation();
    } catch (error) {
      message(selector, error.message || 'Connection unavailable. Please try again.', true);
      if (error.status === 401) {
        protectPrivateView('Your session ended. Please sign in again.', true);
      }
    } finally {
      busy = false;
      document.querySelectorAll('button').forEach((button) => { button.disabled = false; });
    }
  }
  function roleOptions(select, includeAdmin = false) {
    const previous = select.value;
    const options = ['crew'];
    if (state.actor.role === 'owner' || (state.actor.role === 'admin' && managerDefaults.every(can))) options.push('manager');
    if (includeAdmin && state.actor.role === 'owner') options.push('admin');
    select.innerHTML = options.map((role) => `<option value="${role}">${roleLabels[role]}</option>`).join('');
    if (options.includes(previous)) select.value = previous;
  }
  function permissions(container, role, selected = []) {
    let options = role === 'crew' ? crewOptions : role === 'manager' ? ['memberships.manage'] : Object.keys(labels);
    options = options.filter(can);
    container.innerHTML = `${role === 'crew' ? '<p class="account-help">Shift reporting is included. Choose any additional access:</p>' : role === 'manager' ? '<p class="account-help">Store managers have reporting and stock-operation permissions. Shared product editing requires a separate business delegation.</p>' : '<p class="account-help">Choose the permissions to delegate:</p>'}<fieldset><legend class="field-label">Permissions</legend>${options.map((capability) => `<label class="check-option"><input type="checkbox" value="${capability}" ${selected.includes(capability) ? 'checked' : ''} /> ${labels[capability]}</label>`).join('') || '<p class="account-help">No additional permissions are available for this role.</p>'}</fieldset>`;
  }
  const selectedPermissions = (id) => [...document.querySelectorAll(`${id} input:checked`)].map((input) => input.value);
  const memberLabel = (member) => `${member.displayName || member.username} (@${member.username})`;
  function editable(member) {
    if (member.userId === state.actor.userId) return false;
    if (state.actor.role === 'owner') return true;
    if ((member.businessState === 'active' && ['owner', 'admin'].includes(member.businessRole)) || member.role === 'admin') return false;
    if (state.actor.role === 'manager') return member.role === 'crew';
    const effective = member.role === 'manager' ? [...managerDefaults, ...member.capabilities] : ['reports.submit', ...member.capabilities];
    return effective.every(can);
  }
  function showInvitation(result, username) {
    $('#invitation-code').value = result.token;
    $('#invitation-message').textContent = `For ${username}. Expires in ${Math.round(result.expiresIn / 3600)} hours. Give this code only to the intended account holder.`;
    $('#invitation-result').classList.remove('hidden');
    $('#invitation-code').focus();
  }
  async function loadTeam() {
    const generation = contextGeneration;
    const storeId = state.actor.storeId;
    const payload = await request('team');
    if (generation !== contextGeneration || !state || state.actor.storeId !== storeId) return;
    if (payload.storeId !== storeId) { protectPrivateView('Your selected store changed. Retry to load the current team.'); throw new Error('Your selected store changed. Retry to load the current team.'); }
    members = payload.members;
    $('#team-list').innerHTML = members.length ? members.map((member) => {
      const allowed = editable(member);
      const status = member.accountState === 'pending' ? 'Awaiting activation' : member.accountState === 'suspended' ? 'Account suspended' : member.membershipState === 'revoked' ? 'Store access removed' : 'Active';
      return `<article class="team-member" data-user-id="${member.userId}"><div><h3>${esc(member.displayName || member.username)}${member.userId === state.actor.userId ? ' <small>(you)</small>' : ''}</h3><p>@${esc(member.username)} · ${member.businessRole === 'owner' && member.businessState === 'active' ? 'Business owner' : roleLabels[member.role] || 'Team member'}</p><span class="access-badge">${status}</span>${member.businessState === 'active' && member.businessRole === 'admin' ? `<p class="member-permissions">Business delegation: ${(member.businessCapabilities || []).map((capability) => esc(labels[capability] || 'Workspace access')).join(' · ') || 'No permissions delegated'}</p>` : ''}${member.capabilities.length ? `<p class="member-permissions">${member.capabilities.map((capability) => esc(labels[capability] || 'Workspace access')).join(' · ')}</p>` : ''}</div><div class="account-actions">${allowed ? '<button class="secondary-button" type="button" data-action="edit">Edit access</button>' : ''}${allowed && member.accountState === 'pending' && member.membershipState === 'active' ? '<button class="text-button" type="button" data-action="reissue">Reissue invitation</button>' : ''}${allowed && member.membershipState === 'active' ? '<button class="text-button danger-button" type="button" data-action="remove">Remove access</button>' : ''}</div></article>`;
    }).join('') : '<p class="pending-message">No store memberships yet. Create an invitation to bring your first team member in.</p>';
    const targets = members.filter((member) => member.userId !== state.actor.userId && member.accountState !== 'pending');
    ['business-user', 'ownership-user', 'suspension-user'].forEach((id) => {
      const eligible = targets.filter((member) => id === 'suspension-user' || member.accountState === 'active');
      $(`#${id}`).innerHTML = `<option value="">Choose a team member</option>${eligible.map((member) => `<option value="${member.userId}">${esc(memberLabel(member))}</option>`).join('')}`;
    });
  }
  async function render() {
    const actor = state.actor;
    const store = state.stores.find((item) => item.storeId === actor.storeId);
    $('#account-name').innerHTML = `${esc(actor.displayName)},<br /><em>make yourself at home.</em>`;
    $('#account-profile').innerHTML = `<p class="account-person"><strong>${esc(actor.displayName)}</strong><span>@${esc(actor.username)}</span></p><p>${roleLabels[actor.role] || 'Team member'} · <strong>${esc(store?.storeName || 'Your selected store')}</strong></p><ul class="access-list">${actor.capabilities.map((capability) => `<li>${esc(labels[capability] || 'Workspace access')}</li>`).join('')}</ul><details class="account-details"><summary>Account details</summary><p class="account-help">Account number: <strong>${actor.userId}</strong>. Share this number with a manager when joining another store.</p></details>`;
    document.querySelectorAll('.account-home').forEach((link) => { link.href = home(actor); });
    $('#operations-link').href = home(actor);
    $('#operations-link').classList.toggle('hidden', home(actor) === '/accounts.html');
    $('#inventory-link').classList.toggle('hidden', !can('inventory.view'));
    $('#store-select').innerHTML = state.stores.map((item) => `<option value="${item.storeId}" ${item.storeId === actor.storeId ? 'selected' : ''}>${esc(item.storeName)}</option>`).join('');
    $('#store-form').classList.remove('hidden');
    $('#switch-store').classList.toggle('hidden', state.stores.length < 2);
    $('#team-content').classList.toggle('hidden', !can('memberships.manage'));
    $('#refresh-team').classList.toggle('hidden', !can('memberships.manage'));
    $('#owner-section').classList.toggle('hidden', actor.role !== 'owner' || !can('memberships.manage'));
    $('#team-panel').textContent = can('memberships.manage') ? '' : 'Your current role does not include team administration. Ask your store manager if your access needs to change.';
    if (can('memberships.manage')) {
      ['invite-role', 'existing-member-role'].forEach((id) => roleOptions($(`#${id}`)));
      roleOptions($('#member-role'), true);
      permissions($('#invite-capabilities'), $('#invite-role').value);
      permissions($('#existing-member-capabilities'), $('#existing-member-role').value);
      permissions($('#business-capabilities'), 'admin');
      $('#business-capabilities').classList.toggle('hidden', $('#business-role').value === 'owner');
      await loadTeam();
    } else {
      members = [];
      $('#team-list').replaceChildren();
    }
  }
  $('#store-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const storeId = Number($('#store-select').value);
    action('#account-status', async () => {
      if (storeId === state.actor.storeId) return;
      await request('switch-store', { storeId });
      contextGeneration += 1;
      clearPrivateForms();
      state = await request('status');
      await render();
      message('#account-status', 'Store changed. Your access now reflects this store.');
    });
  });
  $('#invite-role').addEventListener('change', () => permissions($('#invite-capabilities'), $('#invite-role').value));
  $('#member-role').addEventListener('change', () => permissions($('#member-capabilities'), $('#member-role').value));
  $('#existing-member-role').addEventListener('change', () => permissions($('#existing-member-capabilities'), $('#existing-member-role').value));
  $('#business-role').addEventListener('change', () => $('#business-capabilities').classList.toggle('hidden', $('#business-role').value === 'owner'));
  $('#business-user').addEventListener('change', () => {
    const member = members.find((item) => item.userId === Number($('#business-user').value));
    $('#business-role').value = member?.businessRole || 'admin';
    $('#business-active').checked = !member?.businessState || member.businessState === 'active';
    permissions($('#business-capabilities'), 'admin', member?.businessCapabilities || []);
    $('#business-capabilities').classList.toggle('hidden', $('#business-role').value === 'owner');
  });
  $('#invite-form').addEventListener('submit', (event) => {
    event.preventDefault();
    action('#team-status', async () => {
      const username = $('#invite-username').value.trim();
      const result = await request('invitations', { username, displayName: $('#invite-display-name').value.trim(), role: $('#invite-role').value, capabilities: selectedPermissions('#invite-capabilities'), storeId: state.actor.storeId });
      $('#invite-form').reset();
      permissions($('#invite-capabilities'), $('#invite-role').value);
      await loadTeam();
      showInvitation(result, username);
      message('#team-status', 'Invitation created. The person chooses their own password when activating.');
    });
  });
  $('#dismiss-invitation').addEventListener('click', clearSecret);
  $('#team-list').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const member = members.find((item) => item.userId === Number(button.closest('[data-user-id]').dataset.userId));
    if (!member) return;
    if (button.dataset.action === 'edit') {
      $('#member-user').value = member.userId;
      $('#membership-heading').textContent = `Store access for ${member.displayName || member.username}`;
      $('#member-role').value = member.role;
      $('#member-active').checked = member.membershipState === 'active';
      permissions($('#member-capabilities'), member.role, member.capabilities);
      $('#membership-editor').classList.remove('hidden');
      $('#member-role').focus();
      return;
    }
    if (button.dataset.action === 'remove' && !window.confirm(`Remove ${memberLabel(member)} from this store? Their sessions for this store will end. Access at other stores stays in place.`)) return;
    if (button.dataset.action === 'reissue' && !window.confirm(`Replace the activation code for ${memberLabel(member)}? The previous code will stop working.`)) return;
    action('#team-status', async () => {
      if (button.dataset.action === 'reissue') {
        const result = await request('invitations/reissue', { userId: member.userId, storeId: state.actor.storeId });
        showInvitation(result, member.username);
        message('#team-status', 'A replacement invitation is ready.');
      } else {
        await request('memberships', { userId: member.userId, role: member.role, capabilities: member.capabilities, active: false, storeId: state.actor.storeId, reason: 'Store access removed by team administrator' });
        clearSecret();
        await loadTeam();
        message('#team-status', 'Store access removed.');
      }
    });
  });
  $('#membership-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!window.confirm('Save these store permissions? This person will need to sign in again for this store.')) return;
    action('#team-status', async () => {
      await request('memberships', { userId: Number($('#member-user').value), role: $('#member-role').value, capabilities: selectedPermissions('#member-capabilities'), active: $('#member-active').checked, storeId: state.actor.storeId });
      $('#membership-editor').classList.add('hidden');
      clearSecret();
      await loadTeam();
      message('#team-status', 'Store permissions updated.');
    });
  });
  $('#cancel-membership').addEventListener('click', () => $('#membership-editor').classList.add('hidden'));
  $('#existing-member-form').addEventListener('submit', (event) => {
    event.preventDefault();
    action('#team-status', async () => {
      await request('memberships', { userId: Number($('#existing-member-id').value), role: $('#existing-member-role').value, capabilities: selectedPermissions('#existing-member-capabilities'), active: true, storeId: state.actor.storeId });
      $('#existing-member-form').reset();
      await loadTeam();
      message('#team-status', 'Account added to this store. Their password is unchanged.');
    });
  });
  $('#refresh-team').addEventListener('click', () => action('#team-status', loadTeam));
  $('#password-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if ($('#new-password').value !== $('#confirm-password').value) return message('#password-status', 'New passwords must match.', true);
    action('#password-status', async () => {
      await request('password', { currentPassword: $('#current-password').value, newPassword: $('#new-password').value });
      clearPrivateForms();
      window.location.replace('/');
    });
  });
  $('#account-logout').addEventListener('click', async () => {
    try { await request('logout', {}); clearPrivateForms(); window.location.replace('/'); }
    catch (error) { message('#account-status', error.message, true); }
  });
  $('#logout-all').addEventListener('click', () => {
    if (!window.confirm('Log out of Shiftly on every device, including this one?')) return;
    action('#account-status', async () => { await request('logout-all', {}); clearPrivateForms(); window.location.replace('/'); });
  });
  $('#business-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const role = $('#business-role').value;
    if (!window.confirm(role === 'owner' ? 'Change business ownership authority for this person? Owners can manage the whole business and appoint other owners.' : 'Update this person’s business delegation? Their current sessions in this business will end.')) return;
    action('#owner-status', async () => {
      await request('business-memberships', { userId: Number($('#business-user').value), role, capabilities: role === 'owner' ? [] : selectedPermissions('#business-capabilities'), active: $('#business-active').checked });
      await loadTeam();
      message('#owner-status', 'Business authority updated. For an admin, also review their store role and matching permissions.');
    });
  });
  $('#ownership-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!window.confirm('Transfer your ownership to this person? Your owner access will be removed and you will be signed out.')) return;
    action('#owner-status', async () => { await request('transfer-ownership', { userId: Number($('#ownership-user').value), reason: 'Owner confirmed ownership transfer' }); clearPrivateForms(); window.location.replace('/'); });
  });
  $('#suspension-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const suspended = $('#suspension-action').value === 'suspend';
    if (!window.confirm(suspended ? 'Suspend this entire account? All sessions and access at every store will end.' : 'Restore this account? Their existing active memberships will become available again.')) return;
    action('#owner-status', async () => {
      await request('suspend', { userId: Number($('#suspension-user').value), suspended, reason: $('#suspension-reason').value.trim() });
      await loadTeam();
      message('#owner-status', suspended ? 'Account suspended.' : 'Account restored. They can sign in again.');
    });
  });
  $('#cutover-button').addEventListener('click', () => {
    if (!window.confirm('Disable shared crew sign-in for this store? Existing shared sessions will end immediately. Every crew member will need an activated individual account.')) return;
    action('#owner-status', async () => {
      await request('cutover', { storeId: state.actor.storeId, reason: 'Owner confirmed individual crew sign-in cutover' });
      message('#owner-status', 'Shared crew sign-in is disabled for this store. Individual accounts continue to work.');
    });
  });
  async function refreshOnFocus() {
    if (busy || refreshing) return;
    refreshing = true;
    try { await verifyContext(); document.querySelector('main').style.visibility = 'visible'; }
    catch (error) {
      if (error.contextChanged) message('#account-status', error.message, true);
      else protectPrivateView(error.message || 'Connection unavailable. Retry to check your account.', [401, 403].includes(error.status));
    }
    finally { refreshing = false; }
  }
  $('#account-retry').addEventListener('click', refreshOnFocus);
  window.addEventListener('focus', refreshOnFocus);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshOnFocus(); });
  window.addEventListener('pageshow', refreshOnFocus);
  window.addEventListener('pagehide', () => { contextGeneration += 1; clearPrivateForms(); document.querySelector('main').style.visibility = 'hidden'; });
  refreshOnFocus();
})();
