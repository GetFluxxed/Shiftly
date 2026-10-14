import { ApiError } from '../api/client';
import type { RequestOptions } from '../api/types';

export type ProductionUnit = 'each' | 'g' | 'kg';
export interface RecipeIngredient { productId: string; name: string; sku: string; amount: string; unit: ProductionUnit; baseUnit: ProductionUnit; baseAmount: string; currentBaseUnit?: ProductionUnit }
export interface Recipe { id: string; name: string; version: number; revisionId: string; yieldAmount: string; yieldUnit: string; instructions: string; ingredients: RecipeIngredient[] }
export interface RecipeInput { name: string; yieldAmount: string; yieldUnit: string; instructions: string; ingredients: { productId: string; amount: string; unit: ProductionUnit }[] }
export interface ProductionEntry { recipeId: string; revisionId: string; batches: number }
export interface Deduction { productId: string; name: string; recipeAmount: string; allowanceAmount: string; quantity: string; baseUnit: ProductionUnit; balance: string | null; remaining: string | null }
export interface ProductionIssue { productId: string; code: 'unknown_stock' | 'unit_changed' | 'insufficient_stock'; message: string }
export interface ProductionPreview { entries: ProductionLogEntry[]; deductions: Deduction[]; canConfirm: boolean; issues: ProductionIssue[] }
export interface ProductionLogEntry { recipeId: string; revisionId: string; name: string; yieldAmount: string; yieldUnit: string; batches: number }
export interface ProductionLog { id: string; businessDate: string; state: 'confirmed' | 'reversed'; createdAt: string; createdBy: string; entries: ProductionLogEntry[]; ingredients: Deduction[]; reversalReason?: string }
export interface Page<T> { items: T[]; nextCursor: string | null }
export type Request = <T>(path: string, options?: RequestOptions) => Promise<T>;

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const decimalPattern = /^\d{1,9}(?:\.\d{1,6})?$/;
const responseDecimalPattern = /^\d{1,15}(?:\.\d{1,9})?$/;
const signedResponseDecimalPattern = /^-?\d{1,15}(?:\.\d{1,9})?$/;
const datePattern = /^\d{4}-\d{2}-\d{2}$/;
function verify(condition: unknown): asserts condition { if (!condition) throw new ApiError('The production response could not be verified. Please reload.'); }
function record(value: unknown): asserts value is Record<string, unknown> { verify(value !== null && typeof value === 'object' && !Array.isArray(value)); }
function uuid(value: unknown): value is string { return typeof value === 'string' && uuidPattern.test(value); }
function decimal(value: unknown, allowZero = false): value is string { return typeof value === 'string' && decimalPattern.test(value) && (allowZero || Number(value) > 0); }
function responseDecimal(value: unknown, signed = false): value is string { return typeof value === 'string' && (signed ? signedResponseDecimalPattern : responseDecimalPattern).test(value); }
function unit(value: unknown): value is ProductionUnit { return value === 'each' || value === 'g' || value === 'kg'; }
function cursor(value: unknown) { return typeof value === 'string' && value.length <= 1200 && /^[A-Za-z0-9._-]+$/.test(value); }
function ingredient(value: unknown): RecipeIngredient { record(value); verify(uuid(value.productId) && typeof value.name === 'string' && typeof value.sku === 'string' && decimal(value.amount) && unit(value.unit) && unit(value.baseUnit) && responseDecimal(value.baseAmount) && (value.currentBaseUnit === undefined || unit(value.currentBaseUnit))); return value as unknown as RecipeIngredient; }
function recipe(value: unknown): Recipe { record(value); verify(uuid(value.id) && uuid(value.revisionId) && typeof value.name === 'string' && Number.isSafeInteger(value.version) && Number(value.version) > 0 && decimal(value.yieldAmount) && typeof value.yieldUnit === 'string' && value.yieldUnit.length <= 40 && typeof value.instructions === 'string' && Array.isArray(value.ingredients) && value.ingredients.length <= 50); return { ...value, ingredients: value.ingredients.map(ingredient) } as unknown as Recipe; }
function page<T>(value: unknown, parse: (item: unknown) => T): Page<T> { record(value); verify(Array.isArray(value.items) && value.items.length <= 40 && (value.nextCursor === null || cursor(value.nextCursor))); return { items: value.items.map(parse), nextCursor: value.nextCursor as string | null }; }
function deduction(value: unknown): Deduction { record(value); verify(uuid(value.productId) && typeof value.name === 'string' && responseDecimal(value.recipeAmount) && responseDecimal(value.allowanceAmount) && responseDecimal(value.quantity) && unit(value.baseUnit) && (value.balance === null || responseDecimal(value.balance)) && (value.remaining === null || responseDecimal(value.remaining, true))); return value as unknown as Deduction; }
function logEntry(value: unknown): ProductionLogEntry { record(value); verify(uuid(value.recipeId) && uuid(value.revisionId) && typeof value.name === 'string' && responseDecimal(value.yieldAmount) && typeof value.yieldUnit === 'string' && Number.isSafeInteger(value.batches) && Number(value.batches) >= 1 && Number(value.batches) <= 1000); return value as unknown as ProductionLogEntry; }
function issue(value: unknown): ProductionIssue { record(value); verify(uuid(value.productId) && (value.code === 'unknown_stock' || value.code === 'unit_changed' || value.code === 'insufficient_stock') && typeof value.message === 'string'); return value as unknown as ProductionIssue; }
function preview(value: unknown): ProductionPreview { record(value); verify(Array.isArray(value.entries) && value.entries.length <= 100 && Array.isArray(value.deductions) && value.deductions.length <= 500 && typeof value.canConfirm === 'boolean' && Array.isArray(value.issues) && value.issues.length <= 500); return { entries: value.entries.map(logEntry), deductions: value.deductions.map(deduction), canConfirm: value.canConfirm, issues: value.issues.map(issue) }; }
function log(value: unknown): ProductionLog { record(value); verify(uuid(value.id) && typeof value.businessDate === 'string' && datePattern.test(value.businessDate) && (value.state === 'confirmed' || value.state === 'reversed') && typeof value.createdAt === 'string' && typeof value.createdBy === 'string' && Array.isArray(value.entries) && value.entries.length <= 100 && Array.isArray(value.ingredients) && value.ingredients.length <= 500 && (value.reversalReason === undefined || typeof value.reversalReason === 'string')); return { ...value, entries: value.entries.map(logEntry), ingredients: value.ingredients.map(deduction) } as unknown as ProductionLog; }
function pathId(value: string) { verify(uuid(value)); return value; }

