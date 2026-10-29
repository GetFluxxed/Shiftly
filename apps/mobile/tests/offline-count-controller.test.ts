import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError } from '../src/api/client';
import { countsApi, type Count, type CountLine, type Entry } from '../src/inventory/counts/api';
import { OfflineCountController } from '../src/inventory/counts/offline/controller';
import { createOfflineCountStorage } from '../src/inventory/counts/offline/storage';
import type { CountOwner, OfflineCountStorage } from '../src/inventory/counts/offline/types';
import type { SecureKeyValue } from '../src/restoration/storage';

const countId = '11111111-1111-4111-8111-111111111111';
const lineId = '22222222-2222-4222-8222-222222222222';
const requestId = '33333333-3333-4333-8333-333333333333';
const owner: CountOwner = { userId: 1, businessId: 2, storeId: 7 };
const count: Count = { id: countId, storeId: 7, businessDate: '2026-10-22', state: 'draft', version: 1,
  startedAt: '2026-10-22T10:00:00Z', startedBy: 'owner', reviewedAt: null, reviewedBy: null, postedAt: null, postedBy: null,
  totalLines: 1, countedLines: 0, totalProducts: 1, countedProducts: 0 };
const line: CountLine = { id: lineId, productId: '44444444-4444-4444-8444-444444444444', shelfId: null, shelfName: 'Back',
  name: 'Flour', sku: '001', baseUnit: 'kg', containerAmount: '5', quantity: null, entry: null, version: 1, observedAt: null, observedBy: null };
const entry: Entry = { mode: 'total', amount: '2', unit: 'kg' };

function memoryKv(): SecureKeyValue & { values: Map<string, string> } {
  const values = new Map<string, string>();
  return { values, get: async key => values.get(key) ?? null, set: async (key, value) => { values.set(key, value); }, remove: async key => { values.delete(key); } };
}
function runtime(api = countsApi(async () => { throw new Error('unexpected request'); })) {
  let status = 'ready'; let activeOwner: CountOwner | null = owner;
  return { value: { context: () => ({ status, owner: activeOwner }), api, revalidate: async () => {}, authorizeOffline: async () => {} },
    online: () => { status = 'ready'; }, offline: () => { status = 'offline'; }, owner: (value: CountOwner | null) => { activeOwner = value; } };
}
async function prepared(storage: OfflineCountStorage) { await storage.prepare(owner, count, [line], 100); }

test('a local save is not reported when its durable line write fails', async () => {
  const base = createOfflineCountStorage(memoryKv(), 'test'); await prepared(base);
  const failing: OfflineCountStorage = { ...base, writeLine: async () => { throw new Error('disk full'); } };
  const env = runtime(), controller = new OfflineCountController(failing, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId);
  await assert.rejects(controller.save(line, entry), /disk full/);
  assert.equal(controller.getSnapshot().lines[0]?.entry, null);
  assert.deepEqual(controller.getSnapshot().pendingLineIds, []);
});

test('pending entries survive a cold controller restore', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const env = runtime();
  const first = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  first.activate(owner); await first.open(countId); await first.save(line, entry);
  const second = new OfflineCountController(storage, env.value);
  second.activate(owner); await second.open(countId);
  assert.equal(second.getSnapshot().lines[0]?.quantity, '2');
  assert.deepEqual(second.getSnapshot().pendingLineIds, [lineId]);
});

test('a pending cached draft renews its offline authorization after restore', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const firstEnv = runtime(), first = new OfflineCountController(storage, firstEnv.value);
  first.activate(owner); await first.open(countId); await first.save(line, entry);
  let authorizations = 0;
  const nextEnv = runtime();
  const restored = new OfflineCountController(storage, { ...nextEnv.value, authorizeOffline: async id => {
    assert.equal(id, countId); authorizations += 1;
  } });
  restored.activate(owner); await restored.restore();
  assert.equal(authorizations, 1);
  assert.deepEqual(restored.getSnapshot().pendingLineIds, [lineId]);
});

test('an authorized offline context can save locally without a network-ready status', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const env = runtime(), controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId); env.offline();
  await controller.save(line, entry);
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '2');
});

test('simultaneous saves serialize revisions and the latest value survives a cold restore', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const env = runtime(), controller = new OfflineCountController(storage, env.value, (() => { let time = 200; return () => time++; })());
  controller.activate(owner); await controller.open(countId); env.offline();
  await Promise.all([controller.save(line, entry), controller.save(line, { mode: 'total', amount: '3', unit: 'kg' })]);
  const restored = new OfflineCountController(storage, env.value); restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().lines[0]?.quantity, '3');
});

