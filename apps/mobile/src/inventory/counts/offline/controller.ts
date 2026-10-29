import { ApiError } from '../../../api/client';
import { entryTotal } from '../measurements';
import type { Count, CountLine, Entry } from '../api';
import type {
  CountOwner, OfflineCountRuntime, OfflineCountSnapshot, OfflineCountStorage, OfflineLineRecord, StoredOfflineCount,
} from './types';

const EMPTY: OfflineCountSnapshot = { status: 'idle', count: null, lines: [], pendingLineIds: [], conflicts: {}, syncing: false, error: null, preparedAt: null };

function sameOwner(left: CountOwner | null, right: CountOwner | null): boolean {
  return left !== null && right !== null && left.userId === right.userId && left.businessId === right.businessId && left.storeId === right.storeId;
}
function message(error: unknown): string { return error instanceof Error ? error.message : 'The offline count could not be updated.'; }
function displayedSyncError(error: unknown): string | null {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500 || error.status === 401 || error.status === 403)
    ? null : message(error);
}
function effective(record: OfflineLineRecord): CountLine {
  if (!record.desired) return record.canonical;
  const quantity = entryTotal(record.desired.entry, record.canonical);
  if (quantity === null) throw new Error('The saved count entry is no longer valid for this product.');
  return { ...record.canonical, entry: record.desired.entry, quantity, observedAt: new Date(record.desired.updatedAt).toISOString() };
}
function progress(count: Count, records: OfflineLineRecord[]): Count {
  const lines = records.map(effective);
  const countedLines = lines.filter(line => line.entry !== null).length;
  const products = new Map<string, boolean>();
  for (const line of lines) products.set(line.productId, (products.get(line.productId) ?? true) && line.entry !== null);
  return { ...count, totalLines: Math.max(count.totalLines, lines.length), countedLines, totalProducts: Math.max(count.totalProducts, products.size),
    countedProducts: [...products.values()].filter(Boolean).length };
}

