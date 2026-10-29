import type { Actor, Store } from '../api/types';

export const OFFLINE_COUNT_PERMIT_MS = 12 * 60 * 60 * 1_000;

/** Encrypted at rest. The bearer token is never copied into a session snapshot. */
export interface OfflineCountPermit {
  version: 1;
  token: string;
  actor: Actor;
  stores: Store[];
  countId: string | null;
  catalogCapture?: boolean;
  validatedAt: number;
}

export interface OfflineCountPermitStore {
  read(): Promise<OfflineCountPermit | null>;
  write(permit: OfflineCountPermit): Promise<void>;
  remove(): Promise<void>;
}

const countIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function validOfflineCountId(value: unknown): value is string {
  return typeof value === 'string' && countIdPattern.test(value);
}

export function eligibleOfflineActor(actor: Actor): boolean {
  return actor.businessId !== null
    && actor.capabilities.includes('inventory.view')
    && actor.capabilities.includes('counts.submit');
}


/** Capture permission saves local drafts only; server catalog writes stay online. */
export function eligibleCatalogCapture(actor: Actor): boolean {
  return actor.businessId !== null && actor.capabilities.includes('inventory.view')
    && actor.capabilities.includes('catalog.manage');
}

export function usableOfflinePermit(permit: OfflineCountPermit): boolean {
  const count = validOfflineCountId(permit.countId) && eligibleOfflineActor(permit.actor);
  const capture = permit.catalogCapture === true && eligibleCatalogCapture(permit.actor);
  return (permit.countId === null || count)
    && (permit.catalogCapture === undefined || permit.catalogCapture === false || capture)
    && (count || capture);
}

function validActor(value: unknown): value is Actor {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const actor = value as Partial<Actor>;
  return Number.isSafeInteger(actor.userId) && Number(actor.userId) > 0
    && Number.isSafeInteger(actor.storeId) && Number(actor.storeId) > 0
    && Number.isSafeInteger(actor.businessId) && Number(actor.businessId) > 0
    && actor.provenance === 'named' && typeof actor.username === 'string'
    && typeof actor.displayName === 'string' && typeof actor.role === 'string'
    && Array.isArray(actor.capabilities) && actor.capabilities.every(item => typeof item === 'string');
}

export function parseOfflineCountPermit(raw: string): OfflineCountPermit {
  let candidate: unknown;
  try { candidate = JSON.parse(raw); } catch { throw new Error('Offline count authorization is malformed'); }
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) throw new Error('Offline count authorization is malformed');
  const permit = candidate as Partial<OfflineCountPermit>;
  if (permit.version !== 1 || typeof permit.token !== 'string' || permit.token.length < 32
      || !(permit.countId === null || validOfflineCountId(permit.countId))
      || !(permit.catalogCapture === undefined || typeof permit.catalogCapture === 'boolean') || !Number.isSafeInteger(permit.validatedAt) || Number(permit.validatedAt) <= 0
      || !validActor(permit.actor) || !Array.isArray(permit.stores) || !permit.stores.every(store => {
        if (!validActor(store) || typeof (store as Partial<Store>).storeName !== 'string') return false;
        return store.userId === permit.actor!.userId && store.businessId === permit.actor!.businessId;
      }) || !permit.stores.some(store => store.storeId === permit.actor!.storeId)) {
    throw new Error('Offline count authorization is malformed');
  }
  if (!usableOfflinePermit(permit as OfflineCountPermit)) throw new Error('Offline authorization has no permitted workflow');
  return permit as OfflineCountPermit;
}
