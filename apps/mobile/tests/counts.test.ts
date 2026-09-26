import assert from 'node:assert/strict';
import test from 'node:test';
import { entryTotal, entryLabel } from '../src/inventory/counts/measurements';
import { countsApi } from '../src/inventory/counts/api';
import { MutationIdentity, type Request } from '../src/inventory/api';
const product = { productId: '11111111-1111-4111-8111-111111111111', name: 'White Quella', sku: '000184', baseUnit: 'kg' as const, containerAmount: '6' };
const count = { id: product.productId, storeId: 1, businessDate: '2026-09-25', state: 'draft', version: 1,
  startedAt: '2026-09-25T01:00:00Z', startedBy: 'owner', reviewedAt: null, reviewedBy: null, postedAt: null, postedBy: null, totalLines: 1, countedLines: 0, totalProducts: 1 };
function request(value: unknown): Request { return async <T>() => value as T; }

test('full containers and gram partials produce exact kilograms', () => {
  assert.equal(entryTotal({ mode: 'containers', fullContainers: 2, partialAmount: '1250', partialUnit: 'g' }, product), '13.25');
  assert.equal(entryTotal({ mode: 'total', amount: '0.000001', unit: 'g' }, product), '0.000000001');
  assert.equal(entryTotal({ mode: 'total', amount: '0', unit: 'kg' }, product), '0');
});
test('invalid, incomplete and incompatible measurements do not become zero', () => {
  for (const amount of ['', '-1', 'NaN', '1e2', '.5']) assert.equal(entryTotal({ mode: 'total', amount, unit: 'kg' }, product), null);
  assert.equal(entryTotal({ mode: 'total', amount: '1', unit: 'each' }, product), null);
  assert.equal(entryTotal({ mode: 'containers', fullContainers: NaN, partialAmount: '0', partialUnit: 'g' }, product), null);
  assert.equal(entryTotal({ mode: 'containers', fullContainers: 1, partialAmount: '0', partialUnit: 'g' }, { ...product, containerAmount: null }), null);
});
test('individual items require whole quantities', () => {
  const item = { ...product, baseUnit: 'each' as const, containerAmount: '12' };
  assert.equal(entryTotal({ mode: 'total', amount: '1.5', unit: 'each' }, item), null);
  assert.equal(entryTotal({ mode: 'containers', fullContainers: 2, partialAmount: '3', partialUnit: 'each' }, item), '27');
});
test('historical entry description uses the captured container reference', () => {
  assert.equal(entryLabel({ mode: 'containers', fullContainers: 2, partialAmount: '1250', partialUnit: 'g' }, product), '2 full × 6 kg + 1250 g net partial');
});
test('count requests reuse an identity after an uncertain response', async () => {
  const calls: { path: string; body: unknown }[] = []; let failed = false;
  const api = countsApi(async <T>(path: string, options?: Parameters<Request>[1]) => {
    calls.push({ path, body: options?.body });
    if (!failed) { failed = true; throw new Error('Response lost'); }
    return count as T;
  });
  const identity = new MutationIdentity();
  await assert.rejects(api.start('2026-09-25', identity));
  await api.start('2026-09-25', identity);
  assert.deepEqual(calls[0], calls[1]);
});
test('unknown balances remain null and measured zeros remain zero', async () => {
  const base = { ...product, active: true, countId: null, countedOn: null, updatedAt: null };
  const unknown = await countsApi(request({ items: [{ ...base, quantity: null }], nextCursor: null })).stock();
  assert.equal(unknown.items[0]?.quantity, null);
  const zero = await countsApi(request({ items: [{ ...base, quantity: '0' }], nextCursor: null })).stock();
  assert.equal(zero.items[0]?.quantity, '0');
});
test('malformed count and stock responses fail closed', async () => {
  await assert.rejects(countsApi(request({ ...count, countedLines: 2 })).detail(product.productId));
  await assert.rejects(countsApi(request({ items: [{ ...product, quantity: '-1' }], nextCursor: null })).stock());
  await assert.rejects(countsApi(request(count)).detail('../../accounts'));
});
test('signed differences and opening balances survive response parsing', async () => {
  const result = await countsApi(request({ items: [{ ...product, previousQuantity: '18', quantity: '13.25', difference: '-4.75', locations: 2, missing: 0 }], nextCursor: null })).comparison(product.productId);
  assert.equal(result.items[0]?.difference, '-4.75');
});
