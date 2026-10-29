import { ApiError, type Transport } from '../api/client';
import type { AccountStatus, Actor, IssuedSession, RedemptionFields, RequestOptions, SignInFields, Store } from '../api/types';

export interface CredentialStore { read(): Promise<string | null>; write(token: string): Promise<void>; remove(): Promise<void> }
export interface Snapshot {
  status: 'loading' | 'signedOut' | 'ready' | 'locked';
  actor: Actor | null; stores: Store[]; message: string | null; busy: boolean; revision: number;
}
const empty = (status: Snapshot['status'], message: string | null = null): Snapshot =>
  ({ status, actor: null, stores: [], message, busy: false, revision: 0 });
function validActor(actor: Actor | undefined): actor is Actor {
  return !!actor && Number.isSafeInteger(actor.userId) && actor.userId > 0
    && Number.isSafeInteger(actor.storeId) && actor.storeId > 0
    && (actor.businessId === null || (Number.isSafeInteger(actor.businessId) && actor.businessId > 0))
    && actor.provenance === 'named' && typeof actor.username === 'string'
    && typeof actor.displayName === 'string' && typeof actor.role === 'string'
    && Array.isArray(actor.capabilities) && actor.capabilities.every(x => typeof x === 'string');
}
function verified(value: AccountStatus): value is AccountStatus & {actor: Actor; stores: Store[]} {
  return value.authenticated === true && validActor(value.actor) && Array.isArray(value.stores)
    && value.stores.every(s => validActor(s) && typeof s.storeName === 'string' && s.userId === value.actor!.userId)
    && value.stores.some(s => s.storeId === value.actor!.storeId);
}
const stale = () => new ApiError('Your session changed. Please try again.');

