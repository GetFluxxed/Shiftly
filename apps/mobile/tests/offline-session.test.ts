/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, type Transport } from '../src/api/client';
import type { AccountStatus, Actor, RequestOptions } from '../src/api/types';
import { SessionController, type CredentialStore } from '../src/session/controller';
import { OFFLINE_COUNT_PERMIT_MS, parseOfflineCountPermit, type OfflineCountPermit, type OfflineCountPermitStore } from '../src/session/offlinePermit';

const TOKEN = 'offline-token-'.padEnd(43, 'x');
const OTHER_TOKEN = 'other-token-'.padEnd(43, 'y');
const COUNT_ID = '123e4567-e89b-42d3-a456-426614174000';
const actor = (changes: Partial<Actor> = {}): Actor => ({ userId: 11, username: 'counter', displayName: 'Counter',
  storeId: 7, businessId: 3, role: 'crew', capabilities: ['inventory.view', 'counts.submit'], provenance: 'named', ...changes });
const account = (changes: Partial<Actor> = {}): AccountStatus => {
  const selected = actor(changes);
  return { authenticated: true, actor: selected, stores: [{ ...selected, storeName: 'Store 7' }] };
};
const permit = (changes: Partial<OfflineCountPermit> = {}): OfflineCountPermit => {
  const selected = actor();
  return { version: 1, token: TOKEN, actor: selected, stores: [{ ...selected, storeName: 'Store 7' }],
    countId: COUNT_ID, validatedAt: Date.now(), ...changes };
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function harness(savedPermit: OfflineCountPermit | null = null) {
  let token: string | null = TOKEN, saved = savedPermit;
  let handler: (path: string, options: RequestOptions, supplied?: string) => unknown | Promise<unknown> = path => path === '/accounts/status' ? account() : {};
  const credentials: CredentialStore = { read: async () => token, write: async value => { token = value; }, remove: async () => { token = null; } };
  const permits: OfflineCountPermitStore = { read: async () => saved, write: async value => { saved = structuredClone(value); }, remove: async () => { saved = null; } };
  const transport: Transport = { send: async <T>(path: string, options: RequestOptions = {}, supplied?: string) => await handler(path, options, supplied) as T };
  return { controller: new SessionController(transport, credentials, permits), permits,
    saved: () => saved, token: () => token, handle: (next: typeof handler) => { handler = next; } };
}

test('a prepared count permit supports a cold offline restore without exposing its token', async () => {
  const h = harness(permit());
  h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore();
  const snapshot = h.controller.getSnapshot();
  assert.equal(snapshot.status, 'offline');
  assert.equal(snapshot.offlineCountId, COUNT_ID);
  assert.equal(snapshot.actor?.storeId, 7);
  assert.equal(JSON.stringify(snapshot).includes(TOKEN), false);
  await assert.rejects(h.controller.request('/inventory/counts'), /session changed/i);
});

test('authorization records the latest successful account validation time and never extends it offline', async () => {
  const h = harness();
  const originalNow = Date.now;
  let now = 1_900_000_000_000;
  Date.now = () => now;
  try {
    await h.controller.restore();
    now += 60_000;
    await h.controller.authorizeOfflineCount(COUNT_ID);
    assert.equal(h.saved()?.validatedAt, now - 60_000);
    now += OFFLINE_COUNT_PERMIT_MS - 59_999;
    h.controller.lock(); h.handle(() => { throw new ApiError('No network'); });
    await h.controller.retry();
    assert.equal(h.controller.getSnapshot().status, 'locked');
    assert.equal(h.saved(), null);
  } finally { Date.now = originalNow; }
});

test('wrong-token, wrong-store, and removed-capability permits fail closed and are erased', async () => {
  const invalid = [
    permit({ token: OTHER_TOKEN }),
    permit({ actor: actor({ storeId: 8 }) }),
    permit({ actor: actor({ capabilities: ['inventory.view'] }) }),
  ];
  for (const saved of invalid) {
    const h = harness(saved); h.handle(() => { throw new ApiError('No network'); });
    await h.controller.restore();
    assert.equal(h.controller.getSnapshot().status, 'locked');
    assert.equal(h.controller.getSnapshot().actor, null);
    assert.equal(h.saved(), null);
  }
});

test('background lock hides an offline actor and foreground retry restores only the restricted count', async () => {
  const h = harness(permit()); h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore(); h.controller.lock();
  assert.equal(h.controller.getSnapshot().status, 'locked');
  assert.equal(h.controller.getSnapshot().actor, null);
  await h.controller.retry();
  assert.equal(h.controller.getSnapshot().status, 'offline');
  assert.equal(h.controller.getSnapshot().offlineCountId, COUNT_ID);
});

test('offline access revalidation is shared and returns to ready before sync continues', async () => {
  const h = harness(permit()); h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore();
  const status = deferred<AccountStatus>(); let calls = 0;
  h.handle(path => { if (path === '/accounts/status') { calls += 1; return status.promise; } return {}; });
  const first = h.controller.refreshAccess(), second = h.controller.refreshAccess();
  assert.equal(calls, 1);
  assert.equal(h.controller.getSnapshot().status, 'offline');
  status.resolve(account()); await Promise.all([first, second]);
  assert.equal(h.controller.getSnapshot().status, 'ready');
});

test('an offline permit expires during periodic revalidation and cannot keep the actor visible', async () => {
  const originalNow = Date.now; let now = 1_900_000_000_000;
  Date.now = () => now;
  try {
    const h = harness(permit({ validatedAt: now })); h.handle(() => { throw new ApiError('No network'); });
    await h.controller.restore(); assert.equal(h.controller.getSnapshot().status, 'offline');
    now += OFFLINE_COUNT_PERMIT_MS + 1;
    await h.controller.refreshAccess();
    assert.equal(h.controller.getSnapshot().status, 'locked');
    assert.equal(h.controller.getSnapshot().actor, null);
    assert.equal(h.saved(), null);
  } finally { Date.now = originalNow; }
});

test('a successful refresh renews only an unchanged grant; authorization failures revoke it', async () => {
  const h = harness(permit({ validatedAt: Date.now() - 10_000 }));
  await h.controller.restore();
  const renewed = h.saved()!.validatedAt;
  assert.ok(renewed > Date.now() - 10_000);
  h.handle(path => { if (path === '/accounts/status') return account(); throw new ApiError('Denied', 403, 'permission_denied'); });
  await assert.rejects(h.controller.request('/inventory/counts'), /Denied/);
  assert.equal(h.saved(), null);
});

test('sign-out removes the permit and a late offline status response cannot restore it', async () => {
  const h = harness(permit()); await h.controller.restore();
  let rejectStatus!: (error: Error) => void;
  const delayed = new Promise<never>((_resolve, reject) => { rejectStatus = reject; });
  h.handle(path => path === '/accounts/status' ? delayed : {});
  const refresh = h.controller.refreshAccess();
  await h.controller.signOut();
  rejectStatus(new ApiError('No network'));
  await refresh;
  assert.equal(h.controller.getSnapshot().status, 'signedOut');
  assert.equal(h.saved(), null);
  assert.equal(h.token(), null);
});

test('a permit write completed after sign-out cannot resurrect offline access', async () => {
  const h = harness(); await h.controller.restore();
  const started = deferred<void>(), finish = deferred<void>();
  let latePermit: OfflineCountPermit | null = null;
  h.permits.write = async value => { started.resolve(); await finish.promise; latePermit = structuredClone(value); };
  h.permits.remove = async () => { latePermit = null; };
  const authorizing = h.controller.authorizeOfflineCount(COUNT_ID);
  await started.promise;
  const signingOut = h.controller.signOut();
  assert.equal(h.controller.getSnapshot().status, 'signedOut');
  finish.resolve();
  await assert.rejects(authorizing, /session changed/i);
  await signingOut;
  assert.equal(latePermit, null);
  h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'signedOut');
});

