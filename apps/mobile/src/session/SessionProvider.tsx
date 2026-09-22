import { createContext, useContext, useEffect, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import { apiOrigin, createTransport, ApiError, type Transport } from '../api/client';
import { secureCredentials } from './credentials';
import { SessionController } from './controller';

function buildController() {
  try {
    const origin = apiOrigin(process.env.EXPO_PUBLIC_API_URL, __DEV__);
    return new SessionController(createTransport(origin), secureCredentials(origin));
  } catch (error) {
    const fail = async (): Promise<never> => { throw error instanceof ApiError ? error : new ApiError('The app could not connect to Shiftly.'); };
    return new SessionController({ send: fail } as Transport, { read: fail, write: fail, remove: async () => undefined });
  }
}
const Context = createContext<SessionController | null>(null);
export function SessionProvider({ children }: PropsWithChildren) {
  const [controller] = useState(buildController);
  useEffect(() => {
    void controller.restore();
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active') void controller.retry(); else controller.lock();
    });
    const blur = AppState.addEventListener('blur', controller.lock);
    const focus = AppState.addEventListener('focus', () => {
      if (controller.getSnapshot().status === 'locked') void controller.retry();
    });
    const verification = setInterval(() => {
      if (AppState.currentState === 'active') void controller.refreshAccess();
    }, 60_000);
    return () => { listener.remove(); blur.remove(); focus.remove(); clearInterval(verification); controller.lock(); };
  }, [controller]);
  return <Context.Provider value={controller}>{children}</Context.Provider>;
}
export function useSession() {
  const controller = useContext(Context);
  if (!controller) throw new Error('SessionProvider is required.');
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  return { ...snapshot, signIn: controller.signIn, activate: controller.activate, resetPassword: controller.resetPassword,
    switchStore: controller.switchStore, changePassword: controller.changePassword, signOut: controller.signOut,
    retry: controller.retry, request: controller.request };
}
