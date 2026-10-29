import * as SecureStore from 'expo-secure-store';
import { createCheckpointStorage, type CheckpointStorage } from '../restoration/storage';
import { type OfflineCountPermit, type OfflineCountPermitStore, parseOfflineCountPermit } from './offlinePermit';

export { parseOfflineCountPermit } from './offlinePermit';

export function createOfflineCountPermitStore(storage: CheckpointStorage): OfflineCountPermitStore {
  return {
    read: async () => { const raw = await storage.read(); return raw === null ? null : parseOfflineCountPermit(raw); },
    write: permit => storage.write(JSON.stringify(permit)),
    remove: () => storage.remove(),
  };
}

export function secureOfflineCountPermit(origin: string): OfflineCountPermitStore {
  const namespace = Array.from(origin).map(character => character.charCodeAt(0).toString(16)).join('');
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  const storage = createCheckpointStorage({
    get: key => SecureStore.getItemAsync(key, options),
    set: (key, value) => SecureStore.setItemAsync(key, value, options),
    remove: key => SecureStore.deleteItemAsync(key, options),
  }, `shiftly.offline-count-permit.${namespace}`);
  return createOfflineCountPermitStore(storage);
}
