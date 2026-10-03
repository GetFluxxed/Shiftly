import { ApiError } from '../api/client';
import type { RequestOptions } from '../api/types';

export const units = { each: 'Each / item', g: 'Grams', kg: 'Kilograms', ml: 'Millilitres (legacy)', l: 'Litres (legacy)' } as const;
export const stockUnits = ['each', 'g', 'kg'] as const;
export type StockUnit = typeof stockUnits[number];
export type ContainerUnit = StockUnit | 'lb';
export type Unit = keyof typeof units;
export interface Product { id: string; name: string; sku: string; baseUnit: Unit; active: boolean; version: number; containerAmount: string | null; containerLabelAmount?: string | null; containerLabelUnit?: ContainerUnit | null; canonicalProductId?: string | null }
export type PackageKind = 'container' | 'box' | 'case';
export interface Package { id: string; productId: string; name: string; amount: string; labelAmount?: string | null; labelUnit?: ContainerUnit | null; kind: PackageKind; active: boolean; version: number; isDefault: boolean; containedPackageId: string | null; containedCount: number | null; barcodes: string[] }
export type PackageInput = { name: string; kind: PackageKind; amount?: string; amountUnit?: ContainerUnit; containedPackageId?: string | null; containedCount?: number | null; barcode?: string; barcodeType?: string };
export interface CombinePreview { source: Product; target: Product; sourceVersion: number; targetVersion: number; packages: Package[]; shelves: number; canCombine: boolean; issues: string[] }
export interface MeasurementContext { product: Product; canChangeUnit: boolean; issues: string[]; recipeCount: number }
export interface MeasurementInput { baseUnit: StockUnit; containerAmount: string | null; containerUnit?: ContainerUnit; acknowledgeRecipes: boolean }
export interface Shelf { id: string; name: string; storeId: number; version: number }
export interface ShelfProduct extends Product { storeQuantity: string | null }
export interface Page<T> { items: T[]; nextCursor: string | null }
export interface ShelfDetail extends Shelf { products: Page<ShelfProduct> }
export type Request = <T>(path: string, options?: RequestOptions) => Promise<T>;
export type ProductInput = { name: string; sku: string; baseUnit: StockUnit; containerAmount?: string | null; containerUnit?: ContainerUnit; barcodeType?: string };
const idPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function validId(id: unknown): id is string { return typeof id === 'string' && idPattern.test(id); }
function verify(condition: unknown): asserts condition {
  if (!condition) throw new ApiError('The inventory response could not be verified. Please reload.');
}
function record(value: unknown): asserts value is Record<string, unknown> {
  verify(value && typeof value === 'object');
}
function validLabelAmount(amount: unknown, unit: unknown): boolean {
  if (typeof amount !== 'string' || !['each', 'g', 'kg', 'lb'].includes(String(unit)) || Number(amount) <= 0) return false;
  if (unit === 'each') return /^\d{1,9}$/.test(amount);
  return new RegExp(`^\\d{1,9}(?:\\.\\d{1,${unit === 'lb' ? 6 : 9}})?$`).test(amount);
}
function product(value: unknown): Product {
  record(value);
  verify(validId(value.id) && typeof value.name === 'string' && typeof value.sku === 'string'
    && typeof value.baseUnit === 'string' && Object.hasOwn(units, value.baseUnit)
    && typeof value.active === 'boolean' && Number.isSafeInteger(value.version) && Number(value.version) > 0);
  const amount = value.containerAmount ?? null, labelAmount = value.containerLabelAmount ?? null, labelUnit = value.containerLabelUnit ?? null;
  verify(amount === null || (typeof amount === 'string' && /^\d{1,9}(?:\.\d{1,9})?$/.test(amount) && Number(amount) > 0
    && (value.baseUnit !== 'each' || Number.isInteger(Number(amount)))));
  verify((labelAmount === null) === (labelUnit === null) && (labelAmount === null || validLabelAmount(labelAmount, labelUnit)));
  verify(value.canonicalProductId === undefined || value.canonicalProductId === null || validId(value.canonicalProductId));
  return { ...value, containerAmount: amount, containerLabelAmount: labelAmount, containerLabelUnit: labelUnit } as unknown as Product;
}
export function parsePackage(value: unknown): Package {
  record(value); verify(validId(value.id) && validId(value.productId) && typeof value.name === 'string'
    && typeof value.amount === 'string' && /^\d{1,15}(?:\.\d{1,9})?$/.test(value.amount) && Number(value.amount) > 0
    && ['container', 'box', 'case'].includes(String(value.kind)) && typeof value.active === 'boolean'
    && Number.isSafeInteger(value.version) && Number(value.version) > 0 && typeof value.isDefault === 'boolean'
    && (value.containedPackageId === null || validId(value.containedPackageId))
    && (value.containedCount === null || (Number.isSafeInteger(value.containedCount) && Number(value.containedCount) >= 1 && Number(value.containedCount) <= 1_000_000))
    && Array.isArray(value.barcodes) && value.barcodes.every(code => typeof code === 'string' && code.length <= 64));
  verify((value.containedPackageId === null) === (value.containedCount === null));
  const labelAmount = value.labelAmount ?? null, labelUnit = value.labelUnit ?? null;
  verify((labelAmount === null) === (labelUnit === null) && (labelAmount === null || validLabelAmount(labelAmount, labelUnit)));
  return { ...value, labelAmount, labelUnit } as unknown as Package;
}
function shelf(value: unknown): Shelf {
  record(value);
  verify(validId(value.id) && typeof value.name === 'string' && Number.isSafeInteger(value.version)
    && Number(value.version) > 0 && Number.isSafeInteger(value.storeId) && Number(value.storeId) > 0);
  return value as unknown as Shelf;
}
function shelfProduct(value: unknown): ShelfProduct {
  const parsed = product(value); record(value);
  verify(value.storeQuantity === null || (typeof value.storeQuantity === 'string' && /^\d{1,15}(?:\.\d{1,9})?$/.test(value.storeQuantity)));
  return { ...parsed, storeQuantity: value.storeQuantity as string | null };
}
function catalogCursor(value: unknown): boolean {
  return typeof value === 'string' && value.length <= 1200 && /^p1\.[A-Za-z0-9_-]+$/.test(value);
}
function page<T>(value: unknown, parse: (item: unknown) => T, cursor: (value: unknown) => boolean = validId): Page<T> {
  record(value); verify(Array.isArray(value.items) && value.items.length <= 40 && (value.nextCursor === null || cursor(value.nextCursor)));
  return { items: value.items.map(parse), nextCursor: value.nextCursor as string | null };
}
function pathId(id: string) { verify(validId(id)); return id; }
const recovery = 'We could not confirm this change. Retry the same unchanged form to check its saved result, or refresh the catalog or shelf before making a different change.';

