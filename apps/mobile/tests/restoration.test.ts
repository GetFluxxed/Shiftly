/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import type { Actor, Store } from '../src/api/types';
import { WorkspaceController } from '../src/restoration/controller';
import { savedRoute, workspaceScope } from '../src/restoration/policy';
import type { CheckpointStorage } from '../src/restoration/storage';
import type { Snapshot } from '../src/session/controller';

const UUID_A = '11111111-1111-4111-8111-111111111111';
const UUID_B = '22222222-2222-4222-8222-222222222222';
const NOW = 2_000_000_000_000;

function actor(overrides: Partial<Actor> = {}): Actor {
  return {
    userId: 17,
    username: 'crew.one',
    displayName: 'Crew One',
    storeId: 23,
    businessId: 5,
    role: 'crew',
    capabilities: ['inventory.view', 'reports.submit'],
    provenance: 'named',
    ...overrides,
  };
}

function ready(person = actor(), stores?: Store[]): Snapshot {
  return {
    status: 'ready',
    actor: person,
    stores: stores ?? [{ ...person, storeName: 'Downtown' }],
    message: null,
    busy: false,
    revision: 1,
  };
}

const locked: Snapshot = { status: 'locked', actor: null, stores: [], message: null, busy: false, revision: 2 };
const signedOut: Snapshot = { ...locked, status: 'signedOut', revision: 3 };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

class MemoryStorage implements CheckpointStorage {
  value: string | null = null;
  failRead = false;
  failWrite = false;
  failRemove = false;
  readGate: Promise<void> | null = null;
  writeGate: Promise<void> | null = null;
  calls: string[] = [];

  async read() {
    this.calls.push('read');
    if (this.readGate) await this.readGate;
    if (this.failRead) throw new Error('private device detail');
    return this.value;
  }

  async write(value: string) {
    this.calls.push('write:start');
    if (this.writeGate) await this.writeGate;
    if (this.failWrite) throw new Error('private device detail');
    this.value = value;
    this.calls.push('write:end');
  }

  async remove() {
    this.calls.push('remove');
    if (this.failRemove) throw new Error('private device detail');
    this.value = null;
  }
}

async function tick() {
  await new Promise<void>(resolve => setImmediate(resolve));
}

async function open(controller: WorkspaceController, snapshot = ready()) {
  controller.accept(snapshot);
  await tick();
  assert.equal(controller.getSnapshot().ready, true);
}

test('warm lock hides state, retry restores it, and a cold controller restores the same scope', async () => {
  const storage = new MemoryStorage();
  const first = new WorkspaceController(storage, () => NOW);
  await open(first);
  const scope = first.getSnapshot().scope;
  first.write('report.notes', 'handoff', 'report-4', scope);
  assert.equal(await first.flush(), true);

  first.accept(locked);
  assert.equal(first.getSnapshot().ready, false);
  assert.equal(first.read('report.notes', '', 'report-4'), '');
  await open(first);
  assert.equal(first.read('report.notes', '', 'report-4'), 'handoff');

  const restarted = new WorkspaceController(storage, () => NOW);
  await open(restarted);
  assert.equal(restarted.getSnapshot().scope, scope);
  assert.equal(restarted.read('report.notes', '', 'report-4'), 'handoff');
});

test('the ready gate rejects reads and writes until hydration completes and enforces scope', async () => {
  const storage = new MemoryStorage();
  const gate = deferred<void>(); storage.readGate = gate.promise;
  const controller = new WorkspaceController(storage, () => NOW);
  const session = ready();
  controller.accept(session);
  assert.equal(controller.getSnapshot().ready, false);
  controller.write('draft', 'hidden', '', workspaceScope(session.actor!, session.stores));
  assert.equal(controller.read('draft', 'initial'), 'initial');
  gate.resolve(); await tick();
  controller.write('draft', 'wrong scope', '', 'someone else');
  assert.equal(controller.read('draft', 'initial'), 'initial');
});

test('sign-out clears memory and the saved checkpoint', async () => {
  const storage = new MemoryStorage();
  const controller = new WorkspaceController(storage, () => NOW);
  await open(controller);
  controller.write('draft', 'private', '', controller.getSnapshot().scope);
  await controller.flush();
  controller.accept(signedOut); await tick();
  assert.equal(controller.getSnapshot().ready, false);
  assert.equal(controller.getSnapshot().scope, null);
  assert.equal(controller.read('draft', 'empty'), 'empty');
  assert.equal(storage.value, null);
});

test('user, store, role, and capability changes each discard the previous workspace', async () => {
  const changes: Partial<Actor>[] = [
    { userId: 18 }, { storeId: 24 }, { role: 'manager' },
    { capabilities: ['inventory.view', 'reports.submit', 'reports.view'] },
  ];
  for (const change of changes) {
    const storage = new MemoryStorage();
    const controller = new WorkspaceController(storage, () => NOW);
    await open(controller);
    controller.write('draft', 'old account', '', controller.getSnapshot().scope);
    await controller.flush();
    await open(controller, ready(actor(change)));
    assert.equal(controller.read('draft', 'empty'), 'empty');
  }
});

test('expired, corrupt, and wrong-shaped local data never restores form state', async () => {
  const session = ready();
  const scope = workspaceScope(session.actor!, session.stores);
  const documents = [
    JSON.stringify({ version: 1, scope, at: NOW - 7 * 24 * 60 * 60 * 1000, route: null,
      entries: { draft: { value: 'expired', baseline: '', at: NOW } } }),
    '{bad json',
    JSON.stringify({ version: 1, scope, at: NOW, route: null,
      entries: { draft: { value: { count: 'not a number', nested: true }, baseline: '', at: NOW } } }),
  ];
  for (const value of documents) {
    const storage = new MemoryStorage(); storage.value = value;
    const controller = new WorkspaceController(storage, () => NOW);
    await open(controller, session);
    assert.deepEqual(controller.read('draft', { count: 0 }), { count: 0 });
  }
});

