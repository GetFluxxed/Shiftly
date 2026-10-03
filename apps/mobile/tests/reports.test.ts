import assert from 'node:assert/strict';
import test from 'node:test';
import { createResponseGuard, forecastApi, parseForecast } from '../src/reports/forecastApi';
import type { RequestOptions } from '../src/api/types';

const UUID_A = '11111111-1111-4111-8111-111111111111';
const UUID_B = '22222222-2222-4222-8222-222222222222';
const ready = {
  storeId: 7, status: 'ready', error: null,
  forecast: { id: UUID_A, logId: null, asOf: '2026-10-01', generatedAt: null, model: 'gpt-4o-mini', stale: false,
    coverage: { windowDays: 28, productionReports: 2, productionDays: 2, shiftReports: 4, truncated: false },
    facts: { daily: [{ date: '2026-10-01', recipeId: UUID_B, name: 'Bacio', batches: 3 }],
      ingredients: [{ productId: UUID_A, name: 'Base', baseUnit: 'kg', quantity: null, usedAmount: '6.06' }] }, analysis: null },
} as const;

test('forecast GET is read only and preserves sparse exact facts', async () => {
  let call: { path: string; options?: RequestOptions } | undefined;
  const api = forecastApi(async <T>(path: string, options?: RequestOptions) => { call = { path, options }; return ready as T; });
  const result = await api.get();
  assert.equal(call?.path, '/production/forecast');
  assert.equal(call?.options?.method, undefined);
  assert.deepEqual(call?.options?.query, {});
  assert.equal(result.forecast?.coverage.productionDays, 2);
  assert.equal(result.forecast?.analysis, null);
  assert.equal(result.forecast?.facts.daily[0]?.batches, 3);
});

test('forecast POST carries current store and optional selected log', async () => {
  let body: unknown; let query: unknown;
  const api = forecastApi(async <T>(_path: string, options?: RequestOptions) => {
    body = options?.body; query = options?.query;
    return { ...ready, status: 'queued', forecast: null } as T;
  });
  await api.request(7, UUID_B, UUID_A);
  assert.equal((body as { expectedStoreId: number }).expectedStoreId, 7);
  assert.equal((body as { logId: string }).logId, UUID_B);
  assert.equal((body as { requestId: string }).requestId, UUID_A);
  await api.get(UUID_B);
  assert.deepEqual(query, { logId: UUID_B });
});

test('unavailable forecasts can retain bounded facts and reject malformed provider output', () => {
  const unavailable = parseForecast({ ...ready, status: 'unavailable', error: 'No AI provider is configured.' });
  assert.equal(unavailable.status, 'unavailable');
  assert.equal(unavailable.forecast?.facts.ingredients[0]?.usedAmount, '6.06');
  assert.throws(() => parseForecast({ ...ready, forecast: { ...ready.forecast, facts: { ...ready.forecast.facts,
    daily: [{ ...ready.forecast.facts.daily[0], batches: -1 }] } } }), /could not be verified/i);
});

test('zero-batch recommendations represent skipping a flavor', () => {
  const parsed = parseForecast({ ...ready, forecast: { ...ready.forecast, analysis: {
    summary: 'Plan', trends: [], risks: [], limitations: [], recommendations: [
      { recipeId: UUID_B, name: 'Bacio', day: '2026-10-02', batches: 0, rationale: 'Skip this flavor.' },
    ],
  } } });
  assert.equal(parsed.forecast?.analysis?.recommendations[0]?.batches, 0);
});

test('a delayed response cannot replace a newer forecast scope', async () => {
  const guard = createResponseGuard();
  const accepted: string[] = [];
  let releaseOld: (() => void) | undefined;
  const old = guard.begin();
  const delayed = new Promise<void>(resolve => { releaseOld = resolve; }).then(() => {
    if (guard.current(old)) accepted.push('old');
  });
  const current = guard.begin();
  if (guard.current(current)) accepted.push('new');
  releaseOld?.();
  await delayed;
  assert.deepEqual(accepted, ['new']);
});
