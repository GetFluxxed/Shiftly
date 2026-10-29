import { createCheckpointStorage, type CheckpointStorage } from '../../src/restoration/storage';
import { scanOwnerKey, type ScanOwner } from '../../src/inventory/scans/model';

let failNextWrite = false;
export const savedScansTest = {
  failNextWrite: () => { failNextWrite = true; },
  failReadsAfterReload: () => localStorage.setItem('test.saved-scans.fail-read', '1'),
  clearReadFailure: () => localStorage.removeItem('test.saved-scans.fail-read'),
  delayNextReadAfterReload: (milliseconds: number) => localStorage.setItem('test.saved-scans.read-delay', String(milliseconds)),
};

export function savedScansStorage(owner: ScanOwner): CheckpointStorage {
  const prefix = `test.saved-scans.${scanOwnerKey(owner)}`;
  return createCheckpointStorage({
    get: async key => {
      if (key.endsWith('.manifest')) {
        if (localStorage.getItem('test.saved-scans.fail-read') === '1') {
          throw new Error('Simulated saved scan read failure');
        }
        const delay = Number(localStorage.getItem('test.saved-scans.read-delay') || '0');
        if (delay > 0) {
          localStorage.removeItem('test.saved-scans.read-delay');
          await new Promise(resolve => setTimeout(resolve, Math.min(delay, 5_000)));
        }
      }
      return localStorage.getItem(key);
    },
    set: async (key, value) => {
      if (failNextWrite) { failNextWrite = false; throw new Error('Simulated saved scan write failure'); }
      localStorage.setItem(key, value);
    },
    remove: async key => { localStorage.removeItem(key); },
  }, prefix);
}
