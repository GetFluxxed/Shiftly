import { ApiError, type Transport } from '../api/client';
import type { AccountStatus, Actor, IssuedSession, RedemptionFields, RequestOptions, SignInFields, Store } from '../api/types';
import { OFFLINE_COUNT_PERMIT_MS, eligibleOfflineActor, eligibleCatalogCapture, usableOfflinePermit, type OfflineCountPermit,
  type OfflineCountPermitStore, validOfflineCountId } from './offlinePermit';

export type { OfflineCountPermit, OfflineCountPermitStore } from './offlinePermit';

export interface CredentialStore { read(): Promise<string | null>; write(token: string): Promise<void>; remove(): Promise<void> }
export interface Snapshot {
  status: 'loading' | 'signedOut' | 'ready' | 'locked' | 'offline';
  actor: Actor | null; stores: Store[]; message: string | null; busy: boolean; revision: number;
  offlineCountId?: string | null;
  offlineCatalogCapture?: boolean;
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
  private refreshPromise: Promise<void> | null = null;
  private refreshToken: string | null = null;
  private refreshEpoch = -1;
  private permit: OfflineCountPermit | null = null;
  private validatedAt: number | null = null;
  private listeners = new Set<() => void>();
  private storageTail: Promise<void> = Promise.resolve();
  constructor(private transport: Transport, private credentials: CredentialStore,
    private permitStore?: OfflineCountPermitStore) {}
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
  private async removePermit() {
    this.permit = null;
    if (this.state.offlineCatalogCapture) this.publish({ ...this.state, offlineCatalogCapture: false });
    if (this.permitStore) await this.storage(() => this.permitStore!.remove());
  }
  private permitMatches(token: string, permit = this.permit) {
    const now = Date.now();
    return !!permit && permit.token === token && permit.validatedAt <= now
      && now - permit.validatedAt <= OFFLINE_COUNT_PERMIT_MS && usableOfflinePermit(permit)
      && permit.stores.some(store => store.storeId === permit.actor.storeId
        && store.userId === permit.actor.userId && store.businessId === permit.actor.businessId);
  }
  private samePermitScope(permit: OfflineCountPermit, token: string, actor: Actor) {
    return permit.token === token && permit.actor.userId === actor.userId
      && permit.actor.businessId === actor.businessId && permit.actor.storeId === actor.storeId
      && permit.actor.role === actor.role
      && JSON.stringify([...permit.actor.capabilities].sort()) === JSON.stringify([...actor.capabilities].sort());
  }
  private async acceptValidation(token: string, actor: Actor, stores: Store[], version: number) {
    if (version !== this.epoch || token !== this.token) return;
    const validatedAt = Date.now();
    this.validatedAt = validatedAt;
    if (!this.permit || !this.permitStore) return;
    if (!this.samePermitScope(this.permit, token, actor) || !usableOfflinePermit({ ...this.permit, actor })) {
      await this.removePermit();
      return;
    }
    await this.storage(async () => {
      if (version !== this.epoch || token !== this.token || !this.permit) return;
      // A newly prepared workflow may have joined while validation was queued.
      const renewed: OfflineCountPermit = { ...this.permit, actor, stores, validatedAt };
      await this.permitStore!.write(renewed);
      if (version === this.epoch && token === this.token) { this.permit = renewed; return; }
      await this.permitStore!.remove().catch(() => undefined);
      return false;
    });
  }
  private transient(error: unknown) {
    return error instanceof ApiError && !error.code
      && (error.status === 0 || [502, 503, 504].includes(error.status));
  }
  private offline(token: string, error: unknown): boolean {
    if (!this.permitMatches(token)) return false;
    const permit = this.permit!;
    this.publish({ status: 'offline', actor: permit.actor, stores: permit.stores, busy: false,
      message: error instanceof ApiError ? error.message : 'Shiftly is offline.',
      offlineCountId: eligibleOfflineActor(permit.actor) ? permit.countId : null,
      offlineCatalogCapture: permit.catalogCapture === true && eligibleCatalogCapture(permit.actor) });
    return true;
  }
  private async loadPermit(token: string, version: number) {
    if (!this.permitStore) return;
    let loaded: OfflineCountPermit | null = null;
    try {
      loaded = await this.storage(async () => {
        try { return await this.permitStore!.read(); }
        catch { await this.permitStore!.remove().catch(() => undefined); return null; }
      });
    } catch { loaded = null; }
    if (version === this.epoch && token === this.token) this.permit = loaded;
  }
  private async clear(message: string | null = null, discardToken = this.token) {
    const version = ++this.epoch;
    this.suppressRestore = true;
    const discarded = { token: discardToken, storeId: this.state.actor?.storeId ?? null, all: false };
    this.discarded = discarded;
    this.token = null; this.permit = null; this.publish({ ...empty('signedOut'), busy: true });
    try {
      await this.storage(async () => {
        await this.credentials.remove();
        if (this.permitStore) await this.permitStore.remove();
      });
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
      await this.loadPermit(stored, version);
      if (version !== this.epoch) return;
      await this.validate(stored, version);
    } catch (error) {
      if (version === this.epoch) this.publish(empty('locked', error instanceof ApiError ? error.message : 'Secure sign-in is unavailable on this device.'));
    }
  };
  retry = async () => {
    if (this.state.busy) return;
    if (this.discarded) return this.signOut();
    const token = this.token;
    if (!token) return this.restore();
    if (this.state.status === 'offline') return this.refreshAccess();
    const version = ++this.epoch;
    this.publish(empty('loading'));
    await this.validate(token, version);
  };
  refreshAccess = (): Promise<void> => {
    const token = this.token;
    if (!['ready', 'offline'].includes(this.state.status) || !token) return Promise.resolve();
    if (this.refreshPromise && this.refreshToken === token && this.refreshEpoch === this.epoch) return this.refreshPromise;
    const work = this.revalidateAccess(token);
    let shared!: Promise<void>;
    shared = work.finally(() => {
      if (this.refreshPromise === shared) { this.refreshPromise = null; this.refreshToken = null; this.refreshEpoch = -1; }
    });
    this.refreshPromise = shared;
    this.refreshToken = token;
    this.refreshEpoch = this.epoch;
    return shared;
  };
  private async revalidateAccess(token: string) {
    const version = this.epoch;
    try {
      const response = await this.transport.send<AccountStatus>('/accounts/status', {}, token);
      if (version !== this.epoch) return;
      if (!response.authenticated) { await this.clear('Please sign in again.'); return; }
      if (!verified(response)) throw new ApiError('Your account details could not be verified.', 0, 'unverified_account');
      await this.acceptValidation(token, response.actor, response.stores, version);
      if (version !== this.epoch) return;
      const before = JSON.stringify([this.state.actor, this.state.stores]);
      if (this.state.status !== 'ready' || before !== JSON.stringify([response.actor, response.stores])) {
        this.epoch++;
        this.publish({ status: 'ready', actor: response.actor, stores: response.stores, busy: false, message: null,
          offlineCatalogCapture: this.permit?.catalogCapture === true && eligibleCatalogCapture(response.actor) });
      }
    } catch (error) {
      if (version !== this.epoch) return;
      if (error instanceof ApiError && error.status === 401) await this.clear('Your session has ended. Please sign in again.');
      else if (this.transient(error) && this.offline(token, error)) return;
      else {
        await this.removePermit().catch(() => undefined);
        this.epoch++;
        this.publish(empty('locked', error instanceof ApiError ? error.message : 'Your account could not be verified.'));
      }
    }
  }
  private async validate(token: string, version: number) {
    try {
      const response = await this.transport.send<AccountStatus>('/accounts/status', {}, token);
      if (version !== this.epoch) return;
      if (!response.authenticated) { await this.clear('Please sign in again.'); return; }
      if (!verified(response)) throw new ApiError('Your account details could not be verified.', 0, 'unverified_account');
      await this.acceptValidation(token, response.actor, response.stores, version);
      if (version !== this.epoch) return;
      this.publish({ status: 'ready', actor: response.actor, stores: response.stores, busy: false, message: null,
          offlineCatalogCapture: this.permit?.catalogCapture === true && eligibleCatalogCapture(response.actor) });
    } catch (error) {
      if (version !== this.epoch) return;
      if (error instanceof ApiError && error.status === 401) await this.clear('Your session has ended. Please sign in again.');
      else if (this.transient(error) && this.offline(token, error)) return;
      else {
        await this.removePermit().catch(() => undefined);
        this.publish(empty('locked', error instanceof ApiError ? error.message : 'Your account could not be verified.'));
      }
    }
  }
  private async issue(path: string, body: Record<string, unknown>, previous?: string) {
    if (this.state.busy) throw new ApiError('Please wait for the current action to finish.');
    const version = ++this.epoch;
    this.publish({ ...empty(previous ? 'loading' : 'signedOut'), busy: true });
    let issued: string | undefined;
    try {
      await this.removePermit();
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
  canCaptureScans = () => {
    const { status, actor } = this.state;
    // Connected capture uses current catalog permission; only offline capture
    // additionally requires the explicit, durably prepared, unexpired grant.
    return !!actor && eligibleCatalogCapture(actor) && (status === 'ready'
      || status === 'offline' && !!this.token && this.permitMatches(this.token) && this.permit?.catalogCapture === true);
  };
  authorizeOfflineCount = (countId: string) => this.authorizeOffline({ countId });
  authorizeOfflineCatalogCapture = () => this.authorizeOffline({ catalogCapture: true });
  private async authorizeOffline(grant: { countId?: string; catalogCapture?: true }) {
    const actor = this.state.actor, token = this.token, validatedAt = this.validatedAt;
    if (!this.permitStore) throw new ApiError('Offline authorization is unavailable on this device.');
    if (this.state.status !== 'ready' || !actor || !token || validatedAt === null) throw stale();
    if (grant.countId !== undefined && !validOfflineCountId(grant.countId)) throw new ApiError('This count is unavailable.');
    if (grant.countId !== undefined && !eligibleOfflineActor(actor)
        || grant.catalogCapture && !eligibleCatalogCapture(actor))
      throw new ApiError('Your account cannot use this offline workspace.', 403, 'permission_denied');
    if (validatedAt > Date.now() || Date.now() - validatedAt > OFFLINE_COUNT_PERMIT_MS)
      throw new ApiError('Reconnect before enabling offline work.');
    const version = this.epoch;
    const committed = await this.storage(async () => {
      if (version !== this.epoch || this.token !== token || this.state.status !== 'ready') return false;
      // Merge inside the serialized commit: preparing count and capture together
      // must preserve both grants, without extending their offline lifetime.
      const existing = this.permit && this.samePermitScope(this.permit, token, actor) ? this.permit : null;
      const permit: OfflineCountPermit = { version: 1, token, actor, stores: this.state.stores,
        countId: grant.countId ?? existing?.countId ?? null,
        catalogCapture: grant.catalogCapture === true || existing?.catalogCapture === true, validatedAt };
      await this.permitStore!.write(permit);
      if (version === this.epoch && this.token === token && this.state.status === 'ready') {
        this.permit = permit;
        return true;
      }
      await this.permitStore!.remove().catch(() => undefined);
      return false;
    });
    if (!committed || version !== this.epoch || this.token !== token || this.state.status !== 'ready') throw stale();
    if (this.state.offlineCatalogCapture !== this.permit?.catalogCapture)
      this.publish({ ...this.state, offlineCatalogCapture: this.permit?.catalogCapture === true });
  }
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
          await this.removePermit().catch(() => undefined);
          await this.refreshAccess();
        } else if ((error.status === 403 || error.status === 409)
          && !(error.status === 409 && ['duplicate_identifier', 'state_conflict', 'stale_record'].includes(error.code || ''))) {
          await this.removePermit().catch(() => undefined);
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
    this.permit = null;
    const removal = this.storage(async () => {
      await this.credentials.remove();
      if (this.permitStore) await this.permitStore.remove();
    }).then(() => {
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
