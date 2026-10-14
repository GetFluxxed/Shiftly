/** Inventory-only breadcrumbs: bounded UI context, never account authority. */
export type InventoryRoute = { pathname: string; params?: Record<string, string> };
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const routes = new RegExp(`^/(inventory|catalog|catalog/new|catalog/scan|catalog/${uuid}|catalog/packages/${uuid}|shelves|shelves/${uuid}|stock|stock/${uuid}|counts|counts/history|counts/${uuid}(/review|/line/${uuid})?)$`);
const barcode = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/;
const barcodeTypes = new Set(['ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'code93', 'itf14', 'codabar',
  'org.gs1.EAN-13', 'org.gs1.EAN-8', 'org.gs1.UPC-E', 'org.iso.Code39', 'com.intermec.Code93', 'org.iso.Code128',
  'org.gs1.ITF14', 'Codabar', 'VNBarcodeSymbologyEAN13', 'VNBarcodeSymbologyCode39']);
const maxParents = 12;
const maxLength = 4096;

export function inventoryRoute(pathname: string, params: Record<string, unknown> = {}): InventoryRoute | null {
  if (typeof pathname !== 'string' || pathname.length > 220) return null;
  pathname = pathname.replace(/\[(productId|shelfId|countId|lineId)\]/g, (match, key: string) =>
    typeof params[key] === 'string' ? String(params[key]) : match);
  if (!routes.test(pathname)) return null;
  const safe: Record<string, string> = {};
  if (pathname.startsWith('/counts') && params.returnTo === 'stock') safe.returnTo = 'stock';
  if (pathname.startsWith('/catalog/packages/') && typeof params.barcode === 'string' && barcode.test(params.barcode)) {
    safe.barcode = params.barcode;
    if (typeof params.barcodeType === 'string' && barcodeTypes.has(params.barcodeType)) safe.barcodeType = params.barcodeType;
  }
  return { pathname, ...(Object.keys(safe).length ? { params: safe } : {}) };
}

export function inventoryTrail(value: unknown): InventoryRoute[] {
  if (typeof value !== 'string' || value.length > maxLength) return [];
  try {
    const entries: unknown = JSON.parse(value);
    if (!Array.isArray(entries) || entries.length > maxParents) return [];
    const result: InventoryRoute[] = [];
    for (const entry of entries) {
      if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return [];
      const item = entry as Record<string, unknown>;
      if (item.params !== undefined && (!item.params || typeof item.params !== 'object' || Array.isArray(item.params))) return [];
      const frame = inventoryRoute(item.pathname as string, item.params as Record<string, unknown> | undefined);
      if (!frame) return [];
      result.push(frame);
    }
    return result;
  } catch { return []; }
}

function withTrail(route: InventoryRoute, parents: InventoryRoute[]): InventoryRoute {
  const bounded = parents.slice(-maxParents);
  while (JSON.stringify(bounded).length > maxLength) bounded.shift();
  return { ...route, params: { ...route.params, inventoryTrail: JSON.stringify(bounded) } };
}

export function inventoryTarget(current: InventoryRoute, trail: unknown, target: InventoryRoute,
  mode: 'open' | 'replace' = 'open', dropParents = 0): InventoryRoute {
  let parents = inventoryTrail(trail);
  const frame = inventoryRoute(current.pathname, current.params);
  if (mode === 'open' && frame && frame.pathname !== target.pathname) parents.push(frame);
  if (mode === 'replace' && dropParents > 0) parents = parents.slice(0, Math.max(0, parents.length - dropParents));
  // Replacing a completed form must not leave that destination as its own parent.
  // Forward links retain the immediate origin, even when revisiting an earlier page.
  if (mode === 'replace') {
    const existing = parents.findIndex(frame => frame.pathname === target.pathname);
    if (existing >= 0) parents = parents.slice(0, existing);
  }
  return withTrail(inventoryRoute(target.pathname, target.params) || { pathname: '/inventory' }, parents);
}

export function inventoryParent(trail: unknown, fallback: InventoryRoute): InventoryRoute {
  const parents = inventoryTrail(trail);
  return withTrail(parents.pop() || fallback, parents);
}

export function inventoryBackLabel(path: string): string {
  const labels: Record<string, string> = {
    '/inventory': 'Back to inventory', '/catalog': 'Back to catalog', '/catalog/new': 'Back to new product',
    '/catalog/scan': 'Back to scanner', '/shelves': 'Back to Open Shelves', '/stock': 'Back to current inventory',
    '/counts': 'Back to count inventory', '/counts/history': 'Back to count history',
  };
  if (labels[path]) return labels[path];
  if (path.startsWith('/catalog/packages/')) return 'Back to packages';
  if (path.startsWith('/catalog/')) return 'Back to product';
  if (path.startsWith('/shelves/')) return 'Back to shelf';
  if (path.startsWith('/stock/')) return 'Back to stock details';
  if (path.endsWith('/review')) return 'Back to count review';
  if (path.includes('/line/')) return 'Back to count entry';
  return 'Back to count entries';
}
