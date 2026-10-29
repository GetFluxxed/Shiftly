export type ScanOwner = { userId: number; businessId: number; storeId: number };

export type ScanInput = {
  code: string;
  barcodeType: string;
  name: string;
  baseUnit: 'each' | 'g' | 'kg';
  containerAmount: string;
  containerUnit: 'each' | 'g' | 'kg' | 'lb';
};

export type SavedScan = ScanInput & { id: string; createdAt: number; updatedAt: number };

export const MAX_SAVED_SCANS = 100;

const INPUT_KEYS = ['code', 'barcodeType', 'name', 'baseUnit', 'containerAmount', 'containerUnit'] as const;
const SAVED_KEYS = [...INPUT_KEYS, 'id', 'createdAt', 'updatedAt'] as const;
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[], message: string): void {
  const actual = Object.keys(value);
  if (actual.length !== keys.length || actual.some(key => !keys.includes(key))) throw new Error(message);
}

export function parseScanOwner(value: unknown): ScanOwner {
  const item = record(value, 'Saved scan owner is invalid');
  exactKeys(item, ['userId', 'businessId', 'storeId'], 'Saved scan owner is invalid');
  if (![item.userId, item.businessId, item.storeId].every(id => Number.isSafeInteger(id) && Number(id) > 0)) {
    throw new Error('Saved scan owner is invalid');
  }
  return { userId: Number(item.userId), businessId: Number(item.businessId), storeId: Number(item.storeId) };
}

export function sameScanOwner(left: ScanOwner, right: ScanOwner): boolean {
  return left.userId === right.userId && left.businessId === right.businessId && left.storeId === right.storeId;
}

export function scanOwnerKey(owner: ScanOwner): string {
  const valid = parseScanOwner(owner);
  return `${valid.userId}.${valid.businessId}.${valid.storeId}`;
}

export function parseScanInput(value: unknown): ScanInput {
  const item = record(value, 'Saved scan is invalid');
  exactKeys(item, INPUT_KEYS, 'Saved scan is invalid');
  if (typeof item.code !== 'string' || typeof item.barcodeType !== 'string' || typeof item.name !== 'string'
      || typeof item.containerAmount !== 'string') throw new Error('Saved scan is invalid');
  const code = item.code.trim();
  const barcodeType = item.barcodeType.trim();
  const name = item.name.trim();
  const containerAmount = item.containerAmount.trim();
  if (!code || code.length > 64 || barcodeType.length > 96 || name.length > 160) {
    throw new Error('Saved scan is invalid');
  }
  if (item.baseUnit !== 'each' && item.baseUnit !== 'g' && item.baseUnit !== 'kg') throw new Error('Saved scan is invalid');
  if (item.containerUnit !== 'each' && item.containerUnit !== 'g' && item.containerUnit !== 'kg' && item.containerUnit !== 'lb') {
    throw new Error('Saved scan is invalid');
  }
  if ((item.baseUnit === 'each') !== (item.containerUnit === 'each')) throw new Error('Saved scan units are incompatible');
  if (containerAmount) {
    const fractionLimit = item.containerUnit === 'lb' ? 6 : 9;
    const decimal = new RegExp(`^(?:0|[1-9]\\d{0,8})(?:\\.\\d{1,${fractionLimit}})?$`);
    if (!decimal.test(containerAmount) || Number(containerAmount) <= 0
        || (item.containerUnit === 'each' && containerAmount.includes('.'))) {
      throw new Error('Saved scan container amount is invalid');
    }
  }
  return { code, barcodeType, name, baseUnit: item.baseUnit, containerAmount, containerUnit: item.containerUnit };
}

export function parseSavedScan(value: unknown): SavedScan {
  const item = record(value, 'Saved scan is malformed');
  exactKeys(item, SAVED_KEYS, 'Saved scan is malformed');
  const input = parseScanInput(Object.fromEntries(INPUT_KEYS.map(key => [key, item[key]])));
  if (typeof item.id !== 'string' || !ID.test(item.id) || !Number.isFinite(item.createdAt)
      || !Number.isFinite(item.updatedAt) || Number(item.createdAt) <= 0 || Number(item.updatedAt) < Number(item.createdAt)) {
    throw new Error('Saved scan is malformed');
  }
  return { ...input, id: item.id, createdAt: Number(item.createdAt), updatedAt: Number(item.updatedAt) };
}

export function validSavedScanId(value: string): boolean {
  return ID.test(value);
}
