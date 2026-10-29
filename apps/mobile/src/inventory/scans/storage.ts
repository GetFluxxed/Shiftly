import type { CheckpointStorage } from '../../restoration/storage';
import { MAX_SAVED_SCANS, parseSavedScan, parseScanOwner, sameScanOwner, type SavedScan, type ScanOwner } from './model';

type Document = { version: 1; owner: ScanOwner; items: SavedScan[] };

export async function readSavedScans(storage: CheckpointStorage, owner: ScanOwner): Promise<SavedScan[]> {
  const raw = await storage.read();
  if (raw === null) return [];
  let candidate: unknown;
  try { candidate = JSON.parse(raw); } catch { throw new Error('Saved scan inbox is malformed'); }
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) throw new Error('Saved scan inbox is malformed');
  const value = candidate as Record<string, unknown>;
  if (Object.keys(value).length !== 3 || value.version !== 1 || !('owner' in value) || !Array.isArray(value.items)
      || value.items.length > MAX_SAVED_SCANS) throw new Error('Saved scan inbox is malformed');
  const storedOwner = parseScanOwner(value.owner);
  if (!sameScanOwner(owner, storedOwner)) throw new Error('Saved scan inbox belongs to another account or store');
  const items = value.items.map(parseSavedScan);
  if (new Set(items.map(item => item.id)).size !== items.length
      || new Set(items.map(item => `${item.code}\u0000${item.barcodeType}`)).size !== items.length) {
    throw new Error('Saved scan inbox is malformed');
  }
  return items;
}

export function writeSavedScans(storage: CheckpointStorage, owner: ScanOwner, items: readonly SavedScan[]): Promise<void> {
  if (items.length > MAX_SAVED_SCANS) throw new Error(`Saved scan inbox is limited to ${MAX_SAVED_SCANS} items`);
  const parsed = items.map(parseSavedScan);
  if (new Set(parsed.map(item => item.id)).size !== parsed.length
      || new Set(parsed.map(item => `${item.code}\u0000${item.barcodeType}`)).size !== parsed.length) {
    throw new Error('Saved scan inbox is malformed');
  }
  const document: Document = { version: 1, owner: parseScanOwner(owner), items: parsed };
  return storage.write(JSON.stringify(document));
}
