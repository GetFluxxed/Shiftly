import assert from 'node:assert/strict';
import test from 'node:test';
import { appBackLabel, appParent, appRoute, appTarget, appTrail } from '../src/navigation/routes';
import { isPageBackAction } from '../src/navigation/pageBack';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';

test('cross-feature return context survives serialization one parent at a time', () => {
  let route = appTarget({ pathname: '/today' }, undefined, { pathname: '/invoices' });
  route = appTarget(route, route.params?.appTrail, { pathname: `/invoices/${A}` });
  route = appTarget(route, route.params?.appTrail, { pathname: '/catalog/new' });
  route = appTarget(route, route.params?.appTrail, { pathname: `/catalog/${B}` }, 'replace');
  for (const pathname of [`/invoices/${A}`, '/invoices', '/today']) {
    route = appParent(JSON.parse(JSON.stringify(route)).params.appTrail, { pathname: '/today' });
    assert.equal(route.pathname, pathname);
  }
});

test('replace preserves an intervening origin and removes only trailing destination frames', () => {
  const trail = JSON.stringify([
    { pathname: '/inventory' }, { pathname: '/catalog' }, { pathname: `/catalog/${A}` }, { pathname: '/catalog/scan' },
  ]);
  const route = appTarget({ pathname: '/catalog/new' }, trail, { pathname: `/catalog/${A}` }, 'replace');
  assert.deepEqual(appTrail(route.params?.appTrail), [
    { pathname: '/inventory' }, { pathname: '/catalog' }, { pathname: `/catalog/${A}` }, { pathname: '/catalog/scan' },
  ]);
  assert.equal(appParent(route.params?.appTrail, { pathname: '/catalog' }).pathname, '/catalog/scan');

  const repeated = JSON.stringify([
    { pathname: '/inventory' }, { pathname: `/catalog/${A}` }, { pathname: '/catalog/scan' }, { pathname: `/catalog/${A}` },
  ]);
  const nearest = appTarget({ pathname: '/catalog/new' }, repeated, { pathname: `/catalog/${A}` }, 'replace');
  assert.deepEqual(appTrail(nearest.params?.appTrail), [{ pathname: '/inventory' }, { pathname: `/catalog/${A}` }, { pathname: '/catalog/scan' }]);
});

test('a completed flow can install one canonical return parent', () => {
  const trail = JSON.stringify([{ pathname: '/today' }, { pathname: '/production/run' }, { pathname: '/production/review' }]);
  const route = appTarget({ pathname: '/production/review' }, trail, { pathname: `/production/logs/${A}` }, 'replace', 0,
    { pathname: '/production/logs' });
  assert.deepEqual(appTrail(route.params?.appTrail), [{ pathname: '/production/logs' }]);
  assert.equal(appParent(route.params?.appTrail, { pathname: '/production' }).pathname, '/production/logs');
});

test('authenticated route allowlist accepts actual IDs and strips untrusted parameters', () => {
  for (const pathname of ['/today', '/reports', '/production/recipes/new', `/production/logs/${A}`, '/team/7', '/owner/9', `/counts/${A}/line/${B}`])
    assert.equal(appRoute(pathname)?.pathname, pathname);
  for (const pathname of ['/sign-in', '/activate', '/team/0', '/owner/-1', '/catalog/not-a-uuid', 'https://example.com'])
    assert.equal(appRoute(pathname), null);
  assert.deepEqual(appRoute('/catalog/packages/[productId]', { productId: A, barcode: '00CASE', barcodeType: 'code39', token: 'secret' }),
    { pathname: `/catalog/packages/${A}`, params: { barcode: '00CASE', barcodeType: 'code39' } });
  assert.deepEqual(appRoute('/counts/[countId]', { countId: A, returnTo: 'stock', token: 'secret' }),
    { pathname: `/counts/${A}`, params: { returnTo: 'stock' } });
  assert.deepEqual(appRoute('/team/[userId]', { userId: 42 }), { pathname: '/team/42' });
  assert.deepEqual(appRoute('/owner/[userId]', { userId: 9 }), { pathname: '/owner/9' });
  for (const userId of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER + 1])
    assert.equal(appRoute('/team/[userId]', { userId }), null);
  assert.equal(appRoute('/catalog/[productId]', { productId: 42 }), null);
});

test('specialized app parents have action-specific Back labels', () => {
  const labels = new Map([
    ['/team/build', 'Back to build team'], ['/team/invite', 'Back to invite'], ['/team/assign', 'Back to assign team member'],
    ['/team/access', 'Back to store access'], ['/owner/cutover', 'Back to store sign-in'],
  ]);
  for (const [path, label] of labels) assert.equal(appBackLabel(path), label);
});

test('generic trails remain bounded and reject malformed or unknown frames', () => {
  assert.deepEqual(appTrail(JSON.stringify([{ pathname: '/today', params: { token: 'secret', appTrail: 'nested' } }])), [{ pathname: '/today' }]);
  for (const bad of ['{', '{}', JSON.stringify([{ pathname: '/sign-in' }]), JSON.stringify(Array(13).fill({ pathname: '/today' })), ' '.repeat(4097)])
    assert.deepEqual(appTrail(bad), []);
  let route = { pathname: '/today' };
  for (let index = 0; index < 20; index += 1)
    route = appTarget(route, (route as { params?: Record<string, string> }).params?.appTrail, { pathname: index % 2 ? '/reports' : '/accounts' });
  assert.equal(appTrail((route as { params?: Record<string, string> }).params?.appTrail).length, 12);
});

test('native page Back recognizes only semantic stack-back removal actions', () => {
  for (const type of ['GO_BACK', 'POP', 'POP_TO_TOP']) assert.equal(isPageBackAction(type), true);
  for (const type of ['POP_TO', 'REPLACE', 'RESET', 'NAVIGATE', 'PUSH']) assert.equal(isPageBackAction(type), false);
});