test('route restoration denies public, malformed, and role-limited pages and strips unsafe params', () => {
  const crew = actor();
  assert.equal(savedRoute('/sign-in', {}, crew), null);
  assert.equal(savedRoute('/activate', { token: 'secret' }, crew), null);
  assert.deepEqual(savedRoute('/counts/[countId]', {
    countId: UUID_A, token: 'secret', unexpected: 'discard me', returnTo: 'stock',
  }, crew),
    { pathname: `/counts/${UUID_A}`, params: { returnTo: 'stock' } });
  assert.equal(savedRoute('/counts/[countId]', { countId: 'not-a-uuid' }, crew), null);
  assert.equal(savedRoute('/owner/42', {}, crew), null);
  assert.equal(savedRoute('/team/42', {}, crew), null);
  assert.equal(savedRoute('/store', {}, crew), null);
  assert.equal(savedRoute(`/counts/${UUID_A}/line/${UUID_B}`, {}, actor({ capabilities: [] })), null);
  assert.deepEqual(savedRoute('/owner/42', {}, actor({ role: 'owner' })), { pathname: '/owner/42' });
  assert.deepEqual(savedRoute('/team/42', {}, actor({ role: 'manager' })), { pathname: '/team/42' });
});

test('production restoration follows view, submit, and recipe management capabilities', () => {
  const viewer = actor({ role: 'production', capabilities: ['production.view'] });
  assert.deepEqual(savedRoute('/production', {}, viewer), { pathname: '/production' });
  assert.deepEqual(savedRoute(`/production/recipes/${UUID_A}`, {}, viewer), { pathname: `/production/recipes/${UUID_A}` });
  assert.equal(savedRoute('/production/run', {}, viewer), null);
  assert.equal(savedRoute('/production/recipes/new', {}, viewer), null);
  assert.deepEqual(savedRoute('/production/run', {}, actor({ capabilities: ['production.view', 'production.submit'] })), { pathname: '/production/run' });
  assert.deepEqual(savedRoute('/production/recipes/new', {}, actor({ capabilities: ['production.view', 'recipes.manage'] })), { pathname: '/production/recipes/new' });
});

test('remembered production lists restore bounded plain ingredient and batch rows', async () => {
  const storage = new MemoryStorage(); const first = new WorkspaceController(storage, () => NOW);
  await open(first); const scope = first.getSnapshot().scope;
  const draft = { entries: [{ recipeId: UUID_A, revisionId: UUID_B, batches: 3 }], pending: true };
  first.write('production.run.draft', draft, '', scope); await first.flush();
  const restarted = new WorkspaceController(storage, () => NOW); await open(restarted);
  assert.deepEqual(restarted.read('production.run.draft', { entries: [], pending: false }), draft);
});

test('a hydration finishing after background lock cannot expose local data', async () => {
  const storage = new MemoryStorage();
  const session = ready();
  const scope = workspaceScope(session.actor!, session.stores);
  storage.value = JSON.stringify({ version: 1, scope, at: NOW, route: null,
    entries: { draft: { value: 'private', baseline: '', at: NOW } } });
  const gate = deferred<void>(); storage.readGate = gate.promise;
  const controller = new WorkspaceController(storage, () => NOW);
  controller.accept(session);
  controller.accept(locked);
  gate.resolve(); await tick();
  assert.equal(controller.getSnapshot().ready, false);
  assert.equal(controller.read('draft', 'empty'), 'empty');
});

test('storage write failure returns false, shows a safe message, and recovers on retry', async () => {
  const storage = new MemoryStorage();
  const controller = new WorkspaceController(storage, () => NOW);
  await open(controller);
  controller.write('draft', 'recover me', '', controller.getSnapshot().scope);
  storage.failWrite = true;
  assert.equal(await controller.flush(), false);
  assert.match(controller.getSnapshot().message || '', /could not be saved on this device/i);
  assert.equal((controller.getSnapshot().message || '').includes('private device detail'), false);
  storage.failWrite = false;
  assert.equal(await controller.flush(), true);
  assert.equal(controller.getSnapshot().message, null);
  assert.match(storage.value || '', /recover me/);
});

test('clear queues behind an in-flight write and removes its result', async () => {
  const storage = new MemoryStorage();
  const controller = new WorkspaceController(storage, () => NOW);
  await open(controller);
  controller.write('draft', 'pending', '', controller.getSnapshot().scope);
  const gate = deferred<void>(); storage.writeGate = gate.promise;
  const writing = controller.flush();
  await tick();
  controller.accept(signedOut);
  assert.equal(storage.calls.includes('remove'), false);
  storage.writeGate = null; gate.resolve();
  assert.equal(await writing, true);
  await tick();
  assert.deepEqual(storage.calls.slice(-2), ['write:end', 'remove']);
  assert.equal(storage.value, null);
  assert.equal(controller.getSnapshot().ready, false);
});


test('failed device cleanup cannot resurrect a signed-out draft in the same session', async () => {
  const storage = new MemoryStorage();
  const controller = new WorkspaceController(storage, () => NOW);
  await open(controller);
  controller.write('draft', 'discarded private notes', '', controller.getSnapshot().scope);
  await controller.flush();
  storage.failRemove = true;
  controller.accept(signedOut); await tick();
  assert.match(controller.getSnapshot().message || '', /cleanup/);
  await open(controller);
  assert.equal(controller.read('draft', 'empty'), 'empty');
  storage.failRemove = false;
  await controller.flush();
  assert.equal((storage.value || '').includes('discarded private notes'), false);
});
