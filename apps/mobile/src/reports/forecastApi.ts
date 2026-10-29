import { ApiError } from '../api/client';
import type { RequestOptions } from '../api/types';
import { newUuid, validProductionId, type ProductionUnit } from '../production/api';

export type ForecastStatus = 'not_requested' | 'queued' | 'processing' | 'ready' | 'failed' | 'unavailable';
export interface ForecastCoverage { windowDays: number; productionReports: number; productionDays: number; shiftReports: number; truncated: boolean }
export interface ForecastDailyFact { date: string; recipeId: string; name: string; batches: number }
export interface ForecastIngredientFact { productId: string; name: string; baseUnit: ProductionUnit; quantity: string | null; usedAmount: string }
export interface ForecastAnalysis {
  summary: string;
  trends: string[];
  recommendations: { recipeId: string; name: string; day: string; batches: number; rationale: string }[];
  risks: string[];
  limitations: string[];
}
export interface ProductionForecast {
  id: string;
  logId: string | null;
  asOf: string;
  generatedAt: string | null;
  model: string;
  stale: boolean;
  coverage: ForecastCoverage;
  facts: { daily: ForecastDailyFact[]; ingredients: ForecastIngredientFact[] };
  analysis: ForecastAnalysis | null;
}
export interface ForecastEnvelope { storeId: number; status: ForecastStatus; forecast: ProductionForecast | null; error: string | null }
type Request = <T>(path: string, options?: RequestOptions) => Promise<T>;

export function createResponseGuard() {
  let generation = 0;
  return { begin: () => ++generation, current: (value: number) => value === generation, invalidate: () => { generation += 1; } };
}

const datePattern = /^\d{4}-\d{2}-\d{2}$/;
const decimalPattern = /^\d{1,15}(?:\.\d{1,9})?$/;
const statuses = new Set<ForecastStatus>(['not_requested', 'queued', 'processing', 'ready', 'failed', 'unavailable']);
function fail(): never { throw new ApiError('The production forecast response could not be verified. Please reload.'); }
function object(value: unknown): asserts value is Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value)) fail(); }
function text(value: unknown, max = 4000): value is string { return typeof value === 'string' && value.length <= max; }
function integer(value: unknown, max = 1_000_000): value is number { return Number.isSafeInteger(value) && Number(value) >= 0 && Number(value) <= max; }
function list(value: unknown, max: number): asserts value is unknown[] { if (!Array.isArray(value) || value.length > max) fail(); }
function strings(value: unknown, max: number): string[] { list(value, max); if (!value.every(item => text(item))) fail(); return value as string[]; }
function productionUnit(value: unknown): value is ProductionUnit { return value === 'each' || value === 'g' || value === 'kg'; }

function coverage(value: unknown): ForecastCoverage {
  object(value);
  if (!integer(value.windowDays, 366) || !integer(value.productionReports) || !integer(value.productionDays, 366)
      || !integer(value.shiftReports) || typeof value.truncated !== 'boolean') fail();
  return value as unknown as ForecastCoverage;
}
function daily(value: unknown): ForecastDailyFact {
  object(value);
  if (!text(value.date, 10) || !datePattern.test(value.date) || !validProductionId(value.recipeId)
      || !text(value.name, 160) || !integer(value.batches, 1_000_000) || value.batches < 1) fail();
  return value as unknown as ForecastDailyFact;
}
function ingredient(value: unknown): ForecastIngredientFact {
  object(value);
  if (!validProductionId(value.productId) || !text(value.name, 160) || !productionUnit(value.baseUnit)
      || (value.quantity !== null && (!text(value.quantity, 32) || !decimalPattern.test(value.quantity)))
      || !text(value.usedAmount, 32) || !decimalPattern.test(value.usedAmount)) fail();
  return value as unknown as ForecastIngredientFact;
}
function analysis(value: unknown): ForecastAnalysis {
  object(value); list(value.recommendations, 100);
  if (!text(value.summary) || !value.recommendations.every(item => {
    try { object(item); return validProductionId(item.recipeId) && text(item.name, 160) && text(item.day, 10) && datePattern.test(item.day)
      && integer(item.batches, 1000) && text(item.rationale); } catch { return false; }
  })) fail();
  return { summary: value.summary, trends: strings(value.trends, 100),
    recommendations: value.recommendations as ForecastAnalysis['recommendations'],
    risks: strings(value.risks, 100), limitations: strings(value.limitations, 100) };
}
function forecast(value: unknown): ProductionForecast {
  object(value); object(value.facts); list(value.facts.daily, 500); list(value.facts.ingredients, 500);
  if (!validProductionId(value.id) || (value.logId !== null && !validProductionId(value.logId))
      || !text(value.asOf, 10) || !datePattern.test(value.asOf)
      || (value.generatedAt !== null && !text(value.generatedAt, 80)) || !text(value.model, 160)
      || typeof value.stale !== 'boolean' || (value.analysis !== null && typeof value.analysis !== 'object')) fail();
  return { id: value.id, logId: value.logId as string | null, asOf: value.asOf,
    generatedAt: value.generatedAt as string | null, model: value.model, stale: value.stale,
    coverage: coverage(value.coverage), facts: { daily: value.facts.daily.map(daily), ingredients: value.facts.ingredients.map(ingredient) },
    analysis: value.analysis === null ? null : analysis(value.analysis) };
}
export function parseForecast(value: unknown): ForecastEnvelope {
  object(value);
  if (!integer(value.storeId) || value.storeId < 1 || !statuses.has(value.status as ForecastStatus)
      || (value.error !== null && !text(value.error)) || (value.forecast !== null && typeof value.forecast !== 'object')) fail();
  return { storeId: value.storeId, status: value.status as ForecastStatus,
    forecast: value.forecast === null ? null : forecast(value.forecast), error: value.error as string | null };
}

export function forecastApi(request: Request) {
  return {
    get: async (logId?: string) => parseForecast(await request('/production/forecast', {
      query: logId ? { logId } : {},
    })),
    request: async (storeId: number, logId?: string, requestId = newUuid()) => parseForecast(await request('/production/forecast', {
      method: 'POST', body: { requestId, expectedStoreId: storeId, ...(logId ? { logId } : {}) },
      uncertainMessage: 'We could not confirm the forecast request. Refresh its status before requesting it again.',
    })),
  };
}
