import type { Actor, Store } from '../../src/api/types';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const C = '33333333-3333-4333-8333-333333333333';
const D = '44444444-4444-4444-8444-444444444444';

export const NAVIGATION_FIXTURE_IDS = Object.freeze({
  productId: A, packageId: B, shelfId: C, countId: B, lineId: D,
  invoiceId: C, invoiceLineId: D, recipeId: B, revisionId: C, logId: D, userId: 2,
});

export type NavigationFixtureRole = 'owner' | 'admin' | 'manager' | 'production' | 'crew';
export type FixtureRequest = { path: string; method: string };
type SendOptions = { method?: string; body?: unknown; query?: Record<string, unknown> };

const roleCapabilities: Record<NavigationFixtureRole, string[]> = {
  owner: ['reports.view', 'reports.submit', 'inventory.view', 'catalog.manage', 'counts.submit', 'counts.approve',
    'production.view', 'production.submit', 'production.manage', 'recipes.manage', 'memberships.manage',
    'configuration.manage', 'receipts.draft', 'receipts.post'],
  admin: ['reports.view', 'reports.submit', 'inventory.view', 'catalog.manage', 'counts.submit', 'counts.approve',
    'production.view', 'production.submit', 'production.manage', 'recipes.manage', 'memberships.manage',
    'configuration.manage', 'receipts.draft', 'receipts.post'],
  manager: ['reports.view', 'reports.submit', 'inventory.view', 'catalog.manage', 'counts.submit', 'counts.approve',
    'production.view', 'production.submit', 'recipes.manage', 'memberships.manage', 'receipts.draft', 'receipts.post'],
  production: ['reports.view', 'reports.submit', 'inventory.view', 'production.view', 'production.submit'],
  crew: ['reports.view', 'reports.submit', 'inventory.view', 'counts.submit'],
};

const product = { id: A, name: 'Fixture vanilla base', sku: 'VAN-BASE', baseUnit: 'kg', active: true, version: 3,
  containerAmount: '5', containerLabelAmount: '5', containerLabelUnit: 'kg', canonicalProductId: null };
const packageItem = { id: B, productId: A, name: 'Five kilogram tub', amount: '5', labelAmount: '5', labelUnit: 'kg',
  kind: 'container', active: true, version: 2, isDefault: true, containedPackageId: null, containedCount: null, barcodes: ['000111222333'] };
const shelf = { id: C, name: 'Walk-in freezer', storeId: 1, version: 2 };
const count = { id: B, storeId: 1, businessDate: '2026-10-29', state: 'draft', version: 4,
  startedAt: '2026-10-29T08:00:00.000Z', startedBy: 'Fixture Owner', reviewedAt: null, reviewedBy: null,
  postedAt: null, postedBy: null, totalLines: 1, countedLines: 1, totalProducts: 1, countedProducts: 1,
  configurationChanged: false, catalogProductsAvailable: false };
const countLine = { id: D, productId: A, name: product.name, sku: product.sku, baseUnit: 'kg', containerAmount: '5', packages: [packageItem],
  shelfId: C, shelfName: shelf.name, quantity: '8.5', entry: { mode: 'total', amount: '8.5', unit: 'kg' }, version: 2,
  observedAt: '2026-10-29T08:15:00.000Z', observedBy: 'Fixture Owner' };
const stock = { productId: A, name: product.name, sku: product.sku, baseUnit: 'kg', containerAmount: '5', packages: [packageItem],
  quantity: '8.5', active: true, countId: B, countedOn: '2026-10-29', updatedAt: '2026-10-29T08:15:00.000Z',
  lastCountedAt: '2026-10-29T08:15:00.000Z', lastMovement: 'count', stockVersion: 2 };
const recipe = { id: B, name: 'Fixture vanilla gelato', version: 2, revisionId: C, yieldAmount: '10', yieldUnit: 'pans',
  instructions: 'Blend, rest, and churn.', ingredients: [{ productId: A, name: product.name, sku: product.sku, amount: '2', unit: 'kg',
    baseUnit: 'kg', baseAmount: '2', currentBaseUnit: 'kg', section: 'base' }], referenceIngredients: [] };
const deduction = { productId: A, name: product.name, recipeAmount: '2', allowanceAmount: '0.02', quantity: '2.02',
  baseUnit: 'kg', balance: '8.5', remaining: '6.48' };
