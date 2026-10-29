import React, { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import type { SessionController } from '../../session/controller';
import type { CheckpointStorage } from '../../restoration/storage';
import { SavedScansController } from './controller';
import { sameScanOwner, type ScanOwner } from './model';
import { scanOwnerFor as ownerFor, prepareSavedScans } from './prepare';
export type { SavedScan, ScanInput } from './model';

const Context = createContext<{
  controller: SavedScansController; prepareOffline: () => Promise<void>;
  offlineReady: boolean; preparationError: string | null;
} | null>(null);

/** The temporary intake has its own durable store, never a UI restoration draft. */
export function SavedScansProvider({ session, storage, children }: PropsWithChildren<{
  session: SessionController; storage: (owner: ScanOwner) => CheckpointStorage;
}>) {
  const [controller] = useState(() => new SavedScansController(storage, owner => {
    const current = ownerFor(session);
    return current !== null && sameScanOwner(owner, current);
  }));
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const [preparationError, setPreparationError] = useState<string | null>(null);
  useEffect(() => {
    let activeScope = '';
    const accept = () => {
      const owner = ownerFor(session), actor = session.getSnapshot().actor;
      const scope = owner ? JSON.stringify([owner, actor?.role, actor?.capabilities]) : '';
      if (scope === activeScope) return;
      activeScope = scope; setPreparationError(null); controller.deactivate();
      if (owner) void controller.activate(owner);
    };
    const unsubscribe = session.subscribe(accept); accept();
    return () => { unsubscribe(); controller.deactivate(); };
  }, [controller, session]);
  const prepareOffline = useCallback(async () => {
    const before = ownerFor(session);
    if (!before) throw new Error('Catalog management access is required.');
    try {
      await prepareSavedScans(session, controller);
      setPreparationError(null);
    } catch (error) {
      const current = ownerFor(session);
      if (current && sameScanOwner(before, current)) setPreparationError(error instanceof Error ? error.message : 'Offline scanning could not be prepared.');
      throw error;
    }
  }, [controller, session]);
  const inbox = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const owner = ownerFor(session);
  const offlineReady = snapshot.offlineCatalogCapture === true && !!owner && inbox.status === 'ready'
    && !!inbox.owner && sameScanOwner(owner, inbox.owner);
  return <Context.Provider value={{ controller, prepareOffline, offlineReady, preparationError }}>{children}</Context.Provider>;
}

export function useSavedScans() {
  const context = useContext(Context);
  if (!context) throw new Error('SavedScansProvider is required.');
  const state = useSyncExternalStore(context.controller.subscribe, context.controller.getSnapshot, context.controller.getSnapshot);
  return { ...context, ...state, error: state.error || context.preparationError };
}
