import * as SecureStore from 'expo-secure-store';
import type { CredentialStore } from './controller';

export function secureCredentials(origin: string): CredentialStore {
  // Keep staging and production credentials separate on the same device.
  const key = `shiftly.session.${Array.from(origin).map(c => c.charCodeAt(0).toString(16)).join('')}`;
  const options = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };
  return {
    read: () => SecureStore.getItemAsync(key, options),
    write: token => SecureStore.setItemAsync(key, token, options),
    remove: () => SecureStore.deleteItemAsync(key, options),
  };
}