test('restore finds the active prepared count and another count cannot displace pending work', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const env = runtime();
  const first = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  first.activate(owner); await first.open(countId); await first.save(line, entry);
  const restored = new OfflineCountController(storage, env.value);
  restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().count?.id, countId);
  await assert.rejects(restored.open('66666666-6666-4666-8666-666666666666'), /Sync or resolve/);
  assert.equal(restored.getSnapshot().count?.id, countId);
  assert.deepEqual(restored.getSnapshot().pendingLineIds, [lineId]);
});

test('a direct open deterministically wins when restore is still loading', async () => {
  const base = createOfflineCountStorage(memoryKv(), 'test'); await prepared(base);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; }); let first = true;
  const delayed: OfflineCountStorage = { ...base, loadActive: async activeOwner => {
    if (first) { first = false; began(); await gate; }
    return base.loadActive(activeOwner);
  } };
  const env = runtime(), controller = new OfflineCountController(delayed, env.value);
  controller.activate(owner); const restoring = controller.restore(); await started;
  const opening = controller.open(countId); release(); await Promise.all([restoring, opening]);
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().count?.id, countId);
});

test('a scope change clears an old same-id open flight', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; }); let details = 0;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => {
    details += 1; if (details === 1) { began(); await gate; } return count;
  }, lines: async () => ({ items: [line], nextCursor: null }) };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); const oldOpen = controller.open(countId); await started;
  const nextOwner = { ...owner, userId: 9, businessId: 10 }; controller.activate(nextOwner); env.owner(nextOwner);
  const newOpen = controller.open(countId); await newOpen; release(); await oldOpen;
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().count?.id, countId);
  assert.ok(details >= 3);
});

test('a scope change clears an old sync flight so the new queue can drain', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test');
  const nextOwner = { ...owner, userId: 9, businessId: 10 };
  for (const itemOwner of [owner, nextOwner]) {
    await storage.prepare(itemOwner, count, [line], 100);
    const stored = (await storage.loadActive(itemOwner))!;
    await storage.writeLine(itemOwner, countId, stored.storageGeneration, { ...stored.lines[0]!,
      desired: { entry, localRevision: 1, updatedAt: 200 } });
  }
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; }); let saves = 0;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count,
    savePersisted: async () => { saves += 1; if (saves === 1) { began(); await gate; } return {
      line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } }; } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.restore(); const oldSync = controller.sync(); await started;
  controller.activate(nextOwner); env.owner(nextOwner); await controller.restore(); await controller.sync();
  assert.equal(saves, 2); assert.deepEqual(controller.getSnapshot().pendingLineIds, []);
  release(); await oldSync;
  assert.equal(controller.getSnapshot().count?.id, countId);
});

test('an interrupted replacement leaves the previously committed generation readable', async () => {
  const kv = memoryKv(), storage = createOfflineCountStorage(kv, 'test'); await prepared(storage);
  let fail = true;
  const interrupted = createOfflineCountStorage({ ...kv, set: async (key, value) => {
    if (fail && key.includes('.line.') && key.endsWith('.manifest')) { fail = false; throw new Error('interrupted'); }
    kv.values.set(key, value);
  } }, 'test');
  await assert.rejects(interrupted.prepare(owner, count, [{ ...line, shelfName: 'Changed' }], 300), /interrupted/);
  const restored = await storage.loadActive(owner);
  assert.equal(restored?.lines[0]?.canonical.shelfName, 'Back');
  assert.equal(restored?.preparedAt, 100);
});

test('an unchanged online count renews access without rewriting line generations', async () => {
  const kv = memoryKv(); let lineWrites = 0;
  const storage = createOfflineCountStorage({ ...kv, set: async (key, value) => {
    if (key.includes('.line.')) lineWrites += 1;
    kv.values.set(key, value);
  } }, 'test');
  await prepared(storage); lineWrites = 0;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId);
  assert.equal(lineWrites, 0);
  assert.equal(controller.getSnapshot().count?.id, countId);
});