export function newUuid(): string { return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const n = Math.floor(Math.random() * 16); return (c === 'x' ? n : (n & 3) | 8).toString(16); }); }
export function validProductionId(value: unknown): value is string { return uuid(value); }
export function validAmount(value: string, unitValue?: ProductionUnit): boolean { return decimal(value) && (unitValue !== 'each' || Number.isInteger(Number(value))); }

export function productionApi(request: Request) {
  const uncertain = 'We could not confirm this production change. Keep this draft and reload the same production log before trying again.';
  const post = (path: string, body: Record<string, unknown>) => request<unknown>(path, { method: 'POST', body, uncertainMessage: uncertain });
  return {
    recipes: async (query = '', after = '') => page(await request('/production/recipes', { query: { q: query, ...(after ? { after } : {}) } }), recipe),
    recipe: async (id: string) => recipe(await request(`/production/recipes/${pathId(id)}`)),
    createRecipe: async (fields: RecipeInput, requestId: string, storeId: number) => recipe(await post('/production/recipes', { ...fields, requestId, expectedStoreId: storeId })),
    editRecipe: async (item: Recipe, fields: RecipeInput, requestId: string, storeId: number) => recipe(await post(`/production/recipes/${pathId(item.id)}`, { ...fields, version: item.version, requestId, expectedStoreId: storeId })),
    logs: async (after = '') => page(await request('/production/logs', { query: after ? { after } : {} }), log),
    log: async (id: string) => log(await request(`/production/logs/${pathId(id)}`)),
    preview: async (businessDate: string, entries: ProductionEntry[], storeId: number) => preview(await post('/production/preview', { businessDate, entries, expectedStoreId: storeId })),
    confirm: async (logId: string, businessDate: string, entries: ProductionEntry[], requestId: string, storeId: number) => log(await post('/production/logs', { logId: pathId(logId), businessDate, entries, confirmed: true, requestId, expectedStoreId: storeId })),
    reverse: async (id: string, reason: string, requestId: string, storeId: number) => log(await post(`/production/logs/${pathId(id)}/reverse`, { reason, requestId, expectedStoreId: storeId })),
  };
}
