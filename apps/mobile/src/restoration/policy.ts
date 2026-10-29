import type { Actor, Store } from '../api/types';
import { appRoute, appTrail, type AppRoute } from '../navigation/routes';

export type SavedRoute = { pathname: string; params?: Record<string, string> };
const id = '[1-9][0-9]*';
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
/** A checkpoint is UI state, never evidence of account authority. */
export function workspaceScope(actor: Actor, stores: Store[]): string {
  return JSON.stringify([actor.userId, actor.businessId, actor.storeId, actor.role,
    [...actor.capabilities].sort(), stores.map(s => [s.storeId, s.role, [...s.capabilities].sort()])
      .sort((a, b) => Number(a[0]) - Number(b[0]))]);
}

function authorizedRoute(path: string, actor: Actor): boolean {
  const can = (capability: string) => actor.capabilities.includes(capability);
  const canReceive = ['manager', 'owner'].includes(actor.role)
    && ['inventory.view', 'receipts.draft', 'receipts.post'].every(can);
  if (['/today', '/accounts'].includes(path)) return true;
  if (path === '/incoming' || path === '/invoices' || new RegExp(`^/invoices/${uuid}(/photo)?$`).test(path)) return canReceive;
  if (path === '/reports') return can('reports.view') || can('reports.submit');
  if (path === '/store') return ['owner', 'manager'].includes(actor.role);
  if (path === '/time-tracking') return actor.role === 'owner';
  if (path === '/heads-up') return ['manager', 'crew', 'production'].includes(actor.role);
  if (/^\/production(\/recipes|\/logs)?$/.test(path) || new RegExp(`^/production/(recipes|logs)/${uuid}$`).test(path)) return can('production.view');
  if (path === '/production/recipes/new') return can('production.view') && can('recipes.manage');
  if (path === '/production/run' || path === '/production/review') return can('production.view') && can('production.submit');
  if (path === '/catalog/new' || path === '/catalog/saved-scans') return can('inventory.view') && can('catalog.manage');
  if (/^\/(inventory|catalog|shelves|stock|counts)$/.test(path) || path === '/counts/history' || path === '/catalog/scan' || path === '/catalog/saved-scans'
      || new RegExp(`^/(catalog|shelves|stock)/${uuid}$`).test(path) || new RegExp(`^/catalog/packages/${uuid}$`).test(path)
      || new RegExp(`^/counts/${uuid}(/review|/line/${uuid})?$`).test(path)) return can('inventory.view');
  if (/^\/team(\/(access|build|invite|assign))?$/.test(path) || new RegExp(`^/team/${id}$`).test(path)) return ['owner', 'admin', 'manager'].includes(actor.role);
  if (/^\/owner(\/cutover)?$/.test(path) || new RegExp(`^/owner/${id}$`).test(path)) return actor.role === 'owner';
  return false;
}

function safeParents(value: unknown, actor: Actor): AppRoute[] {
  return appTrail(value).filter(frame => authorizedRoute(frame.pathname, actor));
}

/** Only known app routes and bounded non-secret navigation metadata may be saved. */
export function savedRoute(path: string, params: Record<string, unknown>, actor: Actor): SavedRoute | null {
  if (typeof path !== 'string' || path.length > 220) return null;
  path = path.replace(/\[(productId|shelfId|countId|lineId|userId|recipeId|logId|invoiceId)\]/g, (match, key: string) =>
    typeof params[key] === 'string' ? String(params[key]) : match);
  if (!authorizedRoute(path, actor)) return null;
  const route = appRoute(path, params);
  if (!route) return { pathname: path };
  const usesAppTrail = typeof params.appTrail === 'string';
  const parents = safeParents(usesAppTrail ? params.appTrail : params.inventoryTrail, actor);
  const trailKey = usesAppTrail ? 'appTrail' : 'inventoryTrail';
  const safe = { ...route.params, ...(parents.length ? { [trailKey]: JSON.stringify(parents) } : {}) };
  return { pathname: path, ...(Object.keys(safe).length ? { params: safe } : {}) };
}