test('an uncertain response replays the identical persisted request', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const calls: unknown[][] = []; let fail = true;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async (...args: Parameters<ReturnType<typeof countsApi>['savePersisted']>) => {
    calls.push(args); if (fail) { fail = false; throw new ApiError('response lost'); }
    return { line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } };
  } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry); env.online();
  await controller.sync(); await controller.sync();
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], calls[1]);
  assert.deepEqual(controller.getSnapshot().pendingLineIds, []);
});

test('a newer edit made during upload remains queued for the next version', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; });
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async () => {
    began(); await gate; return { line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } };
  } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry); env.online();
  const syncing = controller.sync();
  await started;
  await controller.save(line, { mode: 'total', amount: '3', unit: 'kg' });
  release(); await syncing;
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '3');
  assert.deepEqual(controller.getSnapshot().pendingLineIds, [lineId]);
});

test('a save queued during attempt persistence remains the durable latest intent', async () => {
  const base = createOfflineCountStorage(memoryKv(), 'test'); await prepared(base);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; }); let delayed = false;
  const storage: OfflineCountStorage = { ...base, writeLine: async (...args) => {
    const record = args[3];
    if (!delayed && record.attempt && record.canonical.version === 1) { delayed = true; began(); await gate; }
    return base.writeLine(...args);
  } };
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async () => ({
    line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } }) };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  const syncing = controller.sync(); await started;
  const saving = controller.save(line, { mode: 'total', amount: '3', unit: 'kg' }); release();
  await Promise.all([syncing, saving]); env.offline();
  const restored = new OfflineCountController(base, env.value); restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().lines[0]?.quantity, '3');
  assert.deepEqual(restored.getSnapshot().pendingLineIds, [lineId]);
});

test('a save queued during acknowledgement persistence survives the ack', async () => {
  const base = createOfflineCountStorage(memoryKv(), 'test'); await prepared(base);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; }); let delayed = false;
  const storage: OfflineCountStorage = { ...base, writeLine: async (...args) => {
    const record = args[3];
    if (!delayed && !record.attempt && record.canonical.version === 2) { delayed = true; began(); await gate; }
    return base.writeLine(...args);
  } };
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async () => ({
    line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } }) };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  const syncing = controller.sync(); await started;
  const saving = controller.save(line, { mode: 'total', amount: '3', unit: 'kg' }); release();
  await Promise.all([syncing, saving]); env.offline();
  const restored = new OfflineCountController(base, env.value); restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().lines[0]?.quantity, '3');
  assert.deepEqual(restored.getSnapshot().pendingLineIds, [lineId]);
});

test('a stale record becomes an explicit conflict and preserves the entry', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async () => { throw new ApiError('Another counter saved this line.', 409, 'stale_record'); } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry); env.online(); await controller.sync();
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '2');
  assert.equal(controller.getSnapshot().conflicts[lineId], 'Another counter saved this line.');
});

test('conflict resolution cannot discard an edit made during its remote read', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; });
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count,
    line: async () => { began(); await gate; return { ...line, entry, quantity: '2', version: 2 }; } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  const resolving = controller.resolve(lineId, 'server'); await started;
  await controller.save(line, { mode: 'total', amount: '3', unit: 'kg' }); release();
  await assert.rejects(resolving, /local entry changed/);
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '3');
});

test('a delayed response cannot expose or mutate another active scope', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  let release!: () => void, began!: () => void; const gate = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { began = resolve; });
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => count, savePersisted: async () => { began(); await gate; return {
    line: { ...line, entry, quantity: '2', version: 2 }, count: { ...count, countedLines: 1, countedProducts: 1 } }; } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry); env.online();
  const syncing = controller.sync(); await started; controller.activate({ ...owner, storeId: 8 }); env.owner({ ...owner, storeId: 8 }); release(); await syncing;
  assert.equal(controller.getSnapshot().count, null);
  const restored = await storage.load(owner, countId);
  assert.equal(restored?.lines[0]?.attempt?.requestId, requestId);
});

test('online preparation follows every page and rejects an incomplete snapshot', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test');
  let details = 0, pages = 0;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }),
    detail: async () => { details += 1; return count; },
    lines: async (_id: string, _q = '', after = '') => { pages += 1; return after
      ? { items: [], nextCursor: null } : { items: [], nextCursor: '55555555-5555-4555-8555-555555555555' }; } };
  const env = runtime(api); env.online();
  const controller = new OfflineCountController(storage, env.value);
  controller.activate(owner);
  await assert.rejects(controller.open(countId), /changed while it was being prepared/);
  assert.equal(details, 2); assert.equal(pages, 2);
  assert.equal(await storage.load(owner, countId), null);
});

