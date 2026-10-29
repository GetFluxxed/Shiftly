import * as SecureStore from 'expo-secure-store';
import { createCheckpointStorage, type CheckpointStorage } from './storage';

export function secureWorkspaceStorage(origin: string): CheckpointStorage {
  // Keep staging and production workspace checkpoints separate on the same device.
  const namespace = Array.from(origin).map(character => character.charCodeAt(0).toString(16)).join('');
  const prefix = `shiftly.workspace.${namespace}`;
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  return createCheckpointStorage({
    get: key => SecureStore.getItemAsync(key, options),
    set: (key, value) => SecureStore.setItemAsync(key, value, options),
    remove: key => SecureStore.deleteItemAsync(key, options),
  }, prefix);
}
