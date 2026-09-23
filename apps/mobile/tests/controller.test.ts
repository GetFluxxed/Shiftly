/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, type Transport } from '../src/api/client';
import type { AccountStatus, Actor, IssuedSession, RequestOptions } from '../src/api/types';
import { SessionController, type CredentialStore } from '../src/session/controller';

const TOKEN_A = 'a'.repeat(43);
const TOKEN_B = 'b'.repeat(43);
const person = (storeId = 7): Actor => ({ userId: 11, username: 'crew.one', displayName: 'Crew One',
  storeId, businessId: 3, role: 'crew', capabilities: ['reports.submit'], provenance: 'named' });
const status = (storeId = 7): AccountStatus => ({ authenticated: true, actor: person(storeId),
  stores: [7, 8].map(id => ({ ...person(id), storeName: `Store ${id}` })) });
const issued = (token = TOKEN_A, storeId = 7): IssuedSession => ({ ...status(storeId),
  sessionToken: token, expiresIn: 28_800, storeName: `Store ${storeId}` });
const fields = { storeCode: 'test-store', username: 'crew.one', password: 'test-password' };
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
type Call = { path: string; options: RequestOptions; token?: string };
function harness(initial: string | null = TOKEN_A) {
  let stored = initial;
  const calls: Call[] = [];
  let handler: (call: Call) => unknown | Promise<unknown> = call => call.path === '/accounts/status' ? status() : {};
  const credentials: CredentialStore = {
    read: async () => stored,
    write: async value => { stored = value; },
    remove: async () => { stored = null; },
  };
  const transport: Transport = {
    send: async <T>(path: string, options: RequestOptions = {}, token?: string): Promise<T> => {
      const call = { path, options, token }; calls.push(call); return await handler(call) as T;
    },
  };
  const controller = new SessionController(transport, credentials);
  return { controller, credentials, calls, stored: () => stored, setStored: (token: string | null) => { stored = token; },
    handle: (next: typeof handler) => { handler = next; } };
}
function assertPrivateCleared(controller: SessionController) {
  assert.equal(controller.getSnapshot().actor, null);
  assert.deepEqual(controller.getSnapshot().stores, []);
}

// These tests use deferred I/O to reproduce actual response/storage reorderings.
// They verify externally visible safety outcomes rather than controller internals.

test('restore waits for server validation and never exposes tokens through React state', async () => {
  const h = harness(); const answer = deferred<AccountStatus>();
  h.handle(() => answer.promise);
  const opening = h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'loading'); assertPrivateCleared(h.controller);
  answer.resolve(status()); await opening;
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.equal(h.controller.getSnapshot().actor?.storeId, 7);
  assert.equal(JSON.stringify(h.controller.getSnapshot()).includes(TOKEN_A), false);
  assert.equal(h.calls[0]?.token, TOKEN_A);
});

test('offline restore hides all private state while retaining the credential for an explicit retry', async () => {
  const h = harness(); h.handle(() => { throw new ApiError('Offline'); });
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), TOKEN_A);
  h.handle(() => status()); await h.controller.retry();
  assert.equal(h.controller.getSnapshot().status, 'ready');
});

test('revoked restore removes the stored session and requires fresh sign-in', async () => {
  const h = harness(); h.handle(() => { throw new ApiError('Revoked', 401); });
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), null);
});

test('malformed status cannot expose a roster from a different account', async () => {
  const h = harness(); h.handle(() => ({ ...status(), stores: [{ ...person(), userId: 999, storeName: 'Other account' }] }));
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
});

test('a write is bound to the rendered account store even if caller supplies another expected store', async () => {
  const h = harness(); await h.controller.restore();
  await h.controller.request('/reports', { method: 'POST', body: { notes: 'Shift notes', expectedStoreId: 999 } });
  assert.deepEqual(h.calls.at(-1)?.options.body, { notes: 'Shift notes', expectedStoreId: 7 });
  assert.equal(h.calls.at(-1)?.token, TOKEN_A);
});