test('online preparation commits all paginated lines before becoming available offline', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test');
  const second = { ...line, id: '77777777-7777-4777-8777-777777777777', shelfId: '88888888-8888-4888-8888-888888888888', shelfName: 'Front' };
  const complete = { ...count, totalLines: 2 };
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }), detail: async () => complete,
    lines: async (_id: string, _q = '', after = '') => after
      ? { items: [second], nextCursor: null } : { items: [line], nextCursor: '55555555-5555-4555-8555-555555555555' } };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 500);
  controller.activate(owner); await controller.open(countId); controller.activate(null); env.offline();
  const restored = new OfflineCountController(storage, env.value); restored.activate(owner); await restored.restore();
  assert.deepEqual(restored.getSnapshot().lines.map(item => item.id), [lineId, second.id]);
  assert.equal(restored.getSnapshot().preparedAt, 500);
});

test('replaying an acknowledged old operation does not reopen a remotely closed count', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test'); await prepared(storage);
  let lost = true;
  const closed: Count = { ...count, version: 4, state: 'review', countedLines: 1, countedProducts: 1 };
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }),
    detail: async () => lost ? count : closed,
    savePersisted: async () => {
      if (lost) { lost = false; throw new ApiError('response lost'); }
      return { line: { ...line, entry, quantity: '2', version: 2 },
        count: { ...count, version: 2, countedLines: 1, countedProducts: 1 } };
    },
  };
  const env = runtime(api), controller = new OfflineCountController(storage, env.value, () => 200, () => requestId);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  await controller.sync(); await controller.sync();
  assert.equal(controller.getSnapshot().count?.state, 'review');
  assert.equal(controller.getSnapshot().count?.version, 4);
  assert.deepEqual(controller.getSnapshot().pendingLineIds, []);
  await assert.rejects(controller.save(line, entry), /not available for editing/);
});

const extraLine: CountLine = { ...line, id: '55555555-5555-4555-8555-555555555555',
  productId: '66666666-6666-4666-8666-666666666666', name: 'Sugar', shelfId: null, shelfName: 'Unassigned' };

function catalogRuntime() {
  let expanded = false, saved = false, failDownload = false;
  let includes = 0, uploads = 0;
  const remoteCount = (): Count => ({ ...count, version: saved ? 3 : expanded ? 2 : 1,
    totalLines: expanded ? 2 : 1, totalProducts: expanded ? 2 : 1,
    countedLines: saved ? 1 : 0, countedProducts: saved ? 1 : 0,
    configurationChanged: !expanded, catalogProductsAvailable: !expanded });
  const savedLine = (): CountLine => saved
    ? { ...line, entry, quantity: '2', version: 2, observedAt: '2026-10-22T11:00:00Z', observedBy: 'owner' } : line;
  const api = { ...countsApi(async () => { throw new Error('unexpected'); }),
    detail: async () => remoteCount(),
    includeCatalog: async (item: Count) => { assert.equal(item.id, countId); includes++; expanded = true; return remoteCount(); },
    savePersisted: async (_id: string, current: CountLine, desired: Entry) => {
      assert.equal(current.id, lineId); assert.equal(current.version, 1); assert.deepEqual(desired, entry);
      uploads++; saved = true; return { line: savedLine(), count: remoteCount() };
    },
    lines: async () => {
      if (failDownload) throw new ApiError('Connection lost');
      return { items: expanded ? [savedLine(), extraLine] : [savedLine()], nextCursor: null };
    },
  };
  const env = runtime(api);
  return { ...env, value: { ...env.value, canIncludeCatalog: () => true },
    failDownload: (value: boolean) => { failDownload = value; }, includes: () => includes, uploads: () => uploads };
}

test('opening a clean old snapshot appends active catalog items without rewriting counted lines', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime(); const controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId);
  assert.equal(env.includes(), 1);
  assert.equal(controller.getSnapshot().lines.length, 2);
  assert.equal(controller.getSnapshot().lines[0]?.id, lineId);
  assert.equal(controller.getSnapshot().lines[1]?.entry, null);
  assert.equal(controller.getSnapshot().count?.configurationChanged, false);
});

