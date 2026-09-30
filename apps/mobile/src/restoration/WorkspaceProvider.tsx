import React, { createContext, useCallback, useContext, useEffect, useRef, useState, useSyncExternalStore, type PropsWithChildren } from 'react';
import { AppState } from 'react-native';
import { useGlobalSearchParams, usePathname, useRouter, type Href } from 'expo-router';
import type { SessionController } from '../session/controller';
import type { CheckpointStorage } from './storage';
import { WorkspaceController } from './controller';
import { savedRoute, workspaceScope } from './policy';

const Context = createContext<WorkspaceController | null>(null);
const empty = { ready: true, scope: null, resume: 0, route: null, message: null };
const noopSubscribe = () => () => {};
const emptySnapshot = () => empty;

export function WorkspaceProvider({ session, storage, children }: PropsWithChildren<{ session: SessionController; storage: CheckpointStorage }>) {
  const [controller] = useState(() => new WorkspaceController(storage));
  useEffect(() => {
    const sync = () => controller.accept(session.getSnapshot());
    const unsubscribe = session.subscribe(sync); sync();
    const state = AppState.addEventListener('change', value => { if (value !== 'active') void controller.flush(); });
    return () => { unsubscribe(); state.remove(); void controller.flush(); };
  }, [controller, session]);
  return <Context.Provider value={controller}>{children}</Context.Provider>;
}

export function useWorkspace() {
  const controller = useContext(Context);
  const state = useSyncExternalStore(controller?.subscribe || noopSubscribe, controller?.getSnapshot || emptySnapshot, controller?.getSnapshot || emptySnapshot);
  return { controller, ...state };
}

export function useWorkspaceCheckpoint() {
  const controller = useContext(Context);
  const scope = controller?.getSnapshot().scope;
  const lease = controller?.getSnapshot().resume;
  return useCallback(async () => {
    if (!controller) return true;
    const saved = await controller.flush();
    const current = controller.getSnapshot();
    return saved && current.ready && current.scope === scope && current.resume === lease;
  }, [controller, scope, lease]);
}

/** Only call for explicitly approved UI fields, never credentials or server data. */
export function useRememberedState<T>(key: string, initial: T | (() => T), baseline = ''):
  [T, React.Dispatch<React.SetStateAction<T>>, () => void] {
  const controller = useContext(Context);
  const scope = controller?.getSnapshot().scope ?? null;
  const lease = controller?.getSnapshot().resume;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const initialRef = useRef(initial); initialRef.current = initial;
  const makeInitial = () => typeof initialRef.current === 'function' ? (initialRef.current as () => T)() : initialRef.current;
  const identity = `${scope}:${key}:${baseline}`;
  const [record, setRecord] = useState(() => ({ identity, value: controller?.read(key, makeInitial(), baseline) ?? makeInitial() }));
  const value = record.identity === identity ? record.value : controller?.read(key, makeInitial(), baseline) ?? makeInitial();
  const latest = useRef(value); latest.current = value;
  const set = useCallback<React.Dispatch<React.SetStateAction<T>>>((action) => {
    // A delayed request from a former account cannot update its replacement.
    if (!mounted.current) return;
    if (controller && (!controller.getSnapshot().ready || controller.getSnapshot().scope !== scope || controller.getSnapshot().resume !== lease)) return;
    const next = typeof action === 'function' ? (action as (previous: T) => T)(latest.current) : action;
    latest.current = next;
    controller?.write(key, next, baseline, scope);
    setRecord({ identity, value: next });
  }, [controller, scope, lease, key, baseline, identity]);
  const reset = useCallback(() => {
    if (!mounted.current) return;
    if (controller && (!controller.getSnapshot().ready || controller.getSnapshot().scope !== scope || controller.getSnapshot().resume !== lease)) return;
    const next = typeof initialRef.current === 'function' ? (initialRef.current as () => T)() : initialRef.current;
    latest.current = next; controller?.remove(key, scope); setRecord({ identity, value: next });
  }, [controller, scope, lease, key, identity]);
  return [value, set, reset];
}

/** Mounted with the root navigator. Saved public/auth links are never restored. */
export function WorkspaceNavigation({ session }: { session: SessionController }) {
  const { controller, ready, scope, resume, route } = useWorkspace();
  const path = usePathname(), params = useGlobalSearchParams();
  const router = useRouter();
  const restored = useRef(0), started = useRef(false);
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  useEffect(() => {
    if (!controller || !ready || !scope || snapshot.status !== 'ready' || !snapshot.actor
        || workspaceScope(snapshot.actor, snapshot.stores) !== scope) return;
    const current = savedRoute(path, params, snapshot.actor);
    if (restored.current !== resume) {
      // A deliberate launch link wins over the previous screen. Warm resumes use
      // the last checkpoint even if remounting the tabs briefly selected Today.
      const explicitLaunch = !started.current && !['/today', '/'].includes(path);
      if (explicitLaunch || ['/activate', '/sign-in'].includes(path)) {
        restored.current = resume; started.current = true;
        if (current) controller.route(current, scope);
        return; // Let an explicit destination render its own access/activation UI.
      }
      const destination = route || current || { pathname: '/today' };
      restored.current = resume; started.current = true;
      if (JSON.stringify(current) !== JSON.stringify(destination)) router.replace(destination as Href);
      controller.route(destination, scope);
      return;
    }
    if (current) controller.route(current, scope);
  }, [controller, ready, scope, resume, route, path, params, router, snapshot]);
  return null;
}