/** Tokens never enter React state. Epoch changes invalidate pending private responses. */
export class SessionController {
  private state: Snapshot = empty('loading');
  private token: string | null = null;
  private suppressRestore = false;
  private discarded: { token: string | null; storeId: number | null; all: boolean } | null = null;
  private rejectedTokens = new Set<string>();
  private epoch = 0;
  private refreshing = false;
  private listeners = new Set<() => void>();
  private storageTail: Promise<void> = Promise.resolve();
  constructor(private transport: Transport, private credentials: CredentialStore) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(next: Omit<Snapshot, 'revision'>) {
    this.state = { ...next, revision: this.epoch }; this.listeners.forEach(listener => listener());
  }
  private storage<T>(action: () => Promise<T>): Promise<T> {
    const work = this.storageTail.then(action);
    this.storageTail = work.then(() => undefined, () => undefined);
    return work;
  }
  private async clear(message: string | null = null, discardToken = this.token) {
    const version = ++this.epoch;
    this.suppressRestore = true;
    const discarded = { token: discardToken, storeId: this.state.actor?.storeId ?? null, all: false };
    this.discarded = discarded;
    this.token = null; this.publish({ ...empty('signedOut'), busy: true });
    try {
      await this.storage(() => this.credentials.remove());
      if (this.discarded === discarded) this.discarded = null;
    } catch { message = 'Could not clear your saved sign-in. Reconnect and try signing out again before closing the app.'; }
    if (version === this.epoch) this.publish(empty(this.discarded ? 'locked' : 'signedOut', message));
  }
  lock = () => { this.epoch++; this.publish(empty(this.token || this.discarded ? 'locked' : 'signedOut', this.state.message)); };
  restore = async () => {
    if (this.suppressRestore) {
      this.publish(empty(this.discarded ? 'locked' : 'signedOut', this.state.message));
      return;
    }
    const version = ++this.epoch;
    this.publish(empty('loading'));
    try {
      const stored = await this.storage(() => this.credentials.read());
      if (version !== this.epoch) return;
      if (stored && this.rejectedTokens.has(stored)) {
        this.token = null;
        this.suppressRestore = true;
        this.discarded = { token: stored, storeId: null, all: false };
        this.publish(empty('locked', 'An interrupted sign-in could not be cleared. Reconnect and try signing out again.'));
        return;
      }
      this.token = stored;
      if (!stored) { this.publish(empty('signedOut')); return; }
      await this.validate(stored, version);
    } catch (error) {
      if (version === this.epoch) this.publish(empty('locked', error instanceof ApiError ? error.message : 'Secure sign-in is unavailable on this device.'));
    }
  };
  retry = async () => {
    if (this.state.busy) return;
    if (this.discarded) return this.signOut();
    if (!this.token) return this.restore();
    const version = ++this.epoch;
    this.publish(empty('loading'));
    await this.validate(this.token, version);
  };
  refreshAccess = async () => {
    if (this.state.status !== 'ready' || !this.token || this.refreshing) return;
    const token = this.token, version = this.epoch;
    this.refreshing = true;
    try {
      const response = await this.transport.send<AccountStatus>('/accounts/status', {}, token);
      if (version !== this.epoch) return;
      if (!response.authenticated) { await this.clear('Please sign in again.'); return; }
      if (!verified(response)) throw new ApiError('Your account details could not be verified.');
      const before = JSON.stringify([this.state.actor, this.state.stores]);
      if (before !== JSON.stringify([response.actor, response.stores])) {
        this.epoch++;
        this.publish({ status: 'ready', actor: response.actor, stores: response.stores, busy: false, message: null });
      }
    } catch (error) {
      if (version !== this.epoch) return;
      if (error instanceof ApiError && error.status === 401) await this.clear('Your session has ended. Please sign in again.');
      else {
        this.epoch++;
        this.publish(empty('locked', error instanceof ApiError ? error.message : 'Your account could not be verified.'));
      }
    } finally { this.refreshing = false; }
  };
  private async validate(token: string, version: number) {
    try {
      const response = await this.transport.send<AccountStatus>('/accounts/status', {}, token);
      if (version !== this.epoch) return;
      if (!response.authenticated) { await this.clear('Please sign in again.'); return; }
      if (!verified(response)) throw new ApiError('Your account details could not be verified.');
      this.publish({ status: 'ready', actor: response.actor, stores: response.stores, busy: false, message: null });
    } catch (error) {
      if (version !== this.epoch) return;
      if (error instanceof ApiError && error.status === 401) await this.clear('Your session has ended. Please sign in again.');
      else this.publish(empty('locked', error instanceof ApiError ? error.message : 'Your account could not be verified.'));
    }
  }
  private async issue(path: string, body: Record<string, unknown>, previous?: string) {
    if (this.state.busy) throw new ApiError('Please wait for the current action to finish.');
    const version = ++this.epoch;
    this.publish({ ...empty(previous ? 'loading' : 'signedOut'), busy: true });
    let issued: string | undefined;
    try {
      const result = await this.transport.send<IssuedSession>(path, { method: 'POST', body }, previous);
      if (typeof result.sessionToken !== 'string' || result.sessionToken.length < 32 || !validActor(result.actor)
          || result.authenticated !== true || !(result.expiresIn > 0)) throw new ApiError('Your sign-in could not be verified.');
      issued = result.sessionToken;
      if (version !== this.epoch) throw stale();
      await this.storage(async () => {
        if (version !== this.epoch) throw stale();
        await this.credentials.write(result.sessionToken);
      });
      if (version !== this.epoch) throw stale();
      this.token = result.sessionToken;
      this.suppressRestore = false;
      this.discarded = null;
      await this.validate(result.sessionToken, version);
    } catch (error) {
      if (issued) {
        this.rejectedTokens.add(issued);
        void this.transport.send('/accounts/logout', { method: 'POST' }, issued).catch(() => undefined);
      }
      if (version === this.epoch) await this.clear(error instanceof ApiError ? error.message : 'Secure sign-in could not be saved.', issued ?? this.token);
      else if (issued) await this.storage(async () => {
        if (await this.credentials.read() === issued) await this.credentials.remove();
      }).catch(() => undefined);
      throw error instanceof ApiError ? error : new ApiError('Secure sign-in could not be saved.');
    }
  }
  signIn = (fields: SignInFields) => this.issue('/accounts/login', { ...fields });
  activate = (fields: RedemptionFields) => this.issue('/accounts/activate', { ...fields });
  invitationDetails = (token: string) => this.transport.send<import('../accounts/invitations').InvitationDetails>(
    '/accounts/invitation-details', { method: 'POST', body: { token } });
  resetPassword = async (fields: RedemptionFields) => {
    await this.transport.send('/accounts/reset-password', { method: 'POST', body: { ...fields } });
  };
  switchStore = async (storeId: number) => {
    const actor = this.state.actor, token = this.token;
    if (this.state.status !== 'ready' || !actor || !token) throw stale();
    if (!['owner', 'admin'].includes(actor.role)) throw new ApiError('Your account is assigned to one store.', 403, 'permission_denied');
    if (!this.state.stores.some(s => s.storeId === storeId)) throw new ApiError('That store is not available to your account.', 403);
    await this.issue('/accounts/switch-store', { storeId, expectedStoreId: actor.storeId }, token);
  };
  request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
    const actor = this.state.actor, token = this.token, version = this.epoch;
    if (this.state.status !== 'ready' || !actor || !token) throw stale();
    try {
      const body = options.method === 'POST' ? { ...options.body, expectedStoreId: actor.storeId } : options.body;
      const value = await this.transport.send<T>(path, { ...options, body }, token);
      if (version !== this.epoch) throw stale();
      return value;
    } catch (error) {
      if (version === this.epoch && error instanceof ApiError) {
        if (error.status === 401) await this.clear('Your session has ended. Please sign in again.');
        if (error.status === 403 && error.code === 'permission_denied') {
          // A denied action may reveal a remotely changed grant. Revalidate;
          // unchanged access preserves the form, changed access invalidates it.
          await this.refreshAccess();
        } else if ((error.status === 403 || error.status === 409)
          && !(error.status === 409 && ['duplicate_identifier', 'state_conflict', 'stale_record'].includes(error.code || ''))) {
          this.epoch++; this.publish(empty('locked', 'Your access or store may have changed. Reconnect to continue.'));
        }
      }
      throw error;
    }
  };
  transferOwnership = async (userId: number, reason: string) => {
    await this.request('/accounts/transfer-ownership', { method: 'POST', body: { userId, reason } });
    await this.clear('Ownership transferred. Please sign in again.');
  };
  changePassword = async (currentPassword: string, newPassword: string) => {
    await this.request('/accounts/password', { method: 'POST', body: { currentPassword, newPassword } });
    await this.clear('Password changed. Please sign in again.');
  };
  signOut = async (all = false) => {
    if (this.state.busy) throw new ApiError('Please wait for the current action to finish.');
    const discarded = this.discarded ?? { token: this.token, storeId: this.state.actor?.storeId ?? null, all };
    this.discarded = discarded;
    this.suppressRestore = true;
    const { token, storeId } = discarded, version = ++this.epoch;
    all = discarded.all;
    this.token = null; this.publish({ ...empty('signedOut'), busy: true });
    let message: string | null = null;
    // Queue local removal immediately so a newer sign-in cannot be removed later.
    const removal = this.storage(() => this.credentials.remove()).then(() => {
      if (this.discarded === discarded) this.discarded = null;
    }, () => { message = 'Could not clear your saved sign-in. Reconnect and try signing out again before closing the app.'; });
    if (token) {
      try {
        await this.transport.send(`/accounts/${all ? 'logout-all' : 'logout'}`, {
          method: 'POST', body: all ? { expectedStoreId: storeId } : {},
        }, token);
      } catch {
        message ??= all ? 'Signed out here. Sign in again to finish signing out your other devices.'
          : 'Signed out here. Server sign-out could not be confirmed.';
      }
    }
    await removal;
    if (version === this.epoch) this.publish(empty(this.discarded ? 'locked' : 'signedOut', message));
  };
}
