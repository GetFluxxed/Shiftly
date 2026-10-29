// Test-only device storage adapter. Production uses encrypted SecureStore.
import React from 'react';
import { useWorkspace } from '../../src/restoration/WorkspaceProvider';
import type { SessionController } from '../../src/session/controller';
import type { WorkspaceController } from '../../src/restoration/controller';
import { workspaceScope } from '../../src/restoration/policy';
export const workspaceStorage = {
  read: async () => localStorage.getItem('test.workspace'),
  write: async (value:string) => { localStorage.setItem('test.workspace',value); },
  remove: async () => { localStorage.removeItem('test.workspace'); },
};
declare global { interface Window { __workspaceTest: WorkspaceController | null } }
export function WorkspaceGate({session, publicRoute=false, children}:React.PropsWithChildren<{session:SessionController;publicRoute?:boolean}>) {
  const workspace=useWorkspace();
  window.__workspaceTest=workspace.controller;
  const snapshot=React.useSyncExternalStore(session.subscribe,session.getSnapshot,session.getSnapshot);
  if(publicRoute) return <>{children}</>;
  if(snapshot.status!=='ready') return <div>Workspace {snapshot.status}</div>;
  if(!workspace.ready || !snapshot.actor || workspace.scope!==workspaceScope(snapshot.actor,snapshot.stores)) return <div>Restoring workspace</div>;
  return <>{children}</>;
}
