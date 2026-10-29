/** Bounded return context for authenticated app routes. It is UI context, never authority. */
export type AppRoute = { pathname: string; params?: Record<string, string> };
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const positiveId = '[1-9][0-9]*';
const staticRoutes = new Set([
  '/today', '/reports', '/inventory', '/accounts', '/store', '/heads-up', '/time-tracking',
  '/catalog', '/catalog/new', '/catalog/scan', '/catalog/saved-scans', '/shelves', '/stock', '/counts', '/counts/history',
  '/invoices', '/incoming', '/production', '/production/recipes', '/production/recipes/new', '/production/run',
  '/production/review', '/production/logs', '/team', '/team/access', '/team/build', '/team/invite', '/team/assign',
  '/owner', '/owner/cutover',
]);
const entityRoutes = new RegExp(`^/(catalog/${uuid}|catalog/packages/${uuid}|shelves/${uuid}|stock/${uuid}|counts/${uuid}(/review|/line/${uuid})?|invoices/${uuid}(/photo)?|production/(recipes|logs)/${uuid}|team/${positiveId}|owner/${positiveId})$`);
const barcode = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/;
const barcodeTypes = new Set(['ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'code93', 'itf14', 'codabar',
  'org.gs1.EAN-13', 'org.gs1.EAN-8', 'org.gs1.UPC-E', 'org.iso.Code39', 'com.intermec.Code93', 'org.iso.Code128',
  'org.gs1.ITF14', 'Codabar', 'VNBarcodeSymbologyEAN13', 'VNBarcodeSymbologyCode39']);
const maxParents = 12;
const maxLength = 4096;

export function appRoute(pathname: string, params: Record<string, unknown> = {}): AppRoute | null {
  if (typeof pathname !== 'string' || pathname.length > 220) return null;
  pathname = pathname.replace(/\[(productId|shelfId|countId|lineId|invoiceId|recipeId|logId|userId)\]/g, (match, key: string) => {
    const value = params[key];
    if (typeof value === 'string') return value;
    if (key === 'userId' && typeof value === 'number' && Number.isSafeInteger(value) && value > 0) return String(value);
    return match;
  });
  if (!staticRoutes.has(pathname) && !entityRoutes.test(pathname)) return null;
  const safe: Record<string, string> = {};
  if (pathname.startsWith('/counts') && params.returnTo === 'stock') safe.returnTo = 'stock';
  if (pathname.startsWith('/catalog/packages/') && typeof params.barcode === 'string' && barcode.test(params.barcode)) {
    safe.barcode = params.barcode;
    if (typeof params.barcodeType === 'string' && barcodeTypes.has(params.barcodeType)) safe.barcodeType = params.barcodeType;
  }
  return { pathname, ...(Object.keys(safe).length ? { params: safe } : {}) };
}

export function appTrail(value: unknown): AppRoute[] {
  if (typeof value !== 'string' || value.length > maxLength) return [];
  try {
    const entries: unknown = JSON.parse(value);
    if (!Array.isArray(entries) || entries.length > maxParents) return [];
    const result: AppRoute[] = [];
    for (const entry of entries) {
      if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return [];
      const item = entry as Record<string, unknown>;
      if (item.params !== undefined && (!item.params || typeof item.params !== 'object' || Array.isArray(item.params))) return [];
      const frame = appRoute(item.pathname as string, item.params as Record<string, unknown> | undefined);
      if (!frame) return [];
      result.push(frame);
    }
    return result;
  } catch { return []; }
}

function withTrail(route: AppRoute, parents: AppRoute[]): AppRoute {
  const bounded = parents.slice(-maxParents);
  while (JSON.stringify(bounded).length > maxLength) bounded.shift();
  return { ...route, params: { ...route.params, appTrail: JSON.stringify(bounded) } };
}

export function appTarget(current: AppRoute, trail: unknown, target: AppRoute,
  mode: 'open' | 'replace' = 'open', dropParents: number | true = 0, replaceParent?: AppRoute): AppRoute {
  let parents = appTrail(trail);
  const frame = appRoute(current.pathname, current.params);
  if (mode === 'open' && frame && frame.pathname !== target.pathname) parents.push(frame);
  if (mode === 'replace' && dropParents === true) parents = [];
  else if (mode === 'replace' && typeof dropParents === 'number' && dropParents > 0)
    parents = parents.slice(0, Math.max(0, parents.length - dropParents));
  if (mode === 'replace' && replaceParent) {
    const canonicalParent = appRoute(replaceParent.pathname, replaceParent.params);
    if (canonicalParent) parents = [canonicalParent];
  }
  if (mode === 'replace') {
    while (parents.at(-1)?.pathname === target.pathname) parents.pop();
  }
  return withTrail(appRoute(target.pathname, target.params) || { pathname: '/today' }, parents);
}

export function appParent(trail: unknown, fallback: AppRoute): AppRoute {
  const parents = appTrail(trail);
  return withTrail(parents.pop() || fallback, parents);
}

export function appBackLabel(path: string): string {
  const labels: Record<string, string> = {
    '/today': 'Back to Today', '/reports': 'Back to reports', '/inventory': 'Back to inventory', '/accounts': 'Back to account',
    '/store': 'Back to store', '/heads-up': 'Back to Heads Up', '/time-tracking': 'Back to Time Tracking',
    '/catalog': 'Back to catalog', '/catalog/new': 'Back to new product', '/catalog/scan': 'Back to scanner',
    '/catalog/saved-scans': 'Back to saved scans', '/shelves': 'Back to Open Shelves', '/stock': 'Back to current inventory',
    '/invoices': 'Back to invoices', '/incoming': 'Back to incoming inventory', '/counts': 'Back to count inventory',
    '/counts/history': 'Back to count history', '/production': 'Back to production', '/production/recipes': 'Back to recipes',
    '/production/recipes/new': 'Back to new recipe', '/production/run': 'Back to production run', '/production/review': 'Back to production review',
    '/production/logs': 'Back to production logs', '/team': 'Back to team', '/team/build': 'Back to build team',
    '/team/invite': 'Back to invite', '/team/assign': 'Back to assign team member', '/team/access': 'Back to store access',
    '/owner': 'Back to owner tools', '/owner/cutover': 'Back to store sign-in',
  };
  if (labels[path]) return labels[path];
  if (path.startsWith('/invoices/')) return 'Back to invoice';
  if (path.startsWith('/catalog/packages/')) return 'Back to packages';
  if (path.startsWith('/catalog/')) return 'Back to product';
  if (path.startsWith('/shelves/')) return 'Back to shelf';
  if (path.startsWith('/stock/')) return 'Back to stock details';
  if (path.endsWith('/review')) return 'Back to count review';
  if (path.includes('/line/')) return 'Back to count entry';
  if (path.startsWith('/counts/')) return 'Back to count entries';
  if (path.startsWith('/production/recipes/')) return 'Back to recipe';
  if (path.startsWith('/production/logs/')) return 'Back to production log';
  if (path.startsWith('/team/')) return 'Back to team';
  if (path.startsWith('/owner/')) return 'Back to owner tools';
  return 'Back';
}
