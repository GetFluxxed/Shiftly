import type { CheckpointStorage } from '../../restoration/storage';
import { MAX_SAVED_SCANS, parseScanInput, parseScanOwner, sameScanOwner, scanOwnerKey, validSavedScanId, type SavedScan, type ScanInput, type ScanOwner } from './model';
import { readSavedScans, writeSavedScans } from './storage';

export type SavedScansState = {
  owner: ScanOwner | null;
  status: 'idle' | 'loading' | 'ready' | 'error';
  items: SavedScan[];
  error: string | null;
};

const ID_TEMPLATE = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';

export class SavedScansController {
  private state: SavedScansState = { owner: null, status: 'idle', items: [], error: null };
  private listeners = new Set<() => void>();
  private epoch = 0;
  private queues = new Map<string, Promise<void>>();
  private stores = new Map<string, CheckpointStorage>();

  constructor(
    private storageFactory: (owner: ScanOwner) => CheckpointStorage,
    private isAllowed: (owner: ScanOwner) => boolean,
  ) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): SavedScansState => this.state;

  async activate(candidate: ScanOwner): Promise<void> {
    const owner = parseScanOwner(candidate);
    const epoch = ++this.epoch;
    if (!this.allowed(owner)) {
      this.publish({ owner: null, status: 'idle', items: [], error: null });
      return;
    }
    this.publish({ owner, status: 'loading', items: [], error: null });
    try {
      const items = await this.enqueue(owner, () => readSavedScans(this.store(owner), owner));
      if (!this.current(owner, epoch)) return;
      this.publish({ owner, status: 'ready', items, error: null });
    } catch {
      if (!this.current(owner, epoch)) return;
      this.publish({ owner, status: 'error', items: [], error: 'Saved scans could not be restored.' });
    }
  }

  deactivate(): void {
    this.epoch += 1;
    this.publish({ owner: null, status: 'idle', items: [], error: null });
  }

  async save(value: ScanInput, id?: string): Promise<SavedScan> {
    const input = parseScanInput(value);
    if (id !== undefined && !validSavedScanId(id)) throw new Error('Saved scan identifier is invalid');
    const { owner, epoch } = this.active();
    return this.enqueue(owner, async () => {
      this.requireCurrent(owner, epoch);
      const items = this.state.items;
      if (id === undefined) {
        const duplicate = items.find(item => item.code === input.code && item.barcodeType === input.barcodeType);
        if (duplicate) return duplicate;
        if (items.length >= MAX_SAVED_SCANS) throw new Error(`Saved scan inbox is limited to ${MAX_SAVED_SCANS} items`);
      }
      const index = id === undefined ? -1 : items.findIndex(item => item.id === id);
      if (id !== undefined && index < 0) throw new Error('Saved scan was not found');
      const collision = items.find(item => item.id !== id && item.code === input.code && item.barcodeType === input.barcodeType);
      if (collision) throw new Error('A saved scan already uses this barcode and type');
      const now = Date.now();
      const saved: SavedScan = index < 0
        ? { ...input, id: createId(), createdAt: now, updatedAt: now }
        : { ...input, id: id!, createdAt: items[index]!.createdAt, updatedAt: now };
      const next = index < 0 ? [...items, saved] : items.map((item, itemIndex) => itemIndex === index ? saved : item);
      try { await writeSavedScans(this.store(owner), owner, next); }
      catch { throw new DurabilityError(); }
      this.requireCurrent(owner, epoch);
      this.publish({ owner, status: 'ready', items: next, error: null });
      return saved;
    }).catch(error => {
      if (this.current(owner, epoch) && error instanceof DurabilityError) {
        this.publish({ ...this.state, status: 'error', error: 'Saved scans could not be stored.' });
      }
      throw error;
    });
  }

  async remove(id: string): Promise<void> {
    if (!validSavedScanId(id)) throw new Error('Saved scan identifier is invalid');
    const { owner, epoch } = this.active();
    await this.enqueue(owner, async () => {
      this.requireCurrent(owner, epoch);
      const next = this.state.items.filter(item => item.id !== id);
      if (next.length === this.state.items.length) throw new Error('Saved scan was not found');
      try { await writeSavedScans(this.store(owner), owner, next); }
      catch { throw new DurabilityError(); }
      this.requireCurrent(owner, epoch);
      this.publish({ owner, status: 'ready', items: next, error: null });
    }).catch(error => {
      if (this.current(owner, epoch) && error instanceof DurabilityError) {
        this.publish({ ...this.state, status: 'error', error: 'Saved scan could not be removed.' });
      }
      throw error;
    });
  }

  private active(): { owner: ScanOwner; epoch: number } {
    const owner = this.state.owner;
    if (!owner || this.state.status !== 'ready' || !this.allowed(owner)) throw new Error('Saved scan inbox is not available');
    return { owner, epoch: this.epoch };
  }

  private current(owner: ScanOwner, epoch: number): boolean {
    return this.epoch === epoch && this.state.owner !== null && sameScanOwner(this.state.owner, owner) && this.allowed(owner);
  }

  private allowed(owner: ScanOwner): boolean {
    try { return this.isAllowed(owner); } catch { return false; }
  }

  private requireCurrent(owner: ScanOwner, epoch: number): void {
    if (!this.current(owner, epoch)) throw new StaleScopeError();
  }

  private store(owner: ScanOwner): CheckpointStorage {
    const key = scanOwnerKey(owner);
    let storage = this.stores.get(key);
    if (!storage) { storage = this.storageFactory(owner); this.stores.set(key, storage); }
    return storage;
  }

  private enqueue<T>(owner: ScanOwner, operation: () => Promise<T>): Promise<T> {
    const key = scanOwnerKey(owner);
    const prior = this.queues.get(key) ?? Promise.resolve();
    const result = prior.then(operation);
    const tail = result.then(() => undefined, () => undefined);
    this.queues.set(key, tail);
    void tail.finally(() => { if (this.queues.get(key) === tail) this.queues.delete(key); });
    return result;
  }

  private publish(state: SavedScansState): void {
    this.state = state;
    for (const listener of this.listeners) listener();
  }
}

class StaleScopeError extends Error {
  constructor() { super('Saved scan scope changed'); }
}

class DurabilityError extends Error {
  constructor() { super('Saved scan durable commit failed'); }
}

function createId(): string {
  return ID_TEMPLATE.replace(/[xy]/g, character => {
    const value = Math.floor(Math.random() * 16);
    return (character === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
