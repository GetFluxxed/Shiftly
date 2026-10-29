import type { ProductionUnit, RecipeInput, RecipeReferenceIngredient } from './api';

export type DraftIngredient = RecipeInput['ingredients'][number] & {
  name: string;
  sku: string;
  baseUnit: ProductionUnit;
  previousBaseUnit: ProductionUnit | null;
};
export type RecipeDraft = Omit<RecipeInput, 'ingredients' | 'referenceIngredients'> & {
  ingredients: DraftIngredient[];
  requestId: string;
  pending: boolean;
};
export type DraftReferenceIngredient = RecipeReferenceIngredient & { localId: string };

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);
const text = (value: unknown, max: number): value is string => typeof value === 'string' && value.length <= max;
const unit = (value: unknown): value is ProductionUnit => value === 'each' || value === 'g' || value === 'kg';
const section = (value: unknown) => value === undefined || value === 'base' || value === 'variegato';
const exactKeys = (value: Record<string, unknown>, required: string[], optional: string[] = []) =>
  required.every(key => Object.hasOwn(value, key))
  && Object.keys(value).every(key => required.includes(key) || optional.includes(key));

const draftIngredient = (value: unknown): value is DraftIngredient => {
  if (!record(value) || !exactKeys(value,
    ['productId', 'name', 'sku', 'baseUnit', 'previousBaseUnit', 'amount', 'unit'], ['section'])) return false;
  return typeof value.productId === 'string' && uuidPattern.test(value.productId)
    && text(value.name, 160) && text(value.sku, 160) && unit(value.baseUnit)
    && (value.previousBaseUnit === null || unit(value.previousBaseUnit))
    && text(value.amount, 32) && unit(value.unit) && section(value.section);
};

export const validRecipeDraft = (value: unknown): value is RecipeDraft => {
  if (!record(value) || !exactKeys(value,
    ['name', 'yieldAmount', 'yieldUnit', 'instructions', 'ingredients', 'requestId', 'pending'])) return false;
  return text(value.name, 120) && text(value.yieldAmount, 32) && text(value.yieldUnit, 40)
    && text(value.instructions, 4000) && Array.isArray(value.ingredients) && value.ingredients.length <= 50
    && value.ingredients.every(draftIngredient) && typeof value.requestId === 'string'
    && uuidPattern.test(value.requestId) && typeof value.pending === 'boolean';
};

export const validReferenceDraft = (value: unknown): value is DraftReferenceIngredient[] =>
  Array.isArray(value) && value.length <= 50 && value.every(row => record(row)
    && exactKeys(row, ['localId', 'name', 'amount', 'unit'], ['section'])
    && text(row.localId, 200) && text(row.name, 160) && text(row.amount, 32)
    && unit(row.unit) && section(row.section));
