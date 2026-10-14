import { ApiError } from '../../api/client';
import { MutationIdentity, parsePackage, validId, type Package, type Page, type Request, type StockUnit } from '../api';

export interface Count {
  id: string; storeId: number; businessDate: string; state: 'draft' | 'review' | 'posted' | 'cancelled'; version: number;
  startedAt: string; startedBy: string; reviewedAt: string | null; reviewedBy: string | null;
  postedAt: string | null; postedBy: string | null; totalLines: number; countedLines: number; totalProducts: number; countedProducts: number;
  configurationChanged?: boolean;
}
export interface SnapshotProduct { productId: string; name: string; sku: string; baseUnit: StockUnit; containerAmount: string | null; packages?: Package[] }
export type Entry = { mode: 'total'; amount: string; unit: StockUnit }
  | { mode: 'containers'; fullContainers: number; partialAmount: string; partialUnit: StockUnit }
  | { mode: 'packages'; packages: { packageId: string; count: number }[]; partialAmount: string; partialUnit: StockUnit };
export interface CountLine extends SnapshotProduct {
  id: string; shelfId: string | null; shelfName: string; quantity: string | null; entry: Entry | null;
  version: number; observedAt: string | null; observedBy: string | null;
}
export interface Comparison extends SnapshotProduct { previousQuantity: string | null; quantity: string | null; difference: string | null; locations: number; missing: number }
export interface StockItem extends SnapshotProduct { quantity: string | null; active: boolean; countId: string | null; countedOn: string | null; updatedAt: string | null; lastCountedAt?: string | null; lastMovement?: string | null; stockVersion?: number | null }
export interface StockDetail extends StockItem { locations: Page<CountLine> }
export interface CountStatus { storeId: number; openCount: Count | null; lastCount: Count | null }

