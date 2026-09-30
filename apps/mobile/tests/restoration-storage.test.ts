/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { createCheckpointStorage, type SecureKeyValue } from '../src/restoration/storage';

class MemoryKeyValue implements SecureKeyValue {
  readonly values = new Map<string, string>();
  readonly calls: string[] = [];
  failSet: ((key: string, value: string) => boolean) | null = null;
  waitSet: Promise<void> | null = null;

  async get(key: string) {
    this.calls.push(`get:${key}`);
    return this.values.get(key) ?? null;
  }

  async set(key: string, value: string) {
    this.calls.push(`set:${key}`);
    if (this.waitSet) await this.waitSet;
    if (this.failSet?.(key, value)) throw new Error('simulated secure storage failure');
    // SecureStore crosses a native UTF-8 bridge, where an isolated surrogate is replaced.
    this.values.set(key, Buffer.from(value, 'utf8').toString('utf8'));
  }

  async remove(key: string) {
    this.calls.push(`remove:${key}`);
    this.values.delete(key);
  }
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}

test('round trips a large Unicode checkpoint across storage instances', async () => {
  const kv = new MemoryKeyValue();
  const value = JSON.stringify({ notes: '☕️ 店舗 👩🏽‍🍳'.repeat(3_000) });
  await createCheckpointStorage(kv, 'checkpoint').write(value);
  assert.equal(await createCheckpointStorage(kv, 'checkpoint').read(), value);
  const chunks = [...kv.values].filter(([key]) => key.startsWith('checkpoint.bank.'));
  assert.ok(chunks.length > 1);
  assert.ok(chunks.every(([, chunk]) => chunk.length <= 500));
});

test('does not split an emoji surrogate pair at a chunk boundary', async () => {
  const kv = new MemoryKeyValue();
  const value = `${'a'.repeat(499)}😀${'b'.repeat(500)}`;
  await createCheckpointStorage(kv, 'checkpoint').write(value);
  assert.equal(await createCheckpointStorage(kv, 'checkpoint').read(), value);
  assert.equal(kv.values.get('checkpoint.bank.0.0')?.length, 499);
  assert.ok([...kv.values].filter(([key]) => key.startsWith('checkpoint.bank.'))
    .every(([, chunk]) => chunk.length <= 500));
});

test('a partial inactive-bank write preserves the previously committed checkpoint', async () => {
  const kv = new MemoryKeyValue();
  const storage = createCheckpointStorage(kv, 'checkpoint');
  const original = JSON.stringify({ draft: 'original' });
  await storage.write(original);
  kv.failSet = key => key === 'checkpoint.bank.1.1';
  await assert.rejects(storage.write('replacement'.repeat(100)), /simulated secure storage failure/);
  assert.equal(await createCheckpointStorage(kv, 'checkpoint').read(), original);
});

test('rejects malformed manifests and missing checkpoint chunks', async () => {
  const kv = new MemoryKeyValue();
  const storage = createCheckpointStorage(kv, 'checkpoint');
  kv.values.set('checkpoint.manifest', '{bad json');
  await assert.rejects(storage.read(), /manifest is malformed/);

  kv.values.set('checkpoint.manifest', JSON.stringify({
    version: 1, bank: 0, chunks: 1, length: 3, checksum: '00000000',
  }));
  await assert.rejects(storage.read(), /checkpoint is incomplete/);
});

test('serializes writes, removal, and reads so an older write cannot resurrect a checkpoint', async () => {
  const kv = new MemoryKeyValue();
  const gate = deferred();
  kv.waitSet = gate.promise;
  const storage = createCheckpointStorage(kv, 'checkpoint');
  const writing = storage.write('pending checkpoint');
  const removing = storage.remove();
  const reading = storage.read();
  await Promise.resolve();
  assert.equal(kv.calls.some(call => call.startsWith('remove:')), false);
  kv.waitSet = null;
  gate.resolve();
  await writing;
  await removing;
  assert.equal(await reading, null);
  assert.equal(await storage.read(), null);
});

test('rejects checkpoints over 64,000 UTF-16 code units without modifying storage', async () => {
  const kv = new MemoryKeyValue();
  const storage = createCheckpointStorage(kv, 'checkpoint');
  await assert.rejects(storage.write('x'.repeat(64_001)), /64000 character limit/);
  assert.equal(kv.values.size, 0);
  assert.deepEqual(kv.calls, []);
});

test('removal clears the manifest first and every bounded slot in both banks', async () => {
  const kv = new MemoryKeyValue();
  kv.values.set('checkpoint.manifest', 'committed');
  kv.values.set('checkpoint.bank.0.127', 'old');
  kv.values.set('checkpoint.bank.1.127', 'new');
  await createCheckpointStorage(kv, 'checkpoint').remove();
  assert.equal(kv.calls[0], 'remove:checkpoint.manifest');
  assert.equal(kv.calls.filter(call => call.startsWith('remove:checkpoint.bank.')).length, 256);
  assert.equal(kv.values.size, 0);
});


test('a failed cleanup still waits for delayed removals before allowing a new checkpoint', async () => {
  const kv = new MemoryKeyValue();
  const originalRemove = kv.remove.bind(kv);
  const gate = deferred();
  kv.remove = async key => {
    if (key.endsWith('bank.1.1')) throw new Error('failed removal');
    if (key.endsWith('bank.0.0')) await gate.promise;
    await originalRemove(key);
  };
  const storage = createCheckpointStorage(kv, 'checkpoint');
  const removing = assert.rejects(storage.remove(), /cleanup could not finish/);
  const writing = storage.write('new draft');
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(kv.calls.some(call => call.startsWith('set:')), false);
  gate.resolve();
  await removing; await writing;
  assert.equal(await storage.read(), 'new draft');
});
