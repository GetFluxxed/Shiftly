import assert from 'node:assert/strict';
import test from 'node:test';
import { inventoryParent, inventoryRoute, inventoryTarget, inventoryTrail } from '../src/inventory/navigation';
const productId = '11111111-1111-4111-8111-111111111111';
const countId = '22222222-2222-4222-8222-222222222222';
const home = { pathname: '/inventory' };
const stock = { pathname: '/stock' };
const detail = { pathname: `/stock/${productId}` };
const review = { pathname: `/counts/${countId}/review` };

test('stock detail, physical count and entries return one level after a serialized checkpoint', () => {
  let route = inventoryTarget(home, undefined, stock);
  route = inventoryTarget(route, route.params?.inventoryTrail, detail);
  route = inventoryTarget(route, route.params?.inventoryTrail, review);
  route = inventoryTarget(route, route.params?.inventoryTrail, { pathname: `/counts/${countId}` });
  for (const expected of [review, detail, stock, home]) {
    route = inventoryParent(JSON.parse(JSON.stringify(route)).params.inventoryTrail, home);
    assert.equal(route.pathname, expected.pathname);
  }
});

test('creation replaces the form while explicit forward links retain their immediate origin', () => {
  const shelf = { pathname: `/shelves/${productId}` };
  let route = inventoryTarget(shelf, JSON.stringify([home, { pathname: '/shelves' }]), { pathname: '/catalog/new' });
  route = inventoryTarget(route, route.params?.inventoryTrail, { pathname: `/catalog/${productId}` }, 'replace');
  assert.equal(inventoryParent(route.params?.inventoryTrail, home).pathname, shelf.pathname);
  route = inventoryTarget(route, route.params?.inventoryTrail, { pathname: '/shelves' });
  assert.equal(inventoryParent(route.params?.inventoryTrail, home).pathname, `/catalog/${productId}`);
});

test('navigation metadata only admits bounded known inventory destinations and non-secret parameters', () => {
  for (const bad of ['https://example.com', '/accounts', '/catalog/../accounts', '/catalog/not-a-uuid', '//stock']) {
    assert.equal(inventoryRoute(bad), null);
    assert.deepEqual(inventoryTrail(JSON.stringify([{ pathname: bad }])), []);
  }
  assert.deepEqual(inventoryTrail(JSON.stringify([{ pathname: '/stock', params: { token: 'secret', inventoryTrail: 'nested' } }])), [stock]);
  for (const bad of ['{', '{}', JSON.stringify([null]), JSON.stringify([{ pathname: '/stock', params: [] }]), JSON.stringify(Array(13).fill(stock)), ' '.repeat(4097)])
    assert.deepEqual(inventoryTrail(bad), []);
  assert.equal(inventoryParent('broken', stock).pathname, '/stock');
  assert.deepEqual(inventoryRoute('/catalog/packages/[productId]', { productId, barcode: '00BOX-12', barcodeType: 'code39', token: 'secret' }),
    { pathname: `/catalog/packages/${productId}`, params: { barcode: '00BOX-12', barcodeType: 'code39' } });
});

test('long valid journeys retain the nearest twelve parents', () => {
  let route = home;
  for (let n = 1; n <= 20; n++) {
    const target = { pathname: `/catalog/${String(n).padStart(8, '0')}-1111-4111-8111-111111111111` };
    route = inventoryTarget(route, (route as { params?: Record<string, string> }).params?.inventoryTrail, target);
  }
  const parents = inventoryTrail((route as { params?: Record<string, string> }).params?.inventoryTrail);
  assert.equal(parents.length, 12);
  assert.equal(parents.at(-1)?.pathname, '/catalog/00000019-1111-4111-8111-111111111111');
});
