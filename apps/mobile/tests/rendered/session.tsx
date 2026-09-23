import React from 'react';
import { SessionController } from '../../src/session/controller';
export const SessionContext = React.createContext<SessionController | null>(null);
export function useSession() {
  const c=React.useContext(SessionContext)!;
  return {...React.useSyncExternalStore(c.subscribe,c.getSnapshot,c.getSnapshot),request:c.request};
}