test('catalog expansion syncs queued entries then prepares new uncounted lines', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime(); env.offline();
  const controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  env.online(); await controller.sync();
  assert.equal(env.includes(), 1); assert.equal(env.uploads(), 1);
  assert.deepEqual(controller.getSnapshot().pendingLineIds, []);
  assert.equal(controller.getSnapshot().count?.totalProducts, 2);
  assert.equal(controller.getSnapshot().count?.countedProducts, 1);
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '2');
  assert.equal(controller.getSnapshot().lines[1]?.quantity, null);
});

test('lost connection after catalog expansion preserves old entries on cold restore until the new lines download', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime(); env.offline();
  const controller = new OfflineCountController(storage, env.value);
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  env.online(); env.failDownload(true); await controller.sync();
  assert.equal(controller.getSnapshot().count?.totalLines, 2);
  assert.equal(controller.getSnapshot().lines.length, 1);
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '2');
  env.offline();
  const restored = new OfflineCountController(storage, env.value);
  restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().status, 'ready');
  assert.equal(restored.getSnapshot().count?.totalLines, 2);
  assert.equal(restored.getSnapshot().lines[0]?.quantity, '2');
  env.online(); env.failDownload(false); await restored.sync();
  assert.equal(restored.getSnapshot().lines.length, 2);
  assert.equal(env.uploads(), 1);
  assert.equal(env.includes(), 1);
});

test('view-only count readers never append catalog products', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime();
  const controller = new OfflineCountController(storage, { ...env.value, canIncludeCatalog: () => false });
  controller.activate(owner); await controller.open(countId);
  assert.equal(env.includes(), 0);
  assert.equal(controller.getSnapshot().lines.length, 1);
});

test('an uncertain catalog append can be recovered without duplicating queued observations', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime(); env.offline();
  const api = { ...env.value.api, includeCatalog: async (item: Count, id: string) => {
    await env.value.api.includeCatalog(item, id);
    throw new ApiError('Connection lost');
  } };
  const first = new OfflineCountController(storage, { ...env.value, api });
  first.activate(owner); await first.open(countId); await first.save(line, entry);
  env.online(); await first.sync();
  assert.deepEqual(first.getSnapshot().pendingLineIds, [lineId]);
  assert.equal(first.getSnapshot().lines[0]?.quantity, '2');
  const restored = new OfflineCountController(storage, env.value);
  restored.activate(owner); await restored.restore(); await restored.sync();
  assert.equal(env.includes(), 1); assert.equal(env.uploads(), 1);
  assert.equal(restored.getSnapshot().lines.length, 2);
  assert.deepEqual(restored.getSnapshot().pendingLineIds, []);
});

test('a new local edit during an expanded-list download survives instead of being replaced', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime(); env.offline();
  let release!: () => void, started!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  const downloading = new Promise<void>(resolve => { started = resolve; });
  const api = { ...env.value.api, lines: async () => { started(); await gate; return env.value.api.lines(countId); } };
  const controller = new OfflineCountController(storage, { ...env.value, api });
  controller.activate(owner); await controller.open(countId); await controller.save(line, entry);
  env.online(); const sync = controller.sync(); await downloading;
  await controller.save(controller.getSnapshot().lines[0]!, { mode: 'total', amount: '3', unit: 'kg' });
  release(); await sync;
  assert.equal(controller.getSnapshot().lines[0]?.quantity, '3');
  assert.deepEqual(controller.getSnapshot().pendingLineIds, [lineId]);
  env.offline(); const restored = new OfflineCountController(storage, env.value);
  restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().lines[0]?.quantity, '3');
  assert.deepEqual(restored.getSnapshot().pendingLineIds, [lineId]);
});


test('an uncertain append on a clean count persists a retry marker across offline restore', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'catalog'); await prepared(storage);
  const env = catalogRuntime();
  const api = { ...env.value.api, includeCatalog: async (item: Count, id: string) => {
    await env.value.api.includeCatalog(item, id);
    throw new ApiError('Connection lost');
  } };
  const first = new OfflineCountController(storage, { ...env.value, api });
  first.activate(owner); await first.open(countId);
  assert.equal(first.getSnapshot().count?.catalogProductsAvailable, true);
  env.offline(); const restored = new OfflineCountController(storage, env.value);
  restored.activate(owner); await restored.restore();
  assert.equal(restored.getSnapshot().count?.catalogProductsAvailable, true);
  env.online(); await restored.sync();
  assert.equal(env.includes(), 1);
  assert.equal(restored.getSnapshot().lines.length, 2);
  assert.equal(restored.getSnapshot().count?.catalogProductsAvailable, false);
});