const logEntry = { recipeId: B, revisionId: C, name: recipe.name, yieldAmount: '10', yieldUnit: 'pans', batches: 1 };
const productionLog = { id: D, businessDate: '2026-10-29', state: 'confirmed', createdAt: '2026-10-29T09:00:00.000Z',
  createdBy: 'Fixture Owner', entries: [logEntry], ingredients: [deduction] };
const invoiceLine = { id: D, description: 'Vanilla base delivery', sku: product.sku, productId: A, packageId: B, quantity: '2',
  unit: 'package', received: false, productName: product.name, baseUnit: 'kg', normalizedQuantity: '10',
  packageName: packageItem.name, needsCatalogReview: false };
const invoice = { id: C, supplier: 'Fixture Dairy', invoiceNumber: 'INV-1001', state: 'draft', version: 2, lineCount: 1,
  receivedCount: 0, updatedAt: '2026-10-29T09:30:00.000Z', storeId: 1, lines: [invoiceLine], needsCountReview: false,
  needsCatalogReview: false, photoReadingAvailable: true, createdAt: '2026-10-29T09:00:00.000Z', baselineCountId: B };

function management(role: NavigationFixtureRole) {
  const person = { userId: 2, username: 'fixture.manager', displayName: 'Fixture Manager', accountState: 'active',
    businessRole: 'admin', businessState: 'active', businessCapabilities: ['memberships.manage', 'catalog.manage'],
    canDelegate: true, canRevokeBusiness: true, canTransfer: true, canSuspend: true };
  return { storeId: 1, members: [{ ...person, role: 'manager', membershipState: 'active',
    capabilities: roleCapabilities.manager, canEdit: true, canReissue: false, lastSignInAt: '2026-10-29T07:00:00.000Z' }],
  directory: [person], roles: [
    { role: 'crew', included: ['reports.submit'], optional: ['reports.view', 'inventory.view', 'counts.submit'] },
    { role: 'production', included: ['production.view'], optional: ['production.submit', 'reports.view'] },
    { role: 'manager', included: ['inventory.view', 'reports.view'], optional: ['catalog.manage', 'memberships.manage'] },
    { role: 'admin', included: [], optional: roleCapabilities.admin },
  ], isOwner: role === 'owner', businessCapabilities: ['memberships.manage', 'catalog.manage'], sharedCrewEnabled: false };
}

