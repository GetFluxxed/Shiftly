import React from 'react';
import { View } from 'react-native';

type Permission = { granted: boolean; canAskAgain: boolean } | null;
type CameraProps = {
  zoom?: number;
  barcodeScannerSettings?: { barcodeTypes: string[] };
  onCameraReady?: () => void;
  onMountError?: (event: { message?: string }) => void;
  onBarcodeScanned?: (result: { data: string; type: string }) => void;
};

let permission: Permission = null;
let requestMode: 'grant' | 'deny' | 'blocked' | 'pending' | 'reject' = 'grant';
let requestCalls = 0;
let getCalls = 0;
let mountedCamera: CameraProps | null = null;
let lastCamera: CameraProps | null = null;
let settlePending: ((value: Permission) => void) | null = null;
const listeners = new Set<() => void>();

function publish() { listeners.forEach(listener => listener()); }
function setPermission(value: Permission) { permission = value; publish(); }

async function requestPermission() {
  requestCalls += 1;
  if (requestMode === 'reject') throw new Error('permission request failed');
  if (requestMode === 'pending') {
    const result = await new Promise<Permission>(resolve => { settlePending = resolve; });
    setPermission(result);
    return result;
  }
  const result = requestMode === 'grant'
    ? { granted: true, canAskAgain: true }
    : { granted: false, canAskAgain: requestMode !== 'blocked' };
  setPermission(result);
  return result;
}

async function getPermission() {
  getCalls += 1;
  return permission;
}

export function useCameraPermissions() {
  const current = React.useSyncExternalStore(
    listener => { listeners.add(listener); return () => listeners.delete(listener); },
    () => permission,
    () => permission,
  );
  return [current, requestPermission, getPermission] as const;
}

export function CameraView(props: CameraProps) {
  React.useEffect(() => {
    mountedCamera = props;
    lastCamera = props;
    return () => { if (mountedCamera === props) mountedCamera = null; };
  }, [props]);
  return <View accessibilityLabel="Fake native camera boundary" />;
}

export type BarcodeScanningResult = { data: string; type: string };
export type BarcodeType = string;

export const cameraBoundary = {
  reset() {
    permission = null;
    requestMode = 'grant';
    requestCalls = 0;
    getCalls = 0;
    mountedCamera = null;
    lastCamera = null;
    settlePending = null;
    publish();
  },
  setPermission,
  setRequestMode(value: typeof requestMode) { requestMode = value; },
  settleRequest(value: Exclude<Permission, null>) {
    const settle = settlePending;
    settlePending = null;
    settle?.(value);
  },
  ready() { mountedCamera?.onCameraReady?.(); },
  scan(data: string, type = 'ean13') { mountedCamera?.onBarcodeScanned?.({ data, type }); },
  staleScan(data: string, type = 'ean13') { lastCamera?.onBarcodeScanned?.({ data, type }); },
  mountError(message = '') { mountedCamera?.onMountError?.({ message }); },
  snapshot() { return {
    requestCalls, getCalls, cameraMounted: Boolean(mountedCamera),
    zoom: mountedCamera?.zoom, barcodeTypes: mountedCamera?.barcodeScannerSettings?.barcodeTypes,
  }; },
};
