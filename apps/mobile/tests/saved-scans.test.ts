/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { SavedScansController } from '../src/inventory/scans/controller';
import { MAX_SAVED_SCANS, parseScanInput, type ScanInput, type ScanOwner } from '../src/inventory/scans/model';
import type { CheckpointStorage } from '../src/restoration/storage';

const OWNER: ScanOwner = { userId: 7, businessId: 11, storeId: 13 };
const OTHER: ScanOwner = { userId: 7, businessId: 11, storeId: 14 };

function input(code = '000123', overrides: Partial<ScanInput> = {}): ScanInput {
  return { code, barcodeType: 'org.gs1.EAN-13', name: '', baseUnit: 'each', containerAmount: '', containerUnit: 'each', ...overrides };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

class MemoryStorage implements CheckpointStorage {
  value: string | null = null;
  readGate: Promise<void> | null = null;
  writeGates: Promise<void>[] = [];
  failWrite = false;
  writes = 0;
  activeWrites = 0;
  maxActiveWrites = 0;

  async read() { if (this.readGate) await this.readGate; return this.value; }
  async write(value: string) {
    const call = this.writes++;
    this.activeWrites += 1;
    this.maxActiveWrites = Math.max(this.maxActiveWrites, this.activeWrites);
    try {
      if (this.writeGates[call]) await this.writeGates[call];
      if (this.failWrite) throw new Error('device detail');
      this.value = value;
    } finally { this.activeWrites -= 1; }
  }
  async remove() { this.value = null; }
}

function fixture() {
  const stores = new Map<string, MemoryStorage>();
  const key = (owner: ScanOwner) => `${owner.userId}.${owner.businessId}.${owner.storeId}`;
  const factory = (owner: ScanOwner) => {
    const ownerKey = key(owner);
    let storage = stores.get(ownerKey);
    if (!storage) { storage = new MemoryStorage(); stores.set(ownerKey, storage); }
    return storage;
  };
  return { stores, factory, storage: factory(OWNER) };
}

async function ready(controller: SavedScansController, owner = OWNER) {
  await controller.activate(owner);
  assert.equal(controller.getSnapshot().status, 'ready');
}

test('saved scans survive controller restart in their exact owner partition', async () => {
  const { factory } = fixture();
  const first = new SavedScansController(factory, () => true);
  await ready(first);
  const saved = await first.save(input('000001', { name: 'Case', containerAmount: '12' }));
  const restarted = new SavedScansController(factory, () => true);
  await ready(restarted);
  assert.deepEqual(restarted.getSnapshot().items, [saved]);
  await ready(restarted, OTHER);
  assert.deepEqual(restarted.getSnapshot().items, []);
});

test('dedupe preserves raw leading zeros and barcode type and does not erase captured detail', async () => {
  const { factory, storage } = fixture();
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const original = await controller.save(input(' 000123 ', { name: 'Original', containerAmount: '24' }));
  const duplicate = await controller.save(input('000123'));
  const otherType = await controller.save(input('000123', { barcodeType: 'code128' }));
  assert.deepEqual(duplicate, original);
  assert.equal(otherType.code, '000123');
  assert.notEqual(otherType.id, original.id);
  assert.equal(controller.getSnapshot().items[0]!.name, 'Original');
  assert.equal(storage.writes, 2);
});

test('strict input parser enforces bounds, decimal precision, positivity, and dimensions', () => {
  assert.equal(parseScanInput(input(' 0007 ')).code, '0007');
  assert.equal(parseScanInput(input('MANUAL-001', { barcodeType: '' })).barcodeType, '');
  assert.equal(parseScanInput(input('0008', { barcodeType: ' vendor.future.symbology ' })).barcodeType, 'vendor.future.symbology');
  assert.equal(parseScanInput(input('x', { baseUnit: 'kg', containerUnit: 'lb', containerAmount: '0.123456' })).containerAmount, '0.123456');
  for (const invalid of [
    input(' '), input('x'.repeat(65)), input('x', { barcodeType: 'x'.repeat(97) }), input('x', { name: 'x'.repeat(161) }),
    input('x', { containerAmount: '0' }), input('x', { containerAmount: '-1' }), input('x', { containerAmount: '1.2' }),
    input('x', { baseUnit: 'g', containerUnit: 'each' }), input('x', { baseUnit: 'each', containerUnit: 'kg' }),
    input('x', { baseUnit: 'kg', containerUnit: 'lb', containerAmount: '1.1234567' }),
    input('x', { baseUnit: 'kg', containerUnit: 'kg', containerAmount: '1234567890' }),
  ]) assert.throws(() => parseScanInput(invalid));
});

test('failed durable save leaves old data and the published list intact', async () => {
  const { factory, storage } = fixture();
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const first = await controller.save(input('1'));
  const committed = storage.value;
  storage.failWrite = true;
  await assert.rejects(controller.save(input('2')));
  assert.equal(storage.value, committed);
  assert.deepEqual(controller.getSnapshot().items, [first]);
  assert.equal(controller.getSnapshot().status, 'error');
});

test('queue limit rejects item 101 without evicting any unsent scan', async () => {
  const { factory, storage } = fixture();
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  for (let index = 0; index < MAX_SAVED_SCANS; index += 1) await controller.save(input(String(index + 1)));
  const committed = storage.value;
  await assert.rejects(controller.save(input('overflow')), /limited to 100/);
  assert.equal(controller.getSnapshot().items.length, MAX_SAVED_SCANS);
  assert.equal(storage.value, committed);
});

test('scope change during pending read never reveals the stale owner', async () => {
  const { factory, storage } = fixture();
  const gate = deferred<void>(); storage.readGate = gate.promise;
  const controller = new SavedScansController(factory, () => true);
  const pending = controller.activate(OWNER);
  await controller.activate(OTHER);
  gate.resolve(); await pending;
  assert.deepEqual(controller.getSnapshot(), { owner: OTHER, status: 'ready', items: [], error: null });
});

test('scope change during pending write may finish only in the old partition and cannot publish', async () => {
  const { factory, storage } = fixture();
  const gate = deferred<void>(); storage.writeGates.push(gate.promise);
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const pending = assert.rejects(controller.save(input('old')), /scope changed/);
  await new Promise<void>(resolve => setImmediate(resolve));
  await controller.activate(OTHER);
  gate.resolve();
  await pending;
  assert.deepEqual(controller.getSnapshot(), { owner: OTHER, status: 'ready', items: [], error: null });
  assert.match(storage.value ?? '', /old/);
});

test('reactivating an owner reads after its queued stale write completes', async () => {
  const { factory, storage } = fixture();
  const gate = deferred<void>(); storage.writeGates.push(gate.promise);
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const pendingSave = assert.rejects(controller.save(input('queued')));
  await new Promise<void>(resolve => setImmediate(resolve));
  controller.deactivate();
  const pendingActivation = controller.activate(OWNER);
  assert.equal(controller.getSnapshot().status, 'loading');
  gate.resolve();
  await pendingSave;
  await pendingActivation;
  assert.equal(controller.getSnapshot().items[0]!.code, 'queued');
});

test('parallel saves are serialized and both durable results are published', async () => {
  const { factory, storage } = fixture();
  const gate = deferred<void>(); storage.writeGates.push(gate.promise);
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const first = controller.save(input('1'));
  const second = controller.save(input('2'));
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(storage.writes, 1);
  gate.resolve();
  await Promise.all([first, second]);
  assert.equal(storage.maxActiveWrites, 1);
  assert.deepEqual(controller.getSnapshot().items.map(item => item.code), ['1', '2']);
});

test('editing rejects a barcode collision and removal commits before publishing', async () => {
  const { factory, storage } = fixture();
  const controller = new SavedScansController(factory, () => true);
  await ready(controller);
  const first = await controller.save(input('1'));
  const second = await controller.save(input('2'));
  await assert.rejects(controller.save(input('1'), second.id), /already uses/);
  const gate = deferred<void>(); storage.writeGates.push(Promise.resolve(), Promise.resolve(), gate.promise);
  const removal = controller.remove(first.id);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(controller.getSnapshot().items.length, 2);
  gate.resolve(); await removal;
  assert.deepEqual(controller.getSnapshot().items.map(item => item.id), [second.id]);
});

test('corrupt, incomplete, oversize, and unauthorized stores fail closed', async () => {
  const documents = ['{', JSON.stringify({ version: 1, owner: OWNER, items: Array(101).fill({}) }), JSON.stringify({ version: 1, owner: OTHER, items: [] })];
  for (const value of documents) {
    const { factory, storage } = fixture(); storage.value = value;
    const controller = new SavedScansController(factory, () => true);
    await controller.activate(OWNER);
    assert.deepEqual(controller.getSnapshot().items, []);
    assert.equal(controller.getSnapshot().status, 'error');
  }
  const denied = new SavedScansController(fixture().factory, () => false);
  await denied.activate(OWNER);
  assert.deepEqual(denied.getSnapshot(), { owner: null, status: 'idle', items: [], error: null });
});