export function createNavigationFixture({ role = 'owner', signedOut = false }: {
  role?: NavigationFixtureRole; signedOut?: boolean;
} = {}) {
  const actor: Actor = { userId: 1, businessId: 1, storeId: 1, username: `fixture.${role}`,
    displayName: `Fixture ${role[0]!.toUpperCase()}${role.slice(1)}`, role, provenance: 'named', capabilities: [...roleCapabilities[role]] };
  const stores: Store[] = [{ ...actor, storeName: 'Fixture Store' }];
  const requests: FixtureRequest[] = [];
  const unexpectedRequests: string[] = [];

  const send = async <T,>(rawPath: string, options: SendOptions = {}): Promise<T> => {
    const path = rawPath.split('?')[0]!;
    const method = options.method || 'GET';
    requests.push({ path, method });
    const page = (items: unknown[]) => ({ items, nextCursor: null });
    let value: unknown;

    if (path === '/accounts/status') value = signedOut ? { authenticated: false } : { authenticated: true, actor, stores };
    else if (path === '/accounts/management') value = management(role);
    else if (path === '/accounts/memberships') value = method === 'GET' ? { storeId: 1, items: management(role).members, nextCursor: null } : { saved: true };
    else if (path === '/accounts/business-memberships') value = method === 'GET' ? { businessId: 1, items: management(role).directory, nextCursor: null } : { saved: true };
    else if (path === '/accounts/invitations' || path === '/accounts/invitations/reissue') value = { userId: 2, token: 'fixture-invitation-code', expiresIn: 86400 };
    else if (path === '/accounts/suspend') value = { saved: true };
    else if (path === '/reports') value = method === 'POST' ? { date: '2026-10-29T10:00:00.000Z', status: 'received' } : { reports: [{
      id: A, employee: 'Fixture Crew', shift: 'closing', notes: 'Freezer checked and prep complete.', date: '2026-10-29T07:00:00.000Z',
      status: 'ready', storeId: 1, storeName: 'Fixture Store', briefing: { summary: 'Prep is complete.', wins: ['Freezer checked'], risks: [], follow_up: 'Open normally.' },
    }] };
    else if (path === '/heads-up') value = { message: 'Fixture store opens on schedule.', version: 2, updatedAt: '2026-10-29T07:30:00.000Z', updatedBy: 'Fixture Manager' };
    else if (path === '/inventory/products') value = method === 'POST' ? product : page([product]);
    else if (path === `/inventory/products/${A}`) value = product;
    else if (path === '/inventory/products/lookup') value = { sku: product.sku, product, package: packageItem };
    else if (path === `/inventory/products/${A}/measurement`) value = { product, canChangeUnit: true, issues: [], recipeCount: 1 };
    else if (path === `/inventory/products/${A}/packages`) value = method === 'POST' ? packageItem : page([packageItem]);
    else if (path.startsWith(`/inventory/products/${A}/packages/${B}`)) value = packageItem;
    else if (path.startsWith(`/inventory/products/${A}/`)) value = product;
    else if (path === '/inventory/shelves') value = method === 'POST' ? shelf : page([shelf]);
    else if (path === `/inventory/shelves/${C}`) value = { ...shelf, products: page([{ ...product, storeQuantity: '8.5' }]) };
    else if (path.startsWith(`/inventory/shelves/${C}/products/`)) value = { shelf, productId: A, assigned: true };
    else if (path === '/inventory/count-status') value = { storeId: 1, openCount: count, lastCount: null };
    else if (path === '/inventory/counts') value = method === 'POST' ? count : page([count]);
    else if (path === `/inventory/counts/${B}`) value = count;
    else if (path === `/inventory/counts/${B}/lines`) value = page([countLine]);
    else if (path === `/inventory/counts/${B}/lines/${D}`) value = method === 'POST' ? { line: countLine, count } : countLine;
    else if (path === `/inventory/counts/${B}/comparison`) value = page([{ productId: A, name: product.name, sku: product.sku,
      baseUnit: 'kg', containerAmount: '5', packages: [packageItem], previousQuantity: '7', quantity: '8.5', difference: '1.5', locations: 1, missing: 0 }]);
    else if (path.startsWith(`/inventory/counts/${B}/`)) value = count;
    else if (path === '/inventory/stock') value = page([stock]);
    else if (path === `/inventory/stock/${A}`) value = { ...stock, locations: page([countLine]) };
    else if (path === '/inventory/invoices') value = method === 'POST' ? invoice : { ...page([invoice]), photoReadingAvailable: true };
    else if (path === `/inventory/invoices/${C}`) value = invoice;
    else if (path === `/inventory/invoices/${C}/photo-analysis`) value = { id: D, state: 'ready', canRetry: false, message: null,
      supplier: invoice.supplier, invoiceNumber: invoice.invoiceNumber, lines: [{ description: invoiceLine.description, sku: invoiceLine.sku,
        quantity: invoiceLine.quantity, unit: invoiceLine.unit, productId: A, packageId: B }] };
    else if (path.startsWith(`/inventory/invoices/${C}/`)) value = invoice;
    else if (path === '/inventory/incoming') value = { ...page([{ productId: A, name: product.name, baseUnit: 'kg', currentQuantity: '8.5',
      incomingQuantity: '10', receivedQuantity: '0', projectedQuantity: '18.5' }]), unmatchedCount: 0, needsCountReview: false, needsCatalogReview: false };
    else if (path === '/production/recipes') value = method === 'POST' ? recipe : page([recipe]);
    else if (path === `/production/recipes/${B}`) value = recipe;
    else if (path === '/production/logs') value = method === 'POST' ? productionLog : page([productionLog]);
    else if (path === `/production/logs/${D}`) value = productionLog;
    else if (path === `/production/logs/${D}/reverse`) value = { ...productionLog, state: 'reversed', reversalReason: 'Fixture reversal' };
    else if (path === '/production/preview') value = { entries: [logEntry], deductions: [deduction], canConfirm: true, issues: [] };
    else if (path === '/production/forecast') value = { status: 'unavailable', message: 'Forecast is unavailable in this local fixture.', generatedAt: null, item: null };
    else {
      unexpectedRequests.push(`${method} ${path}`);
      throw new Error(`Unexpected full-navigation fixture request: ${method} ${path}`);
    }
    return value as T;
  };

  return { actor, stores, send, requests, unexpectedRequests };
}