for (const code of [403, 409]) {
  test(`${code} clears private context and requires server revalidation before another action`, async () => {
    const h = harness(); await h.controller.restore();
    h.handle(() => { throw new ApiError('Access changed', code); });
    await assert.rejects(h.controller.request('/reports'), error => error instanceof ApiError && error.status === code);
    assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
    const count = h.calls.length;
    await assert.rejects(h.controller.request('/reports'), ApiError);
    assert.equal(h.calls.length, count);
    h.handle(() => status()); await h.controller.retry();
    assert.equal(h.controller.getSnapshot().status, 'ready');
  });
}

test('a 401 on a private request clears the credential as well as private state', async () => {
  const h = harness(); await h.controller.restore();
  h.handle(() => { throw new ApiError('Revoked', 401); });
  await assert.rejects(h.controller.request('/reports'), ApiError);
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), null);
});

test('backgrounding discards a previously started private response and blocks new requests', async () => {
  const h = harness(); await h.controller.restore();
  const answer = deferred<unknown>(); h.handle(() => answer.promise);
  const pending = h.controller.request('/reports');
  h.controller.lock();
  assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
  answer.resolve({ reports: [{ notes: 'Private report' }] });
  await assert.rejects(pending, /session changed/i);
  const count = h.calls.length;
  await assert.rejects(h.controller.request('/reports'), ApiError); assert.equal(h.calls.length, count);
});

test('switching stores rotates credentials and discards responses from the previous store', async () => {
  const h = harness(); await h.controller.restore();
  const oldReports = deferred<unknown>();
  h.handle(call => call.path === '/reports' ? oldReports.promise
    : call.path === '/accounts/switch-store' ? issued(TOKEN_B, 8) : status(8));
  const pending = h.controller.request('/reports');
  const switching = h.controller.switchStore(8);
  assertPrivateCleared(h.controller);
  await switching;
  assert.equal(h.controller.getSnapshot().actor?.storeId, 8); assert.equal(h.stored(), TOKEN_B);
  const switchCall = h.calls.find(call => call.path === '/accounts/switch-store');
  assert.equal(switchCall?.token, TOKEN_A);
  assert.deepEqual(switchCall?.options.body, { storeId: 8, expectedStoreId: 7 });
  oldReports.resolve({ reports: [{ notes: 'Old store private report' }] });
  await assert.rejects(pending, /session changed/i);
});

test('unavailable store selections never reach the server', async () => {
  const h = harness(); await h.controller.restore(); const count = h.calls.length;
  await assert.rejects(h.controller.switchStore(999), error => error instanceof ApiError && error.status === 403);
  assert.equal(h.calls.length, count);
});

test('sign-out immediately hides private state and invalidates a pending report response', async () => {
  const h = harness(); await h.controller.restore();
  const report = deferred<unknown>(), logout = deferred<unknown>();
  h.handle(call => call.path === '/reports' ? report.promise : logout.promise);
  const pending = h.controller.request('/reports'); const signingOut = h.controller.signOut();
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  report.resolve({ reports: [] }); await assert.rejects(pending, /session changed/i);
  logout.resolve({}); await signingOut; assert.equal(h.stored(), null);
});

test('a login response arriving after background lock cannot reopen a private session', async () => {
  const h = harness(null); await h.controller.restore();
  const login = deferred<IssuedSession>();
  h.handle(call => call.path === '/accounts/login' ? login.promise : {});
  const pending = h.controller.signIn(fields); h.controller.lock();
  login.resolve(issued()); await assert.rejects(pending, /session changed/i);
  assertPrivateCleared(h.controller); assert.equal(h.stored(), null);
  assert.ok(h.calls.some(call => call.path === '/accounts/logout' && call.token === TOKEN_A));
});

test('a failed secure-store write revokes the newly issued session and stays signed out', async () => {
  const h = harness(null); await h.controller.restore();
  h.credentials.write = async () => { throw new Error('OS storage failure with private details'); };
  h.handle(call => call.path === '/accounts/login' ? issued() : {});
  await assert.rejects(h.controller.signIn(fields), /Secure sign-in could not be saved/);
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), null);
  assert.ok(h.calls.some(call => call.path === '/accounts/logout' && call.token === TOKEN_A));
});

