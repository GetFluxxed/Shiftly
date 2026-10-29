import React from 'react';
import { SessionController } from '../../src/session/controller';
export const SessionContext = React.createContext<SessionController | null>(null);
export function useSession() {
  const c=React.useContext(SessionContext)!;
  return {...React.useSyncExternalStore(c.subscribe,c.getSnapshot,c.getSnapshot),request:c.request,signIn:c.signIn,activate:c.activate,invitationDetails:c.invitationDetails,resetPassword:c.resetPassword,signOut:c.signOut,switchStore:c.switchStore,changePassword:c.changePassword,retry:c.retry,transferOwnership:c.transferOwnership};
}
