import type { Snapshot } from '../session/controller';
import type { CheckpointStorage } from './storage';
import { savedRoute, workspaceScope, type SavedRoute } from './policy';

const lifetime = 7 * 24 * 60 * 60 * 1000;
const maxEntries = 100;
type Entry = { value: unknown; baseline: string; at: number };
type Document = { version: 1; scope: string; at: number; route: SavedRoute | null; entries: Record<string, Entry> };
type State = { ready: boolean; scope: string | null; resume: number; route: SavedRoute | null; message: string | null };
const storageFailure = 'Your place is kept while this app is open, but could not be saved on this device. Keep the app open until your work is saved.';
const blank = (scope: string, at: number): Document => ({ version: 1, scope, at, route: null, entries: {} });
const validKey = (key: string) => key.length > 0 && key.length <= 220 && !['__proto__', 'constructor', 'prototype'].includes(key);
const current = (at: unknown, now: number): at is number => typeof at === 'number' && at <= now + 60_000 && now - at < lifetime;

export class WorkspaceController {
  private state: State = { ready: false, scope: null, resume: 0, route: null, message: null };
  private document: Document | null = null;
  private generation = 0;
  private loadingScope: string | null = null;
  private dirty = false;
  private discardSaved = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private tail: Promise<unknown> = Promise.resolve();
  private listeners = new Set<() => void>();
  constructor(private storage: CheckpointStorage, private now = Date.now) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(update: Partial<State>) { this.state = { ...this.state, ...update }; this.listeners.forEach(fn => fn()); }
  private queue<T>(action: () => Promise<T>): Promise<T> {
    const work = this.tail.then(action); this.tail = work.catch(() => undefined); return work;
  }
  accept = (session: Snapshot) => {
    if (session.status === 'signedOut') { this.clear(); return; }
    if (session.status !== 'ready' || !session.actor) {
      this.generation++; this.loadingScope = null;
      if (this.state.ready) this.publish({ ready: false });
      return;
    }
    const scope = workspaceScope(session.actor, session.stores);
    if (this.state.ready && this.state.scope === scope || this.loadingScope === scope) return;
    const generation = ++this.generation;
    this.loadingScope = scope;
    this.publish({ ready: false });
    void this.queue(async () => {
      let next = this.document;
      let message = this.state.message;
      if (!next && !this.discardSaved) {
        try {
          const raw = await this.storage.read();
          if (raw && raw.length <= 60_000) {
            const candidate = JSON.parse(raw) as Document;
            if (candidate?.version === 1 && candidate.scope === scope && current(candidate.at, this.now())
                && candidate.entries && typeof candidate.entries === 'object' && !Array.isArray(candidate.entries)) {
              next = blank(scope, this.now());
              if (candidate.route && typeof candidate.route.pathname === 'string')
                next.route = savedRoute(candidate.route.pathname, candidate.route.params || {}, session.actor!);
              for (const [key, entry] of Object.entries(candidate.entries).slice(-maxEntries)) {
                if (validKey(key) && entry && typeof entry.baseline === 'string' && entry.baseline.length <= 4000
                    && current(entry.at, this.now()) && JSON.stringify(entry.value)?.length <= 12_000) next.entries[key] = entry;
              }
            }
          }
        } catch {
          message = storageFailure;
          // A broken manifest must not prevent every later checkpoint.
          try { await this.storage.remove(); } catch { /* Keep the safe storage notice. */ }
        }
      }
      if (generation !== this.generation) return;
      if (!next || next.scope !== scope || !current(next.at, this.now())) next = blank(scope, this.now());
      this.document = next;
      this.loadingScope = null;
      this.publish({ ready: true, scope, resume: this.state.resume + 1, route: next.route, message });
      // Replacing a scope also replaces its on-device checkpoint.
      this.changed();
    });
  };
  private clear() {
    this.generation++; this.loadingScope = null; this.document = null; this.dirty = false; this.discardSaved = true;
    clearTimeout(this.timer);
    this.publish({ ready: false, scope: null, route: null, message: null });
    void this.queue(() => this.storage.remove()).catch(() => {
      if (!this.document) this.publish({ message: 'Saved workspace cleanup could not finish. Reconnect and sign out again before sharing this device.' });
    });
  }
  private changed() {
    this.dirty = true; clearTimeout(this.timer);
    this.timer = setTimeout(() => { void this.flush(); }, 200);
  }
  flush = async (): Promise<boolean> => {
    clearTimeout(this.timer);
    if (!this.document || !this.dirty) { await this.tail; return !this.state.message; }
    const document = this.document, scope = document.scope;
    document.at = this.now();
    const serialized = JSON.stringify(document);
    this.dirty = false;
    if (serialized.length > 60_000) { this.dirty = true; this.publish({ message: storageFailure }); return false; }
    return this.queue(async () => {
      try {
        await this.storage.write(serialized);
        if (this.document?.scope === scope) this.publish({ message: null });
        return true;
      } catch {
        if (this.document?.scope === scope) { this.dirty = true; this.publish({ message: storageFailure }); }
        return false;
      }
    });
  };
  route = (route: SavedRoute, scope: string) => {
    if (!this.state.ready || this.document?.scope !== scope) return;
    if (JSON.stringify(route) === JSON.stringify(this.document.route)) return;
    this.document.route = route; this.changed();
  };
  read<T>(key: string, initial: T, baseline = ''): T {
    const entry = this.state.ready ? this.document?.entries[key] : undefined;
    if (!entry || entry.baseline !== baseline || !current(entry.at, this.now()) || !sameShape(entry.value, initial)) return initial;
    return entry.value as T;
  }
  write(key: string, value: unknown, baseline: string, scope: string | null) {
    if (!this.state.ready || !scope || this.document?.scope !== scope || !validKey(key) || baseline.length > 4000) return;
    const serialized = JSON.stringify(value);
    if (!serialized || serialized.length > 12_000) { this.publish({ message: storageFailure }); return; }
    this.document.entries[key] = { value: JSON.parse(serialized), baseline, at: this.now() };
    const keys = Object.keys(this.document.entries).sort((a, b) => this.document!.entries[a]!.at - this.document!.entries[b]!.at);
    for (const old of keys.slice(0, Math.max(0, keys.length - maxEntries))) delete this.document.entries[old];
    this.changed();
  }
  remove(key: string, scope: string | null) {
    if (!this.state.ready || this.document?.scope !== scope) return;
    delete this.document.entries[key]; this.changed();
  }
}

/** Corrupt local input must not turn a string, list or boolean into executable form state. */
function sameShape(value: unknown, initial: unknown): boolean {
  if (initial === null) return value === null || typeof value === 'string' || typeof value === 'number' && Number.isFinite(value);
  if (typeof initial === 'number') return typeof value === 'number' && Number.isFinite(value);
  if (typeof initial !== 'object') return typeof value === typeof initial;
  if (Array.isArray(initial)) return Array.isArray(value) && value.length <= 500
    && value.every(v => initial.length ? initial.some(example => sameShape(v, example)) : safeData(v, 0));
  return !!value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(initial).length === Object.keys(value).length
    && Object.entries(initial).every(([key, item]) => Object.hasOwn(value, key) && sameShape((value as Record<string, unknown>)[key], item));
}

/** Empty remembered lists still need bounded JSON rows, such as recipe ingredients. */
function safeData(value: unknown, depth: number): boolean {
  if (depth > 4) return false;
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true;
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.length <= 500 && value.every(item => safeData(item, depth + 1));
  if (!value || typeof value !== 'object') return false;
  const entries = Object.entries(value);
  return entries.length <= 30 && entries.every(([key, item]) => validKey(key) && safeData(item, depth + 1));
}
