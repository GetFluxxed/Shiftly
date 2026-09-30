import type { Actor, Store } from '../api/types';

export type SavedRoute = { pathname: string; params?: Record<string, string> };
const id = '[1-9][0-9]*';
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';

/** A checkpoint is UI state, never evidence of account authority. */
export function workspaceScope(actor: Actor, stores: Store[]): string {
  return JSON.stringify([actor.userId, actor.businessId, actor.storeId, actor.role,
    [...actor.capabilities].sort(), stores.map(s => [s.storeId, s.role, [...s.capabilities].sort()])
      .sort((a, b) => Number(a[0]) - Number(b[0]))]);
}

/** Only known app routes and the one non-secret return parameter may be saved. */
export function savedRoute(path: string, params: Record<string, unknown>, actor: Actor): SavedRoute | null {
  if (typeof path !== 'string' || path.length > 220) return null;
  path = path.replace(/\[(productId|shelfId|countId|lineId|userId|recipeId|logId)\]/g, (match, key: string) =>
    typeof params[key] === 'string' ? String(params[key]) : match);
  const can = (capability: string) => actor.capabilities.includes(capability);
  let allowed = ['/today', '/accounts'].includes(path);
  if (path === '/reports') allowed = can('reports.view') || can('reports.submit');
  if (path === '/store') allowed = ['owner', 'manager'].includes(actor.role);
  if (path === '/heads-up') allowed = ['manager', 'crew', 'production'].includes(actor.role);
  if (/^\/production(\/recipes|\/logs)?$/.test(path)
      || new RegExp(`^/production/(recipes|logs)/${uuid}$`).test(path)) allowed = can('production.view');
  if (path === '/production/recipes/new') allowed = can('production.view') && can('recipes.manage');
  if (path === '/production/run' || path === '/production/review') allowed = can('production.view') && can('production.submit');
  if (/^\/(inventory|catalog|shelves|stock|counts)$/.test(path) || path === '/counts/history'
      || new RegExp(`^/(catalog|shelves|stock)/${uuid}$`).test(path)
      || new RegExp(`^/counts/${uuid}(/review|/line/${uuid})?$`).test(path)) allowed = can('inventory.view');
  if (path === '/catalog/new') allowed = can('inventory.view') && can('catalog.manage');
  if (/^\/team(\/(access|build|invite|assign))?$/.test(path) || new RegExp(`^/team/${id}$`).test(path))
    allowed = ['owner', 'admin', 'manager'].includes(actor.role);
  if (/^\/owner(\/cutover)?$/.test(path) || new RegExp(`^/owner/${id}$`).test(path)) allowed = actor.role === 'owner';
  if (!allowed) return null;
  return { pathname: path, ...(path.startsWith('/counts') && params.returnTo === 'stock' ? { params: { returnTo: 'stock' } } : {}) };
}