// Correlation IDs only, never credentials. The server scopes and deduplicates them.
function requestId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const n = Math.floor(Math.random() * 16); return (c === 'x' ? n : (n & 3) | 8).toString(16);
  });
}
export class MutationIdentity {
  private last: { payload: string; id: string } | null = null;
  for(path: string, body: Record<string, unknown>): string {
    const payload = JSON.stringify([path, body]);
    if (this.last?.payload !== payload) this.last = { payload, id: requestId() };
    return this.last.id;
  }
}
export function inventoryApi(request: Request) {
  const write = (path: string, body: Record<string, unknown>, identity: MutationIdentity) =>
    request<unknown>(path, { method: 'POST', body: { ...body, requestId: identity.for(path, body) }, uncertainMessage: recovery });
  return {
    products: async (query = '', state = 'active', after = '') => page(await request('/inventory/products', { query: { q: query, state, ...(after ? { after } : {}) } }), product, catalogCursor),
    product: async (id: string) => product(await request(`/inventory/products/${pathId(id)}`)),
    lookupProduct: async (sku: string, barcodeType?: string): Promise<{ sku: string; product: Product | null; package: Package | null }> => {
      const value = await request<unknown>('/inventory/products/lookup', { query: { sku, ...(barcodeType ? { barcodeType } : {}) } });
      record(value);
      verify(typeof value.sku === 'string' && /^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$/.test(value.sku));
      // Only an explicit null is a verified missing product. Errors never open creation.
      return { sku: value.sku, product: value.product === null ? null : product(value.product), package: value.package === null || value.package === undefined ? null : parsePackage(value.package) };
    },
    createProduct: async (fields: ProductInput, identity: MutationIdentity) => product(await write('/inventory/products', fields, identity)),
    editProduct: async (item: Product, name: string, sku: string, identity: MutationIdentity, containerAmount = item.containerLabelAmount ?? item.containerAmount, containerUnit: ContainerUnit = item.containerLabelUnit ?? item.baseUnit as ContainerUnit) => product(await write(`/inventory/products/${pathId(item.id)}`, { name, sku, containerAmount, ...(containerAmount ? { containerUnit } : {}), version: item.version }, identity)),
    measurement: async (id: string): Promise<MeasurementContext> => {
      const value = await request<unknown>(`/inventory/products/${pathId(id)}/measurement`); record(value);
      verify(typeof value.canChangeUnit === 'boolean' && Array.isArray(value.issues) && value.issues.length <= 10
        && value.issues.every(issue => typeof issue === 'string' && issue.length <= 1000)
        && Number.isSafeInteger(value.recipeCount) && Number(value.recipeCount) >= 0);
      const item = product(value.product); verify(item.id === id);
      return { product: item, canChangeUnit: value.canChangeUnit, issues: value.issues as string[], recipeCount: Number(value.recipeCount) };
    },
    changeMeasurement: async (item: Product, fields: MeasurementInput, identity: MutationIdentity) =>
      product(await write(`/inventory/products/${pathId(item.id)}/measurement`, { ...fields, version: item.version }, identity)),
    productState: async (item: Product, active: boolean, identity: MutationIdentity) => product(await write(`/inventory/products/${pathId(item.id)}/state`, { active, version: item.version }, identity)),
    packages: async (productId: string) => page(await request(`/inventory/products/${pathId(productId)}/packages`), parsePackage),
    createPackage: async (productId: string, fields: PackageInput, identity: MutationIdentity) => parsePackage(await write(`/inventory/products/${pathId(productId)}/packages`, fields, identity)),
    editPackage: async (item: Package, fields: PackageInput, identity: MutationIdentity) => parsePackage(await write(`/inventory/products/${pathId(item.productId)}/packages/${pathId(item.id)}`, { ...fields, version: item.version }, identity)),
    packageState: async (item: Package, active: boolean, identity: MutationIdentity) => parsePackage(await write(`/inventory/products/${pathId(item.productId)}/packages/${pathId(item.id)}/state`, { active, version: item.version }, identity)),
    combinePreview: async (sourceId: string, targetProductId: string): Promise<CombinePreview> => {
      const value = await request<unknown>(`/inventory/products/${pathId(sourceId)}/combine-preview`, { query: { targetProductId: pathId(targetProductId) } }); record(value);
      verify(Number.isSafeInteger(value.sourceVersion) && Number(value.sourceVersion) > 0 && Number.isSafeInteger(value.targetVersion) && Number(value.targetVersion) > 0 && Number.isSafeInteger(value.shelves) && Number(value.shelves) >= 0 && typeof value.canCombine === 'boolean' && Array.isArray(value.issues) && value.issues.every(item => typeof item === 'string') && Array.isArray(value.packages) && value.packages.length <= 40);
      return { source: product(value.source), target: product(value.target), sourceVersion: Number(value.sourceVersion), targetVersion: Number(value.targetVersion), packages: value.packages.map(parsePackage), shelves: Number(value.shelves), canCombine: value.canCombine, issues: value.issues as string[] };
    },
    combine: async (sourceId: string, preview: CombinePreview, identity: MutationIdentity) => product(await write(`/inventory/products/${pathId(sourceId)}/combine`, { targetProductId: preview.target.id, sourceVersion: preview.sourceVersion, targetVersion: preview.targetVersion, confirmed: true }, identity)),
    shelves: async (after = '') => page(await request('/inventory/shelves', { query: after ? { after } : {} }), shelf),
    shelf: async (id: string, after = ''): Promise<ShelfDetail> => {
      const value = await request<unknown>(`/inventory/shelves/${pathId(id)}`, { query: after ? { after } : {} });
      const parsed = shelf(value); record(value); return { ...parsed, products: page(value.products, shelfProduct) };
    },
    createShelf: async (name: string, identity: MutationIdentity) => shelf(await write('/inventory/shelves', { name }, identity)),
    editShelf: async (item: Shelf, name: string, identity: MutationIdentity) => shelf(await write(`/inventory/shelves/${pathId(item.id)}`, { name, version: item.version }, identity)),
    place: async (item: Shelf, productId: string, active: boolean, identity: MutationIdentity): Promise<Shelf> => {
      const value = await write(`/inventory/shelves/${pathId(item.id)}/products/${pathId(productId)}`, { active, version: item.version }, identity);
      record(value); verify(value.productId === productId && value.assigned === active); return shelf(value.shelf);
    },
  };
}

export function containerLabel(item: Product): string {
  return item.containerAmount === null ? 'Full container amount not set'
    : item.containerLabelAmount && item.containerLabelUnit
      ? `Full container: ${item.containerLabelAmount} ${item.containerLabelUnit === 'each' ? 'items' : item.containerLabelUnit === 'lb' ? 'lbs' : item.containerLabelUnit}${item.containerLabelUnit === item.baseUnit ? '' : ` (${item.containerAmount} ${item.baseUnit})`}`
      : `Full container: ${item.containerAmount} ${item.baseUnit === 'each' ? 'items' : item.baseUnit}`;
}