test('a corrupt permit store fails closed and is erased', async () => {
  const h = harness();
  let removed = false;
  h.permits.read = async () => { throw new Error('corrupt encrypted payload'); };
  h.permits.remove = async () => { removed = true; };
  h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'locked');
  assert.equal(h.controller.getSnapshot().actor, null);
  assert.equal(removed, true);
});

const catalogActor = { role: 'manager', capabilities: ['inventory.view', 'catalog.manage'] };
function capturePermit(changes: Partial<OfflineCountPermit> = {}): OfflineCountPermit {
  const selected = actor(catalogActor);
  return permit({ actor: selected, stores: [{ ...selected, storeName: 'Store 7' }], countId: null, catalogCapture: true, ...changes });
}
test('catalog capture alone restores a restricted offline session without granting count or server access', async () => {
  const h = harness(capturePermit()); h.handle(() => { throw new ApiError('No network'); });
  await h.controller.restore();
  assert.equal(h.controller.getSnapshot().status, 'offline');
  assert.equal(h.controller.getSnapshot().offlineCatalogCapture, true);
  assert.equal(h.controller.getSnapshot().offlineCountId, null);
  assert.equal(h.controller.canCaptureScans(), true);
  await assert.rejects(h.controller.request('/inventory/products'), /session changed/i);
  await assert.rejects(h.controller.authorizeOfflineCount(COUNT_ID), /session changed/i);
  await assert.rejects(h.controller.authorizeOfflineCatalogCapture(), /session changed/i);
});
test('capture requires catalog management and count-only actors cannot gain it', async () => {
  const h = harness(); await h.controller.restore();
  assert.equal(h.controller.canCaptureScans(), false);
  await assert.rejects(h.controller.authorizeOfflineCatalogCapture(), /cannot use/i);
  assert.equal(h.saved(), null);
  for (const capabilities of [['inventory.view'], ['catalog.manage'], ['counts.submit','inventory.view']]) {
    const p = capturePermit(); p.actor.capabilities = capabilities;
    const denied = harness(p); denied.handle(() => { throw new ApiError('offline'); });
    await denied.controller.restore();
    assert.equal(denied.controller.getSnapshot().status, 'locked');
  }
});
test('capture cannot cross token, selected store or business and expires at the same 12-hour boundary', async () => {
  for (const p of [capturePermit({token:OTHER_TOKEN}), capturePermit({actor:actor({...catalogActor, storeId:8})}),
    capturePermit({actor:actor({...catalogActor, businessId:99})}), capturePermit({validatedAt:Date.now()-OFFLINE_COUNT_PERMIT_MS-1})]) {
    const h=harness(p);h.handle(()=>{throw new ApiError('offline');});await h.controller.restore();
    assert.equal(h.controller.getSnapshot().status,'locked');assert.equal(h.controller.canCaptureScans(),false);
  }
});
test('capture operations stop at expiry even before periodic refresh, and offline preparation never renews it',async()=>{
  const originalNow=Date.now;let now=1_900_000_000_000;Date.now=()=>now;
  try {
    const h=harness(capturePermit({validatedAt:now}));h.handle(()=>{throw new ApiError('offline');});await h.controller.restore();
    now+=OFFLINE_COUNT_PERMIT_MS+1;
    assert.equal(h.controller.canCaptureScans(),false);
    await assert.rejects(h.controller.authorizeOfflineCatalogCapture());
    assert.equal(h.saved()?.validatedAt,now-OFFLINE_COUNT_PERMIT_MS-1);
  }finally{Date.now=originalNow;}
});
test('parallel count and capture preparation preserves both grants',async()=>{
  const h=harness();h.handle(()=>account({capabilities:['inventory.view','counts.submit','catalog.manage']}));await h.controller.restore();
  await Promise.all([h.controller.authorizeOfflineCount(COUNT_ID),h.controller.authorizeOfflineCatalogCapture()]);
  assert.equal(h.saved()?.countId,COUNT_ID);assert.equal(h.saved()?.catalogCapture,true);
  h.handle(()=>{throw new ApiError('offline');});await h.controller.refreshAccess();
  assert.equal(h.controller.getSnapshot().offlineCountId,COUNT_ID);assert.equal(h.controller.getSnapshot().offlineCatalogCapture,true);
});
test('changed catalog grants and 401 revoke offline capture; failed writes never enable it',async()=>{
  const h=harness(capturePermit());h.handle(()=>account());await h.controller.restore();assert.equal(h.saved(),null);
  assert.equal(h.controller.canCaptureScans(),false);
  const revoked=harness(capturePermit());revoked.handle(()=>{throw new ApiError('expired',401);});await revoked.controller.restore();
  assert.equal(revoked.controller.getSnapshot().status,'signedOut');assert.equal(revoked.saved(),null);
  const failure=harness();failure.handle(()=>account(catalogActor));await failure.controller.restore();
  failure.permits.write=async()=>{throw new Error('disk full');};
  await assert.rejects(failure.controller.authorizeOfflineCatalogCapture(),/disk full/);
  assert.notEqual(failure.controller.getSnapshot().offlineCatalogCapture,true);
});
test('delayed capture permission cannot survive sign out',async()=>{
  const h=harness();h.handle(()=>account(catalogActor));await h.controller.restore();
  const started=deferred<void>(),finish=deferred<void>();let late:OfflineCountPermit|null=null;
  h.permits.write=async value=>{started.resolve();await finish.promise;late=value;};h.permits.remove=async()=>{late=null;};
  const enabling=h.controller.authorizeOfflineCatalogCapture();await started.promise;
  const ending=h.controller.signOut();finish.resolve();await assert.rejects(enabling,/session changed/i);await ending;
  assert.equal(late,null);assert.equal(h.controller.canCaptureScans(),false);
});

