import * as SecureStore from 'expo-secure-store';
import { createCheckpointStorage, type CheckpointStorage } from '../../restoration/storage';
import { scanOwnerKey, type ScanOwner } from './model';

export function secureSavedScansStorage(origin: string): (owner: ScanOwner) => CheckpointStorage {
  if (!origin.trim()) throw new Error('Saved scan storage origin is invalid');
  const namespace = Array.from(origin).map(character => character.codePointAt(0)!.toString(16).padStart(6, '0')).join('');
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  return owner => createCheckpointStorage({
    get: key => SecureStore.getItemAsync(key, options),
    set: (key, value) => SecureStore.setItemAsync(key, value, options),
    remove: key => SecureStore.deleteItemAsync(key, options),
  }, `shiftly.saved-scans.${namespace}.${scanOwnerKey(owner)}`);
}
