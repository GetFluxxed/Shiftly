import type { Count, CountLine, Entry, countsApi } from '../api';

export interface CountOwner { userId: number; businessId: number; storeId: number }

export interface DesiredEntry { entry: Entry; localRevision: number; updatedAt: number }
export interface AttemptedOperation {
  requestId: string; entry: Entry; expectedVersion: number; localRevision: number;
}
export interface OfflineLineRecord {
  canonical: CountLine;
  desired: DesiredEntry | null;
  attempt: AttemptedOperation | null;
  conflict: string | null;
}
export interface StoredOfflineCount {
  owner: CountOwner; count: Count; lines: OfflineLineRecord[]; preparedAt: number; storageGeneration: string;
}
export interface OfflineCountStorage {
  loadActive(owner: CountOwner): Promise<StoredOfflineCount | null>;
  load(owner: CountOwner, countId: string): Promise<StoredOfflineCount | null>;
  prepare(owner: CountOwner, count: Count, lines: CountLine[], preparedAt: number): Promise<StoredOfflineCount>;
  writeLine(owner: CountOwner, countId: string, storageGeneration: string, line: OfflineLineRecord): Promise<void>;
  writeCount(owner: CountOwner, count: Count): Promise<void>;
}

export interface OfflineCountRuntime {
  context(): { status: string; owner: CountOwner | null };
  api: ReturnType<typeof countsApi>;
  revalidate(): Promise<void>;
  authorizeOffline(countId: string): Promise<void>;
  canIncludeCatalog?(): boolean;
}

export interface OfflineCountSnapshot {
  status: 'idle' | 'loading' | 'ready' | 'error';
  count: Count | null;
  lines: CountLine[];
  pendingLineIds: string[];
  conflicts: Record<string, string>;
  syncing: boolean;
  error: string | null;
  preparedAt: number | null;
}
