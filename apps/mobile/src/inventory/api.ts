import { ApiError } from '../api/client';
import type { RequestOptions } from '../api/types';

export const units = { each: 'Each / item', g: 'Grams', kg: 'Kilograms', ml: 'Millilitres (legacy)', l: 'Litres (legacy)' } as const;
export const stockUnits = ['each', 'g', 'kg'] as const;
export type StockUnit = typeof stockUnits[number];
export type Unit = keyof typeof units;
export interface Product { id: string; name: string; sku: string; baseUnit: Unit; active: boolean; version: number; containerAmount: string | null }
export interface Shelf { id: string; name: string; storeId: number; version: number }
export interface Page<T> { items: T[]; nextCursor: string | null }
export interface ShelfDetail extends Shelf { products: Page<Product> }
export type Request = <T>(path: string, options?: RequestOptions) => Promise<T>;
export type ProductInput = { name: string; sku: string; baseUnit: StockUnit; containerAmount?: string | null };
const idPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export function validId(id: unknown): id is string { return typeof id === 'string' && idPattern.test(id); }
function verify(condition: unknown): asserts condition {
  if (!condition) throw new ApiError('The inventory response could not be verified. Please reload.');
}
function record(value: unknown): asserts value is Record<string, unknown> {
  verify(value && typeof value === 'object');
}
function product(value: unknown): Product {
  record(value);
  verify(validId(value.id) && typeof value.name === 'string' && typeof value.sku === 'string'
    && typeof value.baseUnit === 'string' && Object.hasOwn(units, value.baseUnit)
    && typeof value.active === 'boolean' && Number.isSafeInteger(value.version) && Number(value.version) > 0);
  const amount = value.containerAmount ?? null;
  verify(amount === null || (typeof amount === 'string' && /^\d{1,9}(?:\.\d{1,6})?$/.test(amount) && Number(amount) > 0
    && (value.baseUnit !== 'each' || Number.isInteger(Number(amount)))));
  return { ...value, containerAmount: amount } as unknown as Product;
}
function shelf(value: unknown): Shelf {
  record(value);
  verify(validId(value.id) && typeof value.name === 'string' && Number.isSafeInteger(value.version)
    && Number(value.version) > 0 && Number.isSafeInteger(value.storeId) && Number(value.storeId) > 0);
  return value as unknown as Shelf;
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
    createProduct: async (fields: ProductInput, identity: MutationIdentity) => product(await write('/inventory/products', fields, identity)),
    editProduct: async (item: Product, name: string, sku: string, identity: MutationIdentity, containerAmount = item.containerAmount) => product(await write(`/inventory/products/${pathId(item.id)}`, { name, sku, containerAmount, version: item.version }, identity)),
    productState: async (item: Product, active: boolean, identity: MutationIdentity) => product(await write(`/inventory/products/${pathId(item.id)}/state`, { active, version: item.version }, identity)),
    shelves: async (after = '') => page(await request('/inventory/shelves', { query: after ? { after } : {} }), shelf),
    shelf: async (id: string, after = ''): Promise<ShelfDetail> => {
      const value = await request<unknown>(`/inventory/shelves/${pathId(id)}`, { query: after ? { after } : {} });
      const parsed = shelf(value); record(value); return { ...parsed, products: page(value.products, product) };
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
    : `Full container: ${item.containerAmount} ${item.baseUnit === 'each' ? 'items' : item.baseUnit}`;
}
