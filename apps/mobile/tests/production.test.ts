/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError } from '../src/api/client';
import type { RequestOptions } from '../src/api/types';
import { newUuid, productionApi, validAmount, type Recipe } from '../src/production/api';

const recipe: Recipe = { id: '11111111-1111-4111-8111-111111111111', name: 'Vanilla', version: 2,
  revisionId: '22222222-2222-4222-8222-222222222222', yieldAmount: '1', yieldUnit: 'batch', instructions: '',
  ingredients: [{ productId: '33333333-3333-4333-8333-333333333333', name: 'Cream', sku: '0007', amount: '6', unit: 'kg', baseUnit: 'kg', baseAmount: '6' }] };

test('production recipes preserve stable product IDs and version the edit', async () => {
  let call: { path: string; options?: RequestOptions } | undefined;
  const api = productionApi(async <T>(path: string, options?: RequestOptions) => { call = { path, options }; return recipe as T; });
  await api.editRecipe(recipe, { name: 'Vanilla', yieldAmount: '1', yieldUnit: 'batch', instructions: '', ingredients: [{ productId: recipe.ingredients[0]!.productId, amount: '6000', unit: 'g' }] }, newUuid(), 12);
  assert.equal(call?.path, `/production/recipes/${recipe.id}`);
  assert.equal(call?.options?.body?.version, 2);
  assert.equal(call?.options?.body?.expectedStoreId, 12);
  assert.equal((call?.options?.body?.ingredients as { productId: string }[])[0]?.productId, recipe.ingredients[0]!.productId);
});

test('confirm keeps the caller supplied durable log ID and exact batch counts', async () => {
  const logId = newUuid(); let body: Record<string, unknown> | undefined;
  const api = productionApi(async <T>(_path: string, options?: RequestOptions) => { body = options?.body; return { id: logId, businessDate: '2026-09-29', state: 'confirmed', createdAt: '2026-09-29T10:00:00Z', createdBy: 'Crew', entries: [], ingredients: [] } as T; });
  await api.confirm(logId, '2026-09-29', [{ recipeId: recipe.id, revisionId: recipe.revisionId, batches: 4 }], newUuid(), 12);
  assert.equal(body?.logId, logId); assert.equal(body?.confirmed, true);
  assert.deepEqual(body?.entries, [{ recipeId: recipe.id, revisionId: recipe.revisionId, batches: 4 }]);
});

test('preview rejects malformed stock math and exact amount validation keeps each whole', async () => {
  const api = productionApi(async <T>() => ({ entries: [], deductions: [{ productId: recipe.ingredients[0]!.productId, name: 'Cream', recipeAmount: '6', allowanceAmount: '0.06', quantity: 'oops', baseUnit: 'kg', balance: '10', remaining: '3.94' }], canConfirm: true, issues: [] }) as T);
  await assert.rejects(api.preview('2026-09-29', [], 12), ApiError);
  assert.equal(validAmount('1.5', 'each'), false); assert.equal(validAmount('1.5', 'kg'), true);
  assert.equal(validAmount('1e3', 'kg'), false); assert.equal(validAmount('0', 'g'), false);
});

test('preview accepts exact nine-place quantities and a negative remaining balance for an actionable issue', async () => {
  const api = productionApi(async <T>() => ({ entries: [{ recipeId: recipe.id, revisionId: recipe.revisionId, name: recipe.name, yieldAmount: '1', yieldUnit: 'batch', batches: 2 }], deductions: [{ productId: recipe.ingredients[0]!.productId, name: 'Cream', recipeAmount: '999999999999.999999999', allowanceAmount: '0.000000001', quantity: '1000000000000', baseUnit: 'g', balance: '0', remaining: '-1000000000000' }], canConfirm: false, issues: [{ productId: recipe.ingredients[0]!.productId, code: 'insufficient_stock', message: 'There is not enough stock.' }] }) as T);
  const result = await api.preview('2026-09-29', [], 12);
  assert.equal(result.canConfirm, false); assert.equal(result.deductions[0]?.remaining, '-1000000000000');
  assert.equal(result.issues[0]?.code, 'insufficient_stock');
});
