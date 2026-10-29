import { createCheckpointStorage, type SecureKeyValue } from '../../../restoration/storage';
import { validId } from '../../api';
import { parseCount, parseCountLine, type Count, type CountLine } from '../api';
import type { CountOwner, OfflineCountStorage, OfflineLineRecord, StoredOfflineCount } from './types';

const PAGE_SIZE = 100;
const MAX_LINES = 10_000;
type Manifest = { version: 1; owner: CountOwner; count: Count; preparedAt: number; generation: string; pages: number; lines: number };

function ownerKey(owner: CountOwner): string {
  return `${owner.userId}.${owner.businessId}.${owner.storeId}`;
}
function sameOwner(left: CountOwner, right: CountOwner): boolean {
  return left.userId === right.userId && left.businessId === right.businessId && left.storeId === right.storeId;
}
function object(value: unknown): asserts value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Offline count cache is malformed');
}
function parseOwner(value: unknown): CountOwner {
  object(value);
  if (![value.userId, value.businessId, value.storeId].every(item => Number.isSafeInteger(item) && Number(item) > 0)) {
    throw new Error('Offline count cache is malformed');
  }
  return { userId: Number(value.userId), businessId: Number(value.businessId), storeId: Number(value.storeId) };
}
function parseRecord(value: unknown): OfflineLineRecord {
  object(value);
  const canonical = parseCountLine(value.canonical);
  const desired = value.desired;
  if (desired !== null) {
    object(desired);
    if (!Number.isSafeInteger(desired.localRevision) || Number(desired.localRevision) < 1 || !Number.isFinite(desired.updatedAt)) throw new Error('Offline count cache is malformed');
    // Reuse the line parser to fully validate the persisted entry.
    parseCountLine({ ...canonical, entry: desired.entry, quantity: canonical.quantity ?? '0' });
  }
  const attempt = value.attempt;
  if (attempt !== null) {
    object(attempt);
    if (!validId(attempt.requestId) || !Number.isSafeInteger(attempt.expectedVersion) || Number(attempt.expectedVersion) < 1
        || !Number.isSafeInteger(attempt.localRevision) || Number(attempt.localRevision) < 1) throw new Error('Offline count cache is malformed');
    parseCountLine({ ...canonical, entry: attempt.entry, quantity: canonical.quantity ?? '0' });
  }
  if (value.conflict !== null && typeof value.conflict !== 'string') throw new Error('Offline count cache is malformed');
  return value as unknown as OfflineLineRecord;
}