test('a secure-store write completing after backgrounding is removed and cannot resurrect sign-in', async () => {
  const h = harness(null); await h.controller.restore();
  const started = deferred<void>(), finish = deferred<void>();
  h.credentials.write = async token => { started.resolve(); await finish.promise; h.setStored(token); };
  h.handle(call => call.path === '/accounts/login' ? issued() : {});
  const pending = h.controller.signIn(fields); await started.promise;
  h.controller.lock(); finish.resolve();
  await assert.rejects(pending, /session changed/i);
  assertPrivateCleared(h.controller); assert.equal(h.stored(), null);
  assert.ok(h.calls.some(call => call.path === '/accounts/logout' && call.token === TOKEN_A));
});

test('older sign-out network completion cannot remove or clear a newer sign-in', async () => {
  const h = harness(); await h.controller.restore(); const logout = deferred<unknown>();
  h.handle(call => call.path === '/accounts/logout' ? logout.promise
    : call.path === '/accounts/login' ? issued(TOKEN_B) : status());
  const signingOut = h.controller.signOut();
  // A lifecycle transition can interrupt the pending server logout and permit a fresh sign-in.
  h.controller.lock(); await h.controller.signIn(fields);
  assert.equal(h.stored(), TOKEN_B); assert.equal(h.controller.getSnapshot().status, 'ready');
  logout.resolve({}); await signingOut;
  assert.equal(h.stored(), TOKEN_B); assert.equal(h.controller.getSnapshot().status, 'ready');
});

test('logout-all carries current scope and reports partial failure without claiming other devices were revoked', async () => {
  const h = harness(); await h.controller.restore();
  h.handle(() => { throw new ApiError('Offline'); });
  await h.controller.signOut(true);
  assert.equal(h.stored(), null); assertPrivateCleared(h.controller);
  assert.equal(h.calls.at(-1)?.path, '/accounts/logout-all');
  assert.deepEqual(h.calls.at(-1)?.options.body, { expectedStoreId: 7 });
  assert.match(h.controller.getSnapshot().message || '', /finish signing out your other devices/);
});

test('password change returns to signed-out state with no reusable local credential', async () => {
  const h = harness(); await h.controller.restore();
  await h.controller.changePassword('old-password', 'new-password');
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), null);
  assert.equal(h.calls.at(-1)?.path, '/accounts/password');
  assert.deepEqual(h.calls.at(-1)?.options.body, { currentPassword: 'old-password', newPassword: 'new-password', expectedStoreId: 7 });
});


test('a migrated named manager with no business mapping retains authorized reporting access', async () => {
  const h = harness();
  const actor = { ...person(), role: 'manager', businessId: null, capabilities: ['reports.view', 'reports.submit'] };
  h.handle(() => ({ authenticated: true, actor, stores: [{ ...actor, storeName: 'Compatibility store' }] }));
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.equal(h.controller.getSnapshot().actor?.businessId, null);
  assert.equal(h.controller.getSnapshot().actor?.role, 'manager');
  assert.deepEqual(h.controller.getSnapshot().actor?.capabilities, ['reports.view', 'reports.submit']);
});

test('failed device deletion and offline logout cannot restore the discarded live credential', async () => {
  const h = harness(); await h.controller.restore();
  const initialStatusCalls = h.calls.filter(call => call.path === '/accounts/status').length;
  h.credentials.remove = async () => { throw new Error('Device deletion is unavailable'); };
  h.handle(call => {
    if (call.path === '/accounts/logout') throw new ApiError('Offline');
    return status(); // The original token is still live on the server.
  });
  await h.controller.signOut();
  assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), TOKEN_A);
  await h.controller.restore();
  assert.notEqual(h.controller.getSnapshot().status, 'ready'); assertPrivateCleared(h.controller);
  h.controller.lock(); await h.controller.retry();
  assert.notEqual(h.controller.getSnapshot().status, 'ready'); assertPrivateCleared(h.controller);
  await h.controller.restore();
  assert.notEqual(h.controller.getSnapshot().status, 'ready'); assertPrivateCleared(h.controller);
  assert.equal(h.calls.filter(call => call.path === '/accounts/status').length, initialStatusCalls,
    'Lifecycle retries must finish sign-out, never validate the discarded token');
});