function verify(value: unknown): asserts value { if (!value) throw new ApiError('This inventory response could not be verified. Reload before continuing.'); }
function object(value: unknown): asserts value is Record<string, unknown> { verify(value && typeof value === 'object' && !Array.isArray(value)); }
function integer(value: unknown, minimum = 0) { return Number.isSafeInteger(value) && Number(value) >= minimum; }
function quantity(value: unknown, signed = false) { return value === null || (typeof value === 'string' && (signed ? /^-?\d{1,15}(?:\.\d{1,9})?$/ : /^\d{1,15}(?:\.\d{1,9})?$/).test(value)); }
function time(value: unknown) { return typeof value === 'string' && !Number.isNaN(Date.parse(value)); }
function optionalTime(value: unknown) { return value === null || time(value); }
function nullableId(value: unknown) { return value === null || validId(value); }
function count(value: unknown): Count {
  object(value); verify(validId(value.id) && integer(value.storeId, 1) && integer(value.version, 1)
    && ['draft', 'review', 'posted', 'cancelled'].includes(String(value.state)) && time(value.businessDate) && time(value.startedAt)
    && optionalTime(value.reviewedAt) && optionalTime(value.postedAt) && typeof value.startedBy === 'string'
    && (value.reviewedBy === null || typeof value.reviewedBy === 'string') && (value.postedBy === null || typeof value.postedBy === 'string')
    && integer(value.totalLines) && integer(value.countedLines) && Number(value.countedLines) <= Number(value.totalLines) && integer(value.totalProducts)
    && integer(value.countedProducts) && Number(value.countedProducts) <= Number(value.totalProducts)
    && (value.configurationChanged === undefined || typeof value.configurationChanged === 'boolean'));
  return value as unknown as Count;
}
function product(value: unknown): asserts value is Record<string, unknown> {
  object(value); verify(validId(value.productId) && typeof value.name === 'string' && typeof value.sku === 'string'
    && ['each', 'g', 'kg'].includes(String(value.baseUnit)) && quantity(value.containerAmount)
    && (value.packages === undefined || (Array.isArray(value.packages) && value.packages.length <= 40)));
  if (Array.isArray(value.packages)) { const packages = value.packages.map(parsePackage); verify(packages.every((item: Package) => item.productId === value.productId)); value.packages = packages; }
}
function line(value: unknown): CountLine {
  product(value); verify(validId(value.id) && nullableId(value.shelfId) && typeof value.shelfName === 'string'
    && quantity(value.quantity) && integer(value.version, 1) && optionalTime(value.observedAt)
    && (value.observedBy === null || typeof value.observedBy === 'string'));
  if (value.entry !== null) {
    object(value.entry); const e = value.entry;
    const packages = e.mode === 'packages' && Array.isArray(e.packages) && e.packages.length <= 40 && e.packages.every((row: unknown) => { if (!row || typeof row !== 'object' || Array.isArray(row)) return false; const item = row as Record<string, unknown>; return validId(item.packageId) && integer(item.count) && Number(item.count) <= 1_000_000; }) && new Set(e.packages.map((row: { packageId: string }) => row.packageId)).size === e.packages.length && e.partialAmount !== null && quantity(e.partialAmount) && ['each', 'g', 'kg'].includes(String(e.partialUnit));
    verify((e.mode === 'total' && e.amount !== null && quantity(e.amount) && ['each', 'g', 'kg'].includes(String(e.unit)))
      || (e.mode === 'containers' && integer(e.fullContainers) && e.partialAmount !== null && quantity(e.partialAmount) && ['each', 'g', 'kg'].includes(String(e.partialUnit))) || packages);
  }
  verify((value.quantity === null) === (value.entry === null));
  return value as unknown as CountLine;
}
function comparison(value: unknown): Comparison {
  product(value); verify(quantity(value.previousQuantity) && quantity(value.quantity) && quantity(value.difference, true) && integer(value.locations, 1) && integer(value.missing));
  return value as unknown as Comparison;
}
function stock(value: unknown): StockItem {
  product(value); verify(quantity(value.quantity) && typeof value.active === 'boolean' && nullableId(value.countId) && optionalTime(value.countedOn) && optionalTime(value.updatedAt)
    && (value.lastCountedAt === undefined || optionalTime(value.lastCountedAt))
    && (value.lastMovement === undefined || value.lastMovement === null || ['opening', 'count', 'production', 'reversal'].includes(String(value.lastMovement)))
    && (value.stockVersion === undefined || value.stockVersion === null || integer(value.stockVersion, 1)));
  return value as unknown as StockItem;
}
function page<T>(value: unknown, parse: (item: unknown) => T): Page<T> {
  object(value); verify(Array.isArray(value.items) && value.items.length <= 40 && (value.nextCursor === null || (typeof value.nextCursor === 'string'
    && (validId(value.nextCursor) || /^p1\.[A-Za-z0-9_-]{1,1197}$/.test(value.nextCursor)))));
  return { items: value.items.map(parse), nextCursor: value.nextCursor as string | null };
}
function id(value: string) { verify(validId(value)); return value; }
const uncertainMessage = 'We could not confirm this save. Keep the entry unchanged and retry to recover its saved result, or reload the count before making another change.';
export function countsApi(request: Request) {
  const write = (path: string, body: Record<string, unknown>, identity: MutationIdentity) => request<unknown>(path,
    { method: 'POST', body: { ...body, requestId: identity.for(path, body) }, uncertainMessage });
  return {
    status: async (): Promise<CountStatus> => {
      const value = await request<unknown>('/inventory/count-status'); object(value); verify(integer(value.storeId, 1));
      return { storeId: Number(value.storeId), openCount: value.openCount === null ? null : count(value.openCount), lastCount: value.lastCount === null ? null : count(value.lastCount) };
    },
    start: async (businessDate: string, identity: MutationIdentity) => count(await write('/inventory/counts', { businessDate }, identity)),
    detail: async (countId: string) => count(await request(`/inventory/counts/${id(countId)}`)),
    lines: async (countId: string, q = '', after = '', shelf = '', missing = false) => page(await request(`/inventory/counts/${id(countId)}/lines`, { query: { q, after, shelf, missing: String(missing) } }), line),
    line: async (countId: string, lineId: string) => line(await request(`/inventory/counts/${id(countId)}/lines/${id(lineId)}`)),
    save: async (countId: string, item: CountLine, entry: Entry, identity: MutationIdentity) => {
      const value = await write(`/inventory/counts/${id(countId)}/lines/${id(item.id)}`, { version: item.version, entry }, identity);
      object(value); return { line: line(value.line), count: count(value.count) };
    },
    comparison: async (countId: string, q = '', after = '') => page(await request(`/inventory/counts/${id(countId)}/comparison`, { query: { q, after } }), comparison),
    transition: async (item: Count, action: 'review' | 'post' | 'reopen' | 'cancel', identity: MutationIdentity) => count(await write(`/inventory/counts/${id(item.id)}/${action}`, { version: item.version }, identity)),
    history: async (after = '') => page(await request('/inventory/counts', { query: { after } }), count),
    stock: async (q = '', after = '', shelf = '') => page(await request('/inventory/stock', { query: { q, after, shelf } }), stock),
    stockDetail: async (productId: string, after = ''): Promise<StockDetail> => {
      const value = await request<unknown>(`/inventory/stock/${id(productId)}`, { query: { after } }); const parsed = stock(value); object(value);
      return { ...parsed, locations: page(value.locations, line) };
    },
  };
}