test('permit parser accepts legacy count, capture, and dual grants but rejects inconsistent individual grants', () => {
  const dual = capturePermit(); dual.countId=COUNT_ID; dual.actor.capabilities = [...dual.actor.capabilities, 'counts.submit'];
  for (const p of [permit(),capturePermit(),dual]) assert.deepEqual(parseOfflineCountPermit(JSON.stringify(p)),p);
  const invalid = [permit({catalogCapture:true}), capturePermit({countId:COUNT_ID}), permit({countId:null}),
    capturePermit({catalogCapture:false}), capturePermit({catalogCapture:'true' as unknown as boolean}),
    capturePermit({actor:actor({...catalogActor,userId:22})}), capturePermit({actor:actor({...catalogActor,businessId:99})}),
    capturePermit({actor:actor({...catalogActor,storeId:8})})];
  for(const p of invalid)assert.throws(()=>parseOfflineCountPermit(JSON.stringify(p)));
});
test('online local capture uses verified catalog permissions but does not imply offline preparation',async()=>{
 const h=harness();h.handle(()=>account(catalogActor));await h.controller.restore();
 assert.equal(h.controller.canCaptureScans(),true);assert.notEqual(h.controller.getSnapshot().offlineCatalogCapture,true);
 h.handle(()=>{throw new ApiError('offline');});await h.controller.refreshAccess();
 assert.equal(h.controller.getSnapshot().status,'locked');assert.equal(h.controller.canCaptureScans(),false);
});

test('access refresh queued behind preparing capture preserves both offline workflows',async()=>{
  const full={capabilities:['inventory.view','counts.submit','catalog.manage']};
  const h=harness();h.handle(()=>account(full));await h.controller.restore();await h.controller.authorizeOfflineCount(COUNT_ID);
  const started=deferred<void>(),finish=deferred<void>();const write=h.permits.write;let first=true;
  h.permits.write=async p=>{if(first){first=false;started.resolve();await finish.promise;}await write(p);};
  const adding=h.controller.authorizeOfflineCatalogCapture();await started.promise;
  const refreshing=h.controller.refreshAccess();finish.resolve();await Promise.all([adding,refreshing]);
  assert.equal(h.saved()?.catalogCapture,true);assert.equal(h.saved()?.countId,COUNT_ID);
});