test('explicit retry completes pending sign-out when device storage and the server recover', async () => {
  const h = harness(); await h.controller.restore();
  h.credentials.remove = async () => { throw new Error('Device deletion is unavailable'); };
  h.handle(() => { throw new ApiError('Offline'); });
  await h.controller.signOut();
  assertPrivateCleared(h.controller);
  h.credentials.remove = async () => { h.setStored(null); };
  h.handle(call => call.path === '/accounts/status' ? status() : {});
  const count = h.calls.length;
  await h.controller.retry();
  assert.equal(h.stored(), null); assert.equal(h.controller.getSnapshot().status, 'signedOut');
  assertPrivateCleared(h.controller);
  const retryCalls = h.calls.slice(count);
  assert.ok(retryCalls.some(call => call.path === '/accounts/logout' && call.token === TOKEN_A));
  assert.equal(retryCalls.some(call => call.path === '/accounts/status'), false);
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
});

test('a new explicit login survives completion of an older pending sign-out retry', async () => {
  const h = harness(); await h.controller.restore();
  h.credentials.remove = async () => { throw new Error('Device deletion is unavailable'); };
  h.handle(() => { throw new ApiError('Offline'); });
  await h.controller.signOut();
  h.credentials.remove = async () => { h.setStored(null); };
  const logout = deferred<unknown>();
  h.handle(call => call.path === '/accounts/logout' ? logout.promise
    : call.path === '/accounts/login' ? issued(TOKEN_B) : status());
  const retry = h.controller.retry();
  h.controller.lock();
  await h.controller.signIn(fields);
  assert.equal(h.stored(), TOKEN_B); assert.equal(h.controller.getSnapshot().status, 'ready');
  logout.resolve({}); await retry;
  assert.equal(h.stored(), TOKEN_B); assert.equal(h.controller.getSnapshot().status, 'ready');
  h.controller.lock(); await h.controller.restore();
  assert.equal(h.stored(), TOKEN_B); assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.equal(h.calls.at(-1)?.token, TOKEN_B);
});

test('a late login write with failed cleanup cannot restore a session discarded during backgrounding', async () => {
  const h = harness(null); await h.controller.restore();
  const started = deferred<void>(), finish = deferred<void>();
  h.credentials.write = async token => { started.resolve(); await finish.promise; h.setStored(token); };
  h.credentials.remove = async () => { throw new Error('Device deletion is unavailable'); };
  h.handle(call => {
    if (call.path === '/accounts/login') return issued(TOKEN_A);
    if (call.path === '/accounts/logout') throw new ApiError('Offline');
    return status();
  });
  const pending = h.controller.signIn(fields); await started.promise;
  h.controller.lock(); finish.resolve();
  await assert.rejects(pending, /session changed/i);
  assertPrivateCleared(h.controller); assert.equal(h.stored(), TOKEN_A);
  const count = h.calls.filter(call => call.path === '/accounts/status').length;
  await h.controller.restore();
  assert.notEqual(h.controller.getSnapshot().status, 'ready'); assertPrivateCleared(h.controller);
  h.controller.lock(); await h.controller.retry();
  assert.notEqual(h.controller.getSnapshot().status, 'ready'); assertPrivateCleared(h.controller);
  assert.equal(h.calls.filter(call => call.path === '/accounts/status').length, count);
});

test('an unchanged access refresh preserves the workspace revision and an in-flight private response', async () => {
  const h = harness(); await h.controller.restore();
  const snapshot = h.controller.getSnapshot(), report = deferred<unknown>();
  h.handle(call => call.path === '/reports' ? report.promise : status());
  const pending = h.controller.request('/reports');
  await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot(), snapshot,
    'An unchanged status response must not remount screens or discard a draft');
  report.resolve({ reports: [] });
  assert.deepEqual(await pending, { reports: [] });
});

test('losing another authorized store advances the workspace revision and invalidates an old inbox response', async () => {
  const h = harness(); await h.controller.restore();
  const revision = h.controller.getSnapshot().revision, report = deferred<unknown>();
  const reduced = { ...status(), stores: [{ ...person(), storeName: 'Store 7' }] };
  h.handle(call => call.path === '/reports' ? report.promise : reduced);
  const pending = h.controller.request('/reports');
  await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot().actor?.storeId, 7);
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.ok(h.controller.getSnapshot().revision > revision);
  assert.deepEqual(h.controller.getSnapshot().stores.map(store => store.storeId), [7]);
  report.resolve({ reports: [{ storeId: 8, notes: 'Access has been removed' }] });
  await assert.rejects(pending, /session changed/i);
});

