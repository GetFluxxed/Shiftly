import * as SecureStore from 'expo-secure-store';
import { createOfflineCountStorage } from './storage';

export function secureOfflineCountStorage(origin: string) {
  const namespace = Array.from(origin).map(character => character.charCodeAt(0).toString(16)).join('');
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  return createOfflineCountStorage({
    get: key => SecureStore.getItemAsync(key, options),
    set: (key, value) => SecureStore.setItemAsync(key, value, options),
    remove: key => SecureStore.deleteItemAsync(key, options),
  }, `shiftly.offline-count.${namespace}`);
}
