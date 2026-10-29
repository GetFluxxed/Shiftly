import assert from 'node:assert/strict';
import test from 'node:test';
import type { Count, CountLine, Entry } from '../src/inventory/counts/api';
import { createOfflineCountStorage } from '../src/inventory/counts/offline/storage';
import type { CountOwner } from '../src/inventory/counts/offline/types';
import type { SecureKeyValue } from '../src/restoration/storage';

const owner: CountOwner = { userId: 1, businessId: 2, storeId: 7 };
const firstId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const lineId = '33333333-3333-4333-8333-333333333333';
const entry: Entry = { mode: 'total', amount: '2', unit: 'kg' };
const baseCount: Count = { id: firstId, storeId: 7, businessDate: '2026-10-22', state: 'draft', version: 1,
  startedAt: '2026-10-22T10:00:00Z', startedBy: 'owner', reviewedAt: null, reviewedBy: null, postedAt: null, postedBy: null,
  totalLines: 1, countedLines: 0, totalProducts: 1, countedProducts: 0 };
const line: CountLine = { id: lineId, productId: '44444444-4444-4444-8444-444444444444', shelfId: null, shelfName: 'Back',
  name: 'Flour', sku: '001', baseUnit: 'kg', containerAmount: '5', quantity: null, entry: null, version: 1, observedAt: null, observedBy: null };

function memoryKv(): SecureKeyValue & { values: Map<string, string> } {
  const values = new Map<string, string>();
  return { values, get: async key => values.get(key) ?? null, set: async (key, value) => { values.set(key, value); }, remove: async key => { values.delete(key); } };
}
async function settleCleanup() { for (let index = 0; index < 20; index += 1) await Promise.resolve(); }

test('preparing another clean count retires the previous active count', async () => {
  const kv = memoryKv(), storage = createOfflineCountStorage(kv, 'test');
  await storage.prepare(owner, baseCount, [line], 100);
  await storage.prepare(owner, { ...baseCount, id: secondId }, [line], 200);
  await settleCleanup();
  assert.equal(await storage.load(owner, firstId), null);
  assert.equal((await storage.loadActive(owner))?.count.id, secondId);
});

test('the storage boundary refuses to replace an active count with pending work', async () => {
  const storage = createOfflineCountStorage(memoryKv(), 'test');
  const stored = await storage.prepare(owner, baseCount, [line], 100);
  await storage.writeLine(owner, firstId, stored.storageGeneration, { ...stored.lines[0]!,
    desired: { entry, localRevision: 1, updatedAt: 200 } });
  await assert.rejects(storage.prepare(owner, { ...baseCount, id: secondId }, [line], 300), /Sync or resolve/);
  assert.equal((await storage.loadActive(owner))?.count.id, firstId);
  assert.equal((await storage.loadActive(owner))?.lines[0]?.desired?.localRevision, 1);
});

test('a failed new active-pointer commit preserves the previous active count', async () => {
  const kv = memoryKv(); let failActive = false;
  const storage = createOfflineCountStorage({ ...kv, set: async (key, value) => {
    if (failActive && key === 'test.1.2.7.active.manifest') throw new Error('pointer failed');
    kv.values.set(key, value);
  } }, 'test');
  await storage.prepare(owner, baseCount, [line], 100); failActive = true;
  await assert.rejects(storage.prepare(owner, { ...baseCount, id: secondId }, [line], 200), /pointer failed/);
  assert.equal((await storage.loadActive(owner))?.count.id, firstId);
  assert.notEqual(await storage.load(owner, firstId), null);
});
