import React from 'react';
import { createRoot } from 'react-dom/client';
import { AppState, Linking, Pressable, Text } from 'react-native';

// @ts-expect-error Test bundle intentionally bypasses the .web implementation.
import { BarcodeCamera } from '../../src/inventory/BarcodeCamera.tsx';
import { cameraBoundary } from './camera-module';

type State = 'active' | 'background' | 'inactive';
const appStateListeners = new Set<(state: State) => void>();
const appBlurListeners = new Set<() => void>();
const appFocusListeners = new Set<() => void>();
let currentState: State = 'active';
Object.defineProperty(AppState, 'currentState', { configurable: true, get: () => currentState });
AppState.addEventListener = ((event: string, listener: (state: State) => void) => {
  if (event === 'change') appStateListeners.add(listener);
  if (event === 'blur') appBlurListeners.add(listener as () => void);
  if (event === 'focus') appFocusListeners.add(listener as () => void);
  return { remove: () => {
    appStateListeners.delete(listener);
    appBlurListeners.delete(listener as () => void);
    appFocusListeners.delete(listener as () => void);
  } };
}) as typeof AppState.addEventListener;

let settingsCalls = 0;
let settingsReject = false;
Linking.openSettings = async () => {
  settingsCalls += 1;
  if (settingsReject) throw new Error('settings failed');
};

declare global {
  interface Window {
    __cameraTest: {
      permission: typeof cameraBoundary.setPermission;
      requestMode: typeof cameraBoundary.setRequestMode;
      settleRequest: typeof cameraBoundary.settleRequest;
      ready: typeof cameraBoundary.ready;
      scan: typeof cameraBoundary.scan;
      staleScan: typeof cameraBoundary.staleScan;
      mountError: typeof cameraBoundary.mountError;
      appState: (state: State) => void;
      appBlur: () => void;
      appFocus: () => void;
      settingsReject: (reject: boolean) => void;
      snapshot: () => ReturnType<typeof cameraBoundary.snapshot> & { settingsCalls: number };
    };
  }
}

cameraBoundary.reset();
window.__cameraTest = {
  permission: cameraBoundary.setPermission,
  requestMode: cameraBoundary.setRequestMode,
  settleRequest: cameraBoundary.settleRequest,
  ready: cameraBoundary.ready,
  scan: cameraBoundary.scan,
  staleScan: cameraBoundary.staleScan,
  mountError: cameraBoundary.mountError,
  appState(state) {
    currentState = state;
    appStateListeners.forEach(listener => listener(state));
  },
  appBlur() { appBlurListeners.forEach(listener => listener()); },
  appFocus() { appFocusListeners.forEach(listener => listener()); },
  settingsReject(reject) { settingsReject = reject; },
  snapshot: () => ({ ...cameraBoundary.snapshot(), settingsCalls }),
};

function App() {
  const [mounted, setMounted] = React.useState(true);
  const [scans, setScans] = React.useState<Array<{ data: string; type: string }>>([]);
  const [closes, setCloses] = React.useState(0);
  return <>
    <Pressable accessibilityRole="button" accessibilityLabel={mounted ? 'Unmount scanner' : 'Mount scanner'}
      onPress={() => setMounted(value => !value)}><Text>{mounted ? 'Unmount scanner' : 'Mount scanner'}</Text></Pressable>
    {mounted ? <BarcodeCamera onScan={result => setScans(value => [...value, result])}
      onClose={() => setCloses(value => value + 1)} /> : null}
    <Text accessibilityLabel="Scan callback count">{scans.length}</Text>
    <Text accessibilityLabel="Last scan">{scans.length ? JSON.stringify(scans.at(-1)) : ''}</Text>
    <Text accessibilityLabel="Close callback count">{closes}</Text>
  </>;
}

createRoot(document.getElementById('root')!).render(<App />);
