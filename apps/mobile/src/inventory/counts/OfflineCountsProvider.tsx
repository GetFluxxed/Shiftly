import React, { createContext, useContext, useEffect, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import { ApiError } from '../../api/client';
import type { SessionController } from '../../session/controller';
import { countsApi } from './api';
import { OfflineCountController, type CountOwner, type OfflineCountStorage } from './offline';

const Context = createContext<OfflineCountController | null>(null);

function ownerFor(session: SessionController): CountOwner | null {
  const { status, actor, offlineCountId } = session.getSnapshot();
  if (!['ready', 'offline'].includes(status) || status === 'offline' && !offlineCountId || !actor?.businessId
      || !actor.capabilities.includes('inventory.view')) return null;
  return { userId: actor.userId, businessId: actor.businessId, storeId: actor.storeId };
}

/** Count saves have their own durable store; UI draft eviction never touches them. */
export function OfflineCountsProvider({ session, storage, children }: PropsWithChildren<{
  session: SessionController; storage: OfflineCountStorage;
}>) {
  const [controller] = useState(() => new OfflineCountController(storage, {
    context: () => ({ status: session.getSnapshot().status, owner: ownerFor(session) }),
    api: countsApi(session.request),
    canIncludeCatalog: () => !!session.getSnapshot().actor?.capabilities.includes('counts.submit'),
    revalidate: async () => {
      await session.refreshAccess();
      if (session.getSnapshot().status !== 'ready') throw new ApiError('Reconnect to sync your saved counts.');
    },
    authorizeOffline: async countId => {
      // View-only accounts can read connected counts, but receive no offline grant.
      if (session.getSnapshot().actor?.capabilities.includes('counts.submit')) await session.authorizeOfflineCount(countId);
    },
  }));
  useEffect(() => {
    let activeScope = '';
    const accept = () => {
      const owner = ownerFor(session);
      const actor = session.getSnapshot().actor;
      const scope = owner ? JSON.stringify([owner, actor?.role, actor?.capabilities]) : '';
      if (scope === activeScope) return;
      activeScope = scope;
      controller.activate(null);
      controller.activate(owner);
      if (owner) void controller.restore().catch(() => undefined);
    };
    const unsubscribe = session.subscribe(accept);
    accept();
    // Timers operate only in the foreground. A native build is not promised to
    // upload while suspended; foreground/resume always retries persistent work.
    const retry = () => {
      if (AppState.currentState !== 'active' && AppState.currentState !== null) return;
      if (!['ready', 'offline'].includes(session.getSnapshot().status)) return;
      const state = controller.getSnapshot();
      const canIncludeCatalog = session.getSnapshot().actor?.capabilities.includes('counts.submit');
      if (state.pendingLineIds.length || (state.count && state.count.totalLines > state.lines.length)
          || (canIncludeCatalog && state.count?.catalogProductsAvailable)) {
        void controller.sync().catch(() => undefined);
      }
    };
    const timer = setInterval(retry, 15_000);
    const foreground = AppState.addEventListener('change', state => { if (state === 'active') retry(); });
    return () => { unsubscribe(); clearInterval(timer); foreground.remove(); controller.activate(null); };
  }, [controller, session]);
  return <Context.Provider value={controller}>{children}</Context.Provider>;
}

export function useOfflineCount() {
  const controller = useContext(Context);
  if (!controller) throw new Error('OfflineCountsProvider is required.');
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  return { controller, ...snapshot };
}
