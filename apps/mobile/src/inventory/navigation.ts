import { appBackLabel, appParent, appRoute, appTarget, appTrail, type AppRoute } from '../navigation/routes';

export type InventoryRoute = AppRoute;
export const inventoryBackLabel = appBackLabel;
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const inventoryRoutes = new RegExp(`^/(today|inventory|catalog|catalog/new|catalog/scan|catalog/saved-scans|catalog/${uuid}|catalog/packages/${uuid}|invoices|invoices/${uuid}(/photo)?|incoming|shelves|shelves/${uuid}|stock|stock/${uuid}|counts|counts/history|counts/${uuid}(/review|/line/${uuid})?)$`);

export function inventoryRoute(pathname: string, params: Record<string, unknown> = {}): InventoryRoute | null {
  const route = appRoute(pathname, params);
  return route && inventoryRoutes.test(route.pathname) ? route : null;
}

export function inventoryTrail(value: unknown): InventoryRoute[] {
  const routes = appTrail(value);
  return routes.every(route => inventoryRoutes.test(route.pathname)) ? routes : [];
}

function legacyTrail(route: AppRoute): InventoryRoute {
  const { appTrail: trail, ...params } = route.params || {};
  return { ...route, params: { ...params, inventoryTrail: trail || '[]' } };
}

export function inventoryTarget(current: InventoryRoute, trail: unknown, target: InventoryRoute,
  mode: 'open' | 'replace' = 'open', dropParents: number | true = 0): InventoryRoute {
  return legacyTrail(appTarget(inventoryRoute(current.pathname, current.params) || { pathname: '/inventory' }, trail,
    inventoryRoute(target.pathname, target.params) || { pathname: '/inventory' }, mode, dropParents));
}

export function inventoryParent(trail: unknown, fallback: InventoryRoute): InventoryRoute {
  return legacyTrail(appParent(trail, fallback));
}