export class OfflineCountController {
  private listeners = new Set<() => void>();
  private snapshot: OfflineCountSnapshot = EMPTY;
  private owner: CountOwner | null = null;
  private stored: StoredOfflineCount | null = null;
  private epoch = 0;
  private syncFlight: Promise<void> | null = null;
  private openFlight: { countId: string; promise: Promise<void> } | null = null;
  private localQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly storage: OfflineCountStorage,
    private readonly runtime: OfflineCountRuntime,
    private readonly now: () => number = Date.now,
    private readonly newId: () => string = randomId,
  ) {}

  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  getSnapshot = (): OfflineCountSnapshot => this.snapshot;

  activate = (owner: CountOwner | null): void => {
    if ((owner === null && this.owner === null) || sameOwner(owner, this.owner)) return;
    this.epoch += 1;
    this.openFlight = null;
    this.syncFlight = null;
    this.owner = owner;
    this.stored = null;
    this.publish(owner ? { ...EMPTY } : EMPTY);
  };

  restore = async (): Promise<void> => {
    const owner = this.owner;
    if (!owner) return;
    const epoch = ++this.epoch;
    this.stored = null;
    this.publish({ ...EMPTY, status: 'loading' });
    try {
      const active = await this.storage.loadActive(owner);
      this.assertCurrent(epoch, owner);
      if (!active) { this.publish({ ...EMPTY, status: 'ready' }); return; }
      this.stored = active; this.rebuild();
      if (this.runtime.context().status === 'ready') {
        await this.open(active.count.id);
      }
    } catch (error) {
      if (!this.isCurrent(epoch, owner)) return;
      this.publish({ ...EMPTY, status: 'error', error: message(error) });
      throw error;
    }
  };

  open = (countId: string): Promise<void> => {
    if (this.openFlight?.countId === countId) return this.openFlight.promise;
    const promise = this.performOpen(countId).finally(() => { if (this.openFlight?.promise === promise) this.openFlight = null; });
    this.openFlight = { countId, promise };
    return promise;
  };

  private async performOpen(countId: string): Promise<void> {
    const owner = this.owner;
    if (!owner) throw new Error('Sign in before opening a count.');
    if (this.stored && this.stored.count.id !== countId && this.stored.lines.some(line => line.desired || line.attempt)) {
      const error = 'Sync or resolve the saved entries in this count before preparing another count.';
      this.publish({ ...this.snapshot, error });
      throw new Error(error);
    }
    const epoch = ++this.epoch;
    this.publish({ ...EMPTY, status: 'loading' });
    try {
      const active = await this.storage.loadActive(owner);
      this.assertCurrent(epoch, owner);
      if (active && active.count.id !== countId && active.lines.some(line => line.desired || line.attempt)) {
        this.stored = active; this.rebuild();
        this.publish({ ...this.snapshot, error: 'Sync or resolve the saved entries in this count before preparing another count.' });
        throw new Error('Sync or resolve the saved entries in this count before preparing another count.');
      }
      const cached = active?.count.id === countId ? active : await this.storage.load(owner, countId);
      this.assertCurrent(epoch, owner);
      if (cached) {
        this.stored = cached;
        if (this.runtime.context().status !== 'ready') { this.rebuild(); return; }
        if (cached.lines.some(line => line.desired || line.attempt)) {
          if (cached.count.state === 'draft') {
            await this.runtime.authorizeOffline(countId);
            this.assertCurrent(epoch, owner);
          }
          this.rebuild(); return;
        }
        const fresh = await this.includeCatalog(await this.runtime.api.detail(countId), owner, epoch);
        this.assertCurrent(epoch, owner); this.assertRuntime(owner);
        if (fresh.id !== countId || fresh.storeId !== owner.storeId) throw new Error('The refreshed count could not be verified.');
        if (fresh.version === cached.count.version && fresh.state === cached.count.state
            && fresh.configurationChanged === cached.count.configurationChanged && fresh.totalLines === cached.lines.length) {
          const renewed = await this.serializeLocal(async () => {
            this.assertCurrent(epoch, owner);
            const latest = this.stored;
            if (!latest || latest.count.id !== countId || latest.lines.some(line => line.desired || line.attempt)) return false;
            if (fresh.version < latest.count.version) return false;
            await this.storage.writeCount(owner, fresh);
            this.assertCurrent(epoch, owner); latest.count = fresh;
            return true;
          });
          if (!renewed) { this.rebuild(); return; }
          await this.runtime.authorizeOffline(countId);
          this.assertCurrent(epoch, owner);
          this.rebuild(); return;
        }
      } else if (this.runtime.context().status !== 'ready') {
        throw new Error('Prepare this count while connected before using it offline.');
      }
      const downloaded = await this.download(owner, countId, epoch);
      await this.serializeLocal(async () => {
        this.assertCurrent(epoch, owner);
        if (this.stored?.lines.some(line => line.desired || line.attempt)) {
          throw new Error('Sync or resolve the saved entries in this count before replacing its offline snapshot.');
        }
        const prepared = await this.storage.prepare(owner, downloaded.count, downloaded.lines, downloaded.preparedAt);
        this.assertCurrent(epoch, owner);
        await this.runtime.authorizeOffline(countId);
        this.assertCurrent(epoch, owner);
        this.stored = prepared;
      });
      this.rebuild();
    } catch (error) {
      if (!this.isCurrent(epoch, owner)) return;
      if (this.stored) {
        this.rebuild();
        const shown = displayedSyncError(error);
        if (shown) this.publish({ ...this.snapshot, error: shown });
        if (message(error).startsWith('Sync or resolve the saved entries')) throw error;
        return;
      }
      this.publish({ ...EMPTY, status: 'error', error: message(error) });
      throw error;
    }
  }

  save = (line: CountLine, entry: Entry): Promise<{ line: CountLine; count: Count }> => this.serializeLocal(async () => {
      const owner = this.owner, stored = this.stored, epoch = this.epoch;
      if (!owner || !stored || stored.count.state !== 'draft' || this.snapshot.status !== 'ready') throw new Error('This count is not available for editing.');
      this.assertLocalRuntime(owner);
      const index = stored.lines.findIndex(record => record.canonical.id === line.id);
      if (index < 0) throw new Error('This count line is not part of the prepared snapshot.');
      const current = stored.lines[index]!;
      const quantity = entryTotal(entry, current.canonical);
      if (quantity === null) throw new Error('Enter a valid amount before saving.');
      const localRevision = Math.max(current.desired?.localRevision ?? 0, current.attempt?.localRevision ?? 0) + 1;
      const updated: OfflineLineRecord = { ...current, desired: { entry, localRevision, updatedAt: this.now() }, conflict: null };
      await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
      this.assertCurrent(epoch, owner); this.assertLocalRuntime(owner);
      stored.lines[index] = updated;
      this.rebuild();
      return { line: effective(updated), count: this.snapshot.count! };
    });

  sync = (): Promise<void> => {
    if (this.syncFlight) return this.syncFlight;
    const operation = this.performSync().finally(() => { if (this.syncFlight === operation) this.syncFlight = null; });
    this.syncFlight = operation;
    return operation;
  };

  resolve = async (lineId: string, choice: 'local' | 'server'): Promise<void> => {
    const owner = this.owner, stored = this.stored, epoch = this.epoch;
    if (!owner || !stored) throw new Error('Open the prepared count first.');
    const index = stored.lines.findIndex(record => record.canonical.id === lineId);
    if (index < 0) throw new Error('This count line is not part of the prepared snapshot.');
    const expectedLocalRevision = stored.lines[index]!.desired?.localRevision ?? null;
    await this.runtime.revalidate();
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    const [remote, count] = await Promise.all([this.runtime.api.line(stored.count.id, lineId), this.runtime.api.detail(stored.count.id)]);
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    if (remote.id !== lineId || count.id !== stored.count.id || count.storeId !== owner.storeId) throw new Error('The refreshed count could not be verified.');
    if (choice === 'local' && (count.state !== 'draft' || count.configurationChanged)) throw new Error('This count can no longer accept the local entry.');
    await this.serializeLocal(async () => {
      this.assertCurrent(epoch, owner); this.assertRuntime(owner);
      const latest = stored.lines[index]!;
      if ((latest.desired?.localRevision ?? null) !== expectedLocalRevision) {
        throw new Error('The local entry changed while the conflict was being refreshed. Review it again.');
      }
      if (choice === 'local' && latest.desired && entryTotal(latest.desired.entry, remote) === null) {
        throw new Error('The product configuration changed. Review this entry before uploading it.');
      }
      const updated: OfflineLineRecord = choice === 'server'
        ? { canonical: remote, desired: null, attempt: null, conflict: null }
        : { canonical: remote, desired: latest.desired, attempt: null, conflict: null };
      await this.storage.writeCount(owner, count);
      await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
      this.assertCurrent(epoch, owner);
      stored.count = count; stored.lines[index] = updated; this.rebuild();
    });
  };

  private async performSync(): Promise<void> {
    const owner = this.owner, stored = this.stored, epoch = this.epoch;
    if (!owner || !stored) return;
    this.publish({ ...this.snapshot, syncing: true, error: null });
    try {
      await this.runtime.revalidate();
      this.assertCurrent(epoch, owner); this.assertRuntime(owner);
      const freshCount = await this.includeCatalog(await this.runtime.api.detail(stored.count.id), owner, epoch);
      this.assertCurrent(epoch, owner); this.assertRuntime(owner);
      if (freshCount.id !== stored.count.id || freshCount.storeId !== owner.storeId) throw new Error('The refreshed count could not be verified.');
      // Remember added lines before uploading existing entries. If the connection
      // drops, the old generation remains usable but cannot be reviewed as complete.
      if (freshCount.totalLines > stored.lines.length || stored.count.catalogProductsAvailable) {
        await this.serializeLocal(async () => {
          this.assertCurrent(epoch, owner); this.assertRuntime(owner);
          if (freshCount.version < stored.count.version) return;
          await this.storage.writeCount(owner, freshCount);
          this.assertCurrent(epoch, owner); stored.count = freshCount; this.rebuild(true);
        });
      }
      for (const original of [...stored.lines]) {
        const index = stored.lines.findIndex(record => record.canonical.id === original.canonical.id);
        let current = stored.lines[index]!;
        if (!current.desired || current.conflict) continue;
        if (!current.attempt) {
          if (freshCount.state !== 'draft' || freshCount.configurationChanged) {
            await this.serializeLocal(async () => {
              this.assertCurrent(epoch, owner);
              const latest = stored.lines[index]!;
              const updated = { ...latest, conflict: 'Upload blocked: this count is closed or its configuration changed.' };
              await this.storage.writeCount(owner, freshCount);
              await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
              this.assertCurrent(epoch, owner); stored.lines[index] = updated; stored.count = freshCount; this.rebuild(true);
            });
            continue;
          }
          current = await this.serializeLocal(async () => {
            this.assertCurrent(epoch, owner); this.assertRuntime(owner);
            const latest = stored.lines[index]!;
            if (!latest.desired) return latest;
            const updated = { ...latest, attempt: { requestId: this.newId(), entry: latest.desired.entry,
              expectedVersion: latest.canonical.version, localRevision: latest.desired.localRevision } };
            await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
            this.assertCurrent(epoch, owner); stored.lines[index] = updated; this.rebuild(true);
            return updated;
          });
        }
        const attempt = current.attempt;
        if (!attempt) continue;
        try {
          const result = await this.runtime.api.savePersisted(stored.count.id,
            { ...current.canonical, version: attempt.expectedVersion }, attempt.entry, attempt.requestId);
          this.assertCurrent(epoch, owner); this.assertRuntime(owner);
          if (result.line.id !== current.canonical.id || result.count.id !== stored.count.id || result.count.storeId !== owner.storeId) {
            throw new Error('The saved count response could not be verified.');
          }
          await this.serializeLocal(async () => {
            this.assertCurrent(epoch, owner); this.assertRuntime(owner);
            const latest = stored.lines[index]!;
            if (latest.attempt?.requestId !== attempt.requestId) throw new Error('The pending count operation changed unexpectedly.');
            const canonical = result.line.version >= latest.canonical.version ? result.line : latest.canonical;
            const updated: OfflineLineRecord = { ...latest, canonical, attempt: null,
              desired: latest.desired?.localRevision === attempt.localRevision ? null : latest.desired, conflict: null };
            // Persist server count first. If either checkpoint fails, replaying the immutable request is safe.
            const newestCount = [stored.count, freshCount, result.count].reduce((latest, item) => item.version > latest.version ? item : latest);
            await this.storage.writeCount(owner, newestCount);
            await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
            this.assertCurrent(epoch, owner);
            stored.count = newestCount; stored.lines[index] = updated; this.rebuild(true);
          });
        } catch (error) {
          if (!this.isCurrent(epoch, owner)) return;
          if (error instanceof ApiError && error.status === 409) {
            await this.serializeLocal(async () => {
              this.assertCurrent(epoch, owner);
              const latest = stored.lines[index]!;
              const conflict = error.code === 'stale_record' ? error.message : `Upload blocked: ${error.message}`;
              const updated = { ...latest, attempt: null, conflict };
              await this.storage.writeLine(owner, stored.count.id, stored.storageGeneration, updated);
              this.assertCurrent(epoch, owner); stored.lines[index] = updated; this.rebuild(true);
            });
          }
          throw error;
        }
      }
      if (!stored.lines.some(line => line.desired || line.attempt)
          && (freshCount.totalLines > stored.lines.length || stored.count.totalLines > stored.lines.length)) {
        const downloaded = await this.download(owner, stored.count.id, epoch);
        await this.serializeLocal(async () => {
          this.assertCurrent(epoch, owner); this.assertRuntime(owner);
          // A newer local edit made during the download must never be displaced.
          if (stored.lines.some(line => line.desired || line.attempt)) return;
          const prepared = await this.storage.prepare(owner, downloaded.count, downloaded.lines, downloaded.preparedAt);
          this.assertCurrent(epoch, owner); this.stored = prepared;
        });
      }
    } catch (error) {
      if (this.isCurrent(epoch, owner)) this.publish({ ...this.snapshot, syncing: false, error: displayedSyncError(error) });
      return;
    }
    if (this.isCurrent(epoch, owner)) this.rebuild(false);
  }

  private async includeCatalog(count: Count, owner: CountOwner, epoch: number): Promise<Count> {
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    if (count.storeId !== owner.storeId) throw new Error('This count belongs to another store.');
    if (count.state !== 'draft' || !count.catalogProductsAvailable || !this.runtime.canIncludeCatalog?.()) return count;
    // Persist the need to expand before the request. A lost response must remain
    // visible/retryable even when this device has no observations queued.
    await this.serializeLocal(async () => {
      this.assertCurrent(epoch, owner); this.assertRuntime(owner);
      const stored = this.stored;
      if (!stored || stored.count.id !== count.id || stored.count.version > count.version) return;
      await this.storage.writeCount(owner, count);
      this.assertCurrent(epoch, owner); stored.count = count;
    });
    const expanded = await this.runtime.api.includeCatalog(count, this.newId());
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    if (expanded.id !== count.id || expanded.storeId !== owner.storeId || expanded.version < count.version
        || expanded.totalLines < count.totalLines) throw new Error('The expanded count could not be verified.');
    return expanded;
  }

  private async download(owner: CountOwner, countId: string, epoch: number): Promise<{ count: Count; lines: CountLine[]; preparedAt: number }> {
    const before = await this.includeCatalog(await this.runtime.api.detail(countId), owner, epoch);
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    if (before.id !== countId || before.storeId !== owner.storeId) throw new Error('This count belongs to another store.');
    const lines: CountLine[] = []; let after = ''; const cursors = new Set<string>();
    do {
      if (after && cursors.has(after)) throw new Error('The count line list repeated a page. Try preparing it again.');
      if (after) cursors.add(after);
      const page = await this.runtime.api.lines(countId, '', after);
      this.assertCurrent(epoch, owner); this.assertRuntime(owner);
      lines.push(...page.items); after = page.nextCursor ?? '';
      if (lines.length > 10_000) throw new Error('This count exceeds the offline line limit.');
    } while (after);
    const afterDetail = await this.runtime.api.detail(countId);
    this.assertCurrent(epoch, owner); this.assertRuntime(owner);
    if (afterDetail.id !== countId || afterDetail.storeId !== owner.storeId || before.version !== afterDetail.version || before.state !== afterDetail.state
        || before.configurationChanged !== afterDetail.configurationChanged || afterDetail.totalLines !== lines.length
        || new Set(lines.map(line => line.id)).size !== lines.length) {
      throw new Error('The count changed while it was being prepared. Try again while connected.');
    }
    return { count: afterDetail, lines, preparedAt: this.now() };
  }

  private rebuild(syncing = this.snapshot.syncing): void {
    if (!this.stored) return;
    const count = progress(this.stored.count, this.stored.lines);
    const lines = this.stored.lines.map(effective);
    const conflicts: Record<string, string> = {};
    for (const record of this.stored.lines) if (record.conflict) conflicts[record.canonical.id] = record.conflict;
    this.publish({ status: 'ready', count, lines, pendingLineIds: this.stored.lines.filter(record => record.desired || record.attempt).map(record => record.canonical.id),
      conflicts, syncing, error: null, preparedAt: this.stored.preparedAt });
  }
  private publish(snapshot: OfflineCountSnapshot): void { this.snapshot = snapshot; for (const listener of this.listeners) listener(); }
  private isCurrent(epoch: number, owner: CountOwner): boolean { return epoch === this.epoch && sameOwner(owner, this.owner); }
  private assertCurrent(epoch: number, owner: CountOwner): void { if (!this.isCurrent(epoch, owner)) throw new Error('The active account or store changed.'); }
  private assertRuntime(owner: CountOwner): void {
    const context = this.runtime.context();
    if (context.status !== 'ready' || !sameOwner(context.owner, owner)) throw new Error('The active account or store changed.');
  }
  private assertLocalRuntime(owner: CountOwner): void {
    const context = this.runtime.context();
    if (!['ready', 'offline'].includes(context.status) || !sameOwner(context.owner, owner)) throw new Error('The active account or store changed.');
  }
  private serializeLocal<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.localQueue.then(operation);
    this.localQueue = result.then(() => undefined, () => undefined);
    return result;
  }
}

function randomId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const value = Math.floor(Math.random() * 16); return (character === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