export function createOfflineCountStorage(kv: SecureKeyValue, prefix: string): OfflineCountStorage {
  let queue: Promise<void> = Promise.resolve();
  const doc = (key: string) => createCheckpointStorage(kv, `${prefix}.${key}`);
  const serialize = <T>(operation: () => Promise<T>): Promise<T> => {
    const result = queue.then(operation);
    queue = result.then(() => undefined, () => undefined);
    return result;
  };
  const base = (owner: CountOwner, countId: string) => `${ownerKey(owner)}.${countId}`;
  const activeKey = (owner: CountOwner) => `${ownerKey(owner)}.active`;
  const lineKey = (owner: CountOwner, countId: string, generation: string, lineId: string) => `${base(owner, countId)}.line.${generation}.${lineId}`;

  return {
    loadActive: owner => serialize(async () => {
      return loadActiveWithoutQueue(owner);
    }),
    load: (owner, countId) => serialize(async () => {
      return loadWithoutQueue(owner, countId);
    }),
    prepare: (owner, count, lines, preparedAt) => serialize(async () => {
      const previousActive = await loadActiveWithoutQueue(owner);
      if (previousActive?.lines.some(line => line.desired || line.attempt)) {
        throw new Error('Sync or resolve the saved entries in this count before replacing its offline snapshot.');
      }
      const previous = previousActive?.count.id === count.id ? previousActive : await loadWithoutQueue(owner, count.id);
      if (previous?.lines.some(line => line.desired || line.attempt)) {
        throw new Error('Sync or resolve the saved entries in this count before replacing its offline snapshot.');
      }
      if (count.storeId !== owner.storeId || lines.length !== count.totalLines || lines.length > MAX_LINES
          || new Set(lines.map(line => line.id)).size !== lines.length) throw new Error('Offline count snapshot is incomplete');
      const generation = generationId();
      for (const line of lines) await doc(lineKey(owner, count.id, generation, line.id)).write(JSON.stringify({ canonical: line, desired: null, attempt: null, conflict: null }));
      const pages = Math.ceil(lines.length / PAGE_SIZE);
      for (let page = 0; page < pages; page += 1) {
        await doc(`${base(owner, count.id)}.index.${generation}.${page}`).write(JSON.stringify(lines.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(line => line.id)));
      }
      const manifest: Manifest = { version: 1, owner, count, preparedAt, generation, pages, lines: lines.length };
      await doc(`${base(owner, count.id)}.manifest`).write(JSON.stringify(manifest));
      await doc(activeKey(owner)).write(JSON.stringify({ version: 1, owner, countId: count.id }));
      if (previous && previous.storageGeneration !== generation) {
        void cleanupGeneration(owner, count.id, previous).catch(() => undefined);
      }
      if (previousActive && previousActive.count.id !== count.id) {
        void cleanupCount(owner, previousActive).catch(() => undefined);
      }
      return { owner, count, lines: lines.map(canonical => ({ canonical, desired: null, attempt: null, conflict: null })), preparedAt, storageGeneration: generation };
    }),
    writeLine: (owner, countId, storageGeneration, line) => serialize(async () => {
      if (!validId(countId) || !validId(storageGeneration) || !validId(line.canonical.id)) throw new Error('Offline count identifier is invalid');
      await doc(lineKey(owner, countId, storageGeneration, line.canonical.id)).write(JSON.stringify(line));
    }),
    writeCount: (owner, count) => serialize(async () => {
      const storage = doc(`${base(owner, count.id)}.manifest`);
      const raw = await storage.read();
      if (raw === null) throw new Error('Offline count cache is incomplete');
      let value: unknown; try { value = JSON.parse(raw); } catch { throw new Error('Offline count cache is malformed'); }
      object(value); parseCount(count);
      if (count.storeId !== owner.storeId) throw new Error('Offline count belongs to another store');
      await storage.write(JSON.stringify({ ...value, count }));
    }),
  };

  async function loadActiveWithoutQueue(owner: CountOwner): Promise<StoredOfflineCount | null> {
    const raw = await doc(activeKey(owner)).read();
    if (raw === null) return null;
    let value: unknown; try { value = JSON.parse(raw); } catch { throw new Error('Offline count cache is malformed'); }
    object(value);
    const storedOwner = parseOwner(value.owner);
    if (!sameOwner(owner, storedOwner) || !validId(value.countId)) throw new Error('Offline count cache belongs to another account or store');
    return loadWithoutQueue(owner, String(value.countId));
  }

  async function loadWithoutQueue(owner: CountOwner, countId: string): Promise<StoredOfflineCount | null> {
      if (!validId(countId)) throw new Error('Offline count identifier is invalid');
      const raw = await doc(`${base(owner, countId)}.manifest`).read();
      if (raw === null) return null;
      let value: unknown;
      try { value = JSON.parse(raw); } catch { throw new Error('Offline count cache is malformed'); }
      object(value);
      if (value.version !== 1 || !Number.isSafeInteger(value.pages) || Number(value.pages) < 0 || Number(value.pages) > Math.ceil(MAX_LINES / PAGE_SIZE)
          || !Number.isSafeInteger(value.lines) || Number(value.lines) < 0 || Number(value.lines) > MAX_LINES
          || typeof value.generation !== 'string' || !validId(value.generation) || !Number.isFinite(value.preparedAt)) throw new Error('Offline count cache is malformed');
      const storedOwner = parseOwner(value.owner);
      if (!sameOwner(owner, storedOwner)) throw new Error('Offline count cache belongs to another account or store');
      const count = parseCount(value.count);
      // An acknowledged catalog expansion may arrive before its new lines can be
      // downloaded. Keep the prior complete generation (and queued observations)
      // readable; the controller blocks review until the expanded list is ready.
      if (count.id !== countId || count.storeId !== owner.storeId || count.totalLines < Number(value.lines)) throw new Error('Offline count cache is incomplete');
      const ids: string[] = [];
      for (let page = 0; page < Number(value.pages); page += 1) {
        const pageRaw = await doc(`${base(owner, countId)}.index.${value.generation}.${page}`).read();
        if (pageRaw === null) throw new Error('Offline count cache is incomplete');
        let pageValue: unknown; try { pageValue = JSON.parse(pageRaw); } catch { throw new Error('Offline count cache is malformed'); }
        if (!Array.isArray(pageValue) || pageValue.length > PAGE_SIZE || pageValue.some(id => !validId(id))) throw new Error('Offline count cache is malformed');
        ids.push(...pageValue as string[]);
      }
      if (ids.length !== Number(value.lines) || new Set(ids).size !== ids.length) throw new Error('Offline count cache is incomplete');
      const lines: OfflineLineRecord[] = [];
      for (const id of ids) {
        const lineRaw = await doc(lineKey(owner, countId, String(value.generation), id)).read();
        if (lineRaw === null) throw new Error('Offline count cache is incomplete');
        let lineValue: unknown; try { lineValue = JSON.parse(lineRaw); } catch { throw new Error('Offline count cache is malformed'); }
        const line = parseRecord(lineValue);
        if (line.canonical.id !== id) throw new Error('Offline count cache is malformed');
        lines.push(line);
      }
      return { owner: storedOwner, count, lines, preparedAt: Number(value.preparedAt), storageGeneration: String(value.generation) };
  }

  async function cleanupGeneration(owner: CountOwner, countId: string, previous: StoredOfflineCount): Promise<void> {
    const pages = Math.ceil(previous.lines.length / PAGE_SIZE);
    for (let page = 0; page < pages; page += 1) {
      await retire(`${base(owner, countId)}.index.${previous.storageGeneration}.${page}`);
    }
    for (const line of previous.lines) {
      await retire(lineKey(owner, countId, previous.storageGeneration, line.canonical.id));
    }
  }

  async function cleanupCount(owner: CountOwner, previous: StoredOfflineCount): Promise<void> {
    await cleanupGeneration(owner, previous.count.id, previous);
    await retire(`${base(owner, previous.count.id)}.manifest`);
  }

  async function retire(key: string): Promise<void> {
    const documentPrefix = `${prefix}.${key}`;
    try {
      const raw = await kv.get(`${documentPrefix}.manifest`);
      let chunks = 0;
      if (raw !== null) {
        const value = JSON.parse(raw) as { chunks?: unknown };
        if (Number.isSafeInteger(value.chunks) && Number(value.chunks) >= 0 && Number(value.chunks) <= 128) chunks = Number(value.chunks);
      }
      await kv.remove(`${documentPrefix}.manifest`);
      for (const bank of [0, 1]) for (let index = 0; index < chunks; index += 1) {
        await kv.remove(`${documentPrefix}.bank.${bank}.${index}`);
      }
    } catch { /* a committed replacement never fails because retirement is best effort */ }
  }
}

function generationId(): string {
  const random = () => Math.floor(Math.random() * 16);
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const value = random(); return (character === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