test('a capability change advances the workspace revision without retaining the previous grant', async () => {
  const h = harness(); await h.controller.restore(); const revision = h.controller.getSnapshot().revision;
  const actor = { ...person(), capabilities: [] };
  h.handle(() => ({ authenticated: true, actor, stores: [{ ...actor, storeName: 'Store 7' }] }));
  await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.deepEqual(h.controller.getSnapshot().actor?.capabilities, []);
  assert.ok(h.controller.getSnapshot().revision > revision);
});

test('periodic access refresh removes a remotely revoked session before exposing more private data', async () => {
  const h = harness(); await h.controller.restore();
  h.handle(() => { throw new ApiError('Revoked', 401); });
  await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot().status, 'signedOut'); assertPrivateCleared(h.controller);
  assert.equal(h.stored(), null);
});

for (const code of [0, 403]) {
  test(`access refresh failure ${code} locks and hides private data instead of preserving stale access`, async () => {
    const h = harness(); await h.controller.restore();
    h.handle(() => { throw new ApiError(code ? 'Access denied' : 'Offline', code); });
    await h.controller.refreshAccess();
    assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
    const count = h.calls.length;
    await assert.rejects(h.controller.request('/reports'), ApiError);
    assert.equal(h.calls.length, count);
  });
}

test('a periodic refresh completed after background lock cannot resurrect the workspace', async () => {
  const h = harness(); await h.controller.restore(); const answer = deferred<AccountStatus>();
  h.handle(() => answer.promise);
  const refreshing = h.controller.refreshAccess();
  h.controller.lock(); const locked = h.controller.getSnapshot();
  answer.resolve(status()); await refreshing;
  assert.equal(h.controller.getSnapshot(), locked);
  assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
});

test('overlapping periodic refreshes send one status request and never run while locked', async () => {
  const h = harness(); await h.controller.restore(); const answer = deferred<AccountStatus>();
  h.handle(() => answer.promise); const count = h.calls.length;
  const first = h.controller.refreshAccess(); await h.controller.refreshAccess();
  assert.equal(h.calls.length, count + 1);
  answer.resolve(status()); await first;
  h.controller.lock(); await h.controller.refreshAccess();
  assert.equal(h.calls.length, count + 1);
});

test('duplicate foreground retries do not reject while a pending sign-out cleanup is already running', async () => {
  const h = harness(); await h.controller.restore();
  h.credentials.remove = async () => { throw new Error('Device deletion is unavailable'); };
  h.handle(() => { throw new ApiError('Offline'); });
  await h.controller.signOut();
  const logout = deferred<unknown>();
  h.handle(() => logout.promise);
  const first = h.controller.retry(); const count = h.calls.length;
  await h.controller.retry();
  assert.equal(h.calls.length, count);
  logout.resolve({}); await first;
  assertPrivateCleared(h.controller);
});

test('ownership transfer binds the current store and removes the local credential on success', async () => {
  const h = harness(); await h.controller.restore();
  await h.controller.transferOwnership(22, 'Confirmed recipient');
  const call = h.calls.find(item => item.path === '/accounts/transfer-ownership');
  assert.deepEqual(call?.options.body, { userId: 22, reason: 'Confirmed recipient', expectedStoreId: 7 });
  assert.equal(h.stored(), null);
  assert.equal(h.controller.getSnapshot().status, 'signedOut');
  assertPrivateCleared(h.controller);
});

test('a delayed ownership transfer cannot clear a newer account session', async () => {
  const h = harness(); await h.controller.restore();
  const pending = deferred<unknown>();
  h.handle(call => call.path === '/accounts/transfer-ownership' ? pending.promise
    : call.path === '/accounts/login' ? issued(TOKEN_B) : status());
  const transferring = h.controller.transferOwnership(22, 'Confirmed recipient');
  const rejected = assert.rejects(transferring, /session changed/);
  await h.controller.signOut(); await h.controller.signIn(fields);
  pending.resolve({ ownerUserId: 22 }); await rejected;
  assert.equal(h.stored(), TOKEN_B);
  assert.equal(h.controller.getSnapshot().status, 'ready');
});

test('uncertain ownership transfer is not replayed and a revoked session is cleared on revalidation', async () => {
  const h = harness(); await h.controller.restore();
  h.handle(() => { throw new ApiError('Could not confirm account change'); });
  await assert.rejects(h.controller.transferOwnership(22, ''), /Could not confirm/);
  assert.equal(h.calls.filter(call => call.path === '/accounts/transfer-ownership').length, 1);
  h.handle(() => { throw new ApiError('Session revoked', 401); });
  await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot().status, 'signedOut');
  assert.equal(h.stored(), null);
});

for (const code of ['duplicate_identifier', 'state_conflict', 'stale_record']) {
  test(`${code} preserves the workspace and pending private results`, async () => {
    const h = harness(); await h.controller.restore();
    const before = h.controller.getSnapshot(), pending = deferred<unknown>();
    h.handle(call => {
      if (call.path === '/heads-up') return pending.promise;
      throw new ApiError('Correct this value.', 409, code);
    });
    const reading = h.controller.request('/heads-up');
    await assert.rejects(h.controller.request('/inventory/products', { method: 'POST', body: { sku: '0001' } }), /Correct this value/);
    assert.equal(h.controller.getSnapshot(), before);
    assert.equal(h.stored(), TOKEN_A);
    pending.resolve({ message: 'Still in the same store' });
    assert.deepEqual(await reading, { message: 'Still in the same store' });
  });
}

for (const [statusCode, code] of [[409, 'store_context_changed'], [403, 'access_changed'], [409, 'future_code'],
  [403, 'duplicate_identifier'], [409, 'permission_denied']] as const) {
  test(`${statusCode}/${code} cannot bypass workspace invalidation`, async () => {
    const h = harness(); await h.controller.restore();
    h.handle(() => { throw new ApiError('Revalidation required', statusCode, code); });
    await assert.rejects(h.controller.request('/inventory/shelves'), ApiError);
    assert.equal(h.controller.getSnapshot().status, 'locked'); assertPrivateCleared(h.controller);
  });
}

test('denied action with unchanged access preserves the form workspace after revalidation', async () => {
  const h = harness(); await h.controller.restore(); const before = h.controller.getSnapshot();
  h.handle(call => {
    if (call.path === '/accounts/status') return status();
    throw new ApiError('This action is not permitted.', 403, 'permission_denied');
  });
  await assert.rejects(h.controller.request('/inventory/products'), /not permitted/);
  assert.equal(h.calls.at(-1)?.path, '/accounts/status');
  assert.equal(h.controller.getSnapshot(), before);
});

test('denied action with changed grants invalidates earlier responses after revalidation', async () => {
  const h = harness(); await h.controller.restore(); const before = h.controller.getSnapshot().revision;
  const pending = deferred<unknown>();
  h.handle(call => {
    if (call.path === '/heads-up') return pending.promise;
    if (call.path === '/accounts/status') {
      const next = status(); next.actor!.capabilities = []; next.stores![0]!.capabilities = []; return next;
    }
    throw new ApiError('Permission removed', 403, 'permission_denied');
  });
  const read = h.controller.request('/heads-up');
  await assert.rejects(h.controller.request('/inventory/shelves'), ApiError);
  assert.ok(h.controller.getSnapshot().revision > before);
  assert.deepEqual(h.controller.getSnapshot().actor?.capabilities, []);
  pending.resolve({ message: 'Old access' }); await assert.rejects(read, /session changed/);
});

for (const statusCode of [0, 401, 403]) {
  test(`denied action cannot preserve private state when revalidation fails (${statusCode})`, async () => {
    const h = harness(); await h.controller.restore();
    h.handle(call => {
      if (call.path === '/accounts/status') throw new ApiError('Unavailable', statusCode);
      throw new ApiError('Permission removed', 403, 'permission_denied');
    });
    await assert.rejects(h.controller.request('/inventory/shelves'), ApiError);
    assertPrivateCleared(h.controller);
    assert.equal(h.controller.getSnapshot().status, statusCode === 401 ? 'signedOut' : 'locked');
  });
}
