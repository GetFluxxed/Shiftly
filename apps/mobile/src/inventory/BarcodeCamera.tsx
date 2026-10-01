import Ionicons from '@expo/vector-icons/Ionicons';
import { useFocusEffect } from 'expo-router';
import { BarcodeScanningResult, BarcodeType, CameraView, useCameraPermissions } from 'expo-camera';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, Linking, Pressable, StyleSheet, View } from 'react-native';

import { Body, Button, Card, Heading, Notice } from '@/src/ui/components';
import { colors } from '@/src/ui/theme';

type Props = {
  onScan: (result: { data: string; type: string }) => void;
  onClose: () => void;
};

const BARCODE_TYPES: BarcodeType[] = [
  'ean13', 'ean8', 'upc_a', 'upc_e', 'code128', 'code39', 'code93', 'itf14', 'codabar',
];

export function BarcodeCamera({ onScan, onClose }: Props) {
  const [permission, requestPermission, getPermission] = useCameraPermissions();
  const [focused, setFocused] = useState(true);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const [paused, setPaused] = useState(false);
  const [ready, setReady] = useState(false);
  const [torch, setTorch] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [permissionPending, setPermissionPending] = useState(false);
  const scannedRef = useRef(false);
  const liveRef = useRef(false);
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const permissionPendingRef = useRef(false);

  useFocusEffect(useCallback(() => {
    setFocused(true);
    return () => {
      liveRef.current = false;
      generationRef.current += 1;
      setFocused(false);
      setPaused(true);
    };
  }, []));

  useEffect(() => {
    mountedRef.current = true;
    const stopPreview = () => {
      liveRef.current = false;
      generationRef.current += 1;
      setForeground(false);
      setPaused(true);
    };
    const subscription = AppState.addEventListener('change', state => {
      const isActive = state === 'active';
      setForeground(isActive);
      if (!isActive) {
        stopPreview();
      } else {
        void getPermission().catch(() => {
          if (mountedRef.current) setError('Camera access could not be checked. Try again or enter the barcode instead.');
        });
      }
    });
    const blur = AppState.addEventListener('blur', stopPreview);
    const focus = AppState.addEventListener('focus', () => {
      if (AppState.currentState === 'active') setForeground(true);
    });
    return () => {
      liveRef.current = false;
      mountedRef.current = false;
      subscription.remove();
      blur.remove();
      focus.remove();
    };
  }, [getPermission]);

  const request = useCallback(async () => {
    if (permissionPendingRef.current) return;
    permissionPendingRef.current = true;
    setPermissionPending(true);
    setError(null);
    try {
      await requestPermission();
    } catch {
      if (mountedRef.current) setError('Shiftly could not ask for camera access. You can enter the code instead.');
    } finally {
      permissionPendingRef.current = false;
      if (mountedRef.current) setPermissionPending(false);
    }
  }, [requestPermission]);

  const openSettings = useCallback(async () => {
    setError(null);
    try {
      await Linking.openSettings();
    } catch {
      setError('Device settings could not be opened. Enter the barcode instead.');
    }
  }, []);

  const scan = useCallback((result: BarcodeScanningResult, generation: number) => {
    if (!mountedRef.current || generation !== generationRef.current || !liveRef.current || scannedRef.current) return;
    liveRef.current = false;
    generationRef.current += 1;
    scannedRef.current = true;
    setPaused(true);
    onScan({ data: result.data, type: result.type });
  }, [onScan]);

  const resume = useCallback(() => {
    liveRef.current = false;
    generationRef.current += 1;
    scannedRef.current = false;
    setReady(false);
    setError(null);
    setPaused(false);
  }, []);

  const close = useCallback(() => {
    liveRef.current = false;
    generationRef.current += 1;
    scannedRef.current = true;
    onClose();
  }, [onClose]);

  const canShowCamera = permission?.granted && focused && foreground && !paused && !error;
  const previewGeneration = generationRef.current;

  if (!permission) {
    return <Card>
      <Heading>Scan a product barcode</Heading>
      <Body muted>Checking camera access…</Body>
      <Button title="Enter code instead" variant="quiet" onPress={close} />
    </Card>;
  }

  if (!permission.granted) {
    const blocked = !permission.canAskAgain;
    return <Card>
      <Heading>Camera access needed</Heading>
      <Body>Shiftly uses the camera only while this scanner is open. It does not save or upload images.</Body>
      <Notice kind={blocked ? 'error' : 'info'} message={blocked
        ? 'Camera access is blocked. Open device settings to allow it, or enter the barcode instead.'
        : 'Allow camera access to scan a product barcode.'} />
      {error ? <Notice kind="error" message={error} /> : null}
      {blocked
        ? <Button title="Open settings" icon="settings-outline" onPress={() => { void openSettings(); }} />
        : <Button title="Allow camera" icon="camera-outline" loading={permissionPending} onPress={() => { void request(); }} />}
      <Button title="Enter code instead" variant="quiet" onPress={close} />
    </Card>;
  }

  return <Card style={styles.card}>
    <View>
      <Heading>Scan a product barcode</Heading>
      <Body muted>Fit the whole barcode in the frame. If it is blurry, move back until sharp, then use zoom for small print.</Body>
    </View>
    {canShowCamera ? <View style={styles.preview} accessibilityLabel="Barcode camera preview">
      <CameraView
        active
        facing="back"
        enableTorch={torch}
        // Native zoom is device-dependent; avoid displaying an inaccurate “2×”.
        zoom={zoomLevel / 10}
        barcodeScannerSettings={{ barcodeTypes: BARCODE_TYPES }}
        onCameraReady={() => {
          if (!mountedRef.current || previewGeneration !== generationRef.current) return;
          liveRef.current = true;
          setReady(true);
        }}
        onMountError={event => {
          if (!mountedRef.current || previewGeneration !== generationRef.current) return;
          liveRef.current = false;
          generationRef.current += 1;
          setReady(false);
          setError(event.message || 'The camera could not start.');
        }}
        onBarcodeScanned={result => scan(result, previewGeneration)}
        style={StyleSheet.absoluteFill}
      />
      <View pointerEvents="none" style={styles.shade}>
        <View style={styles.guide} />
      </View>
    </View> : <View style={styles.paused} accessibilityLiveRegion="polite">
      <Ionicons name={error ? 'alert-circle-outline' : 'camera-outline'} size={34} color={error ? colors.danger : colors.primary} />
      <Body>{error || (foreground && focused ? 'Camera paused.' : 'Camera stopped while Shiftly is in the background.')}</Body>
    </View>}
    {error ? <Notice kind="error" message="Try opening the camera again, or enter the barcode manually." /> : null}
    {!canShowCamera && foreground && focused
      ? <Button title="Resume camera" icon="camera-outline" onPress={resume} />
      : null}
    {canShowCamera && ready ? <View style={styles.zoomControls}>
      <Pressable accessibilityRole="button" accessibilityLabel="Zoom out"
        accessibilityState={{ disabled: zoomLevel === 0 }} disabled={zoomLevel === 0}
        onPress={() => setZoomLevel(value => Math.max(0, value - 1))}
        style={[styles.zoomButton, zoomLevel === 0 && styles.disabled]}>
        <Ionicons name="remove" size={22} color={colors.primary} />
      </Pressable>
      <Body>Zoom</Body>
      <Pressable accessibilityRole="button" accessibilityLabel="Zoom in"
        accessibilityState={{ disabled: zoomLevel === 4 }} disabled={zoomLevel === 4}
        onPress={() => setZoomLevel(value => Math.min(4, value + 1))}
        style={[styles.zoomButton, zoomLevel === 4 && styles.disabled]}>
        <Ionicons name="add" size={22} color={colors.primary} />
      </Pressable>
    </View> : null}
    {canShowCamera && ready
      ? <Pressable accessibilityRole="button" accessibilityLabel={torch ? 'Turn flashlight off' : 'Turn flashlight on'}
          accessibilityState={{ checked: torch }} onPress={() => setTorch(value => !value)} style={styles.torch}>
          <Ionicons name={torch ? 'flash' : 'flash-outline'} size={20} color={colors.primary} />
          <Body>{torch ? 'Flashlight on' : 'Flashlight off'}</Body>
        </Pressable>
      : null}
    <Button title="Enter code instead" variant="quiet" onPress={close} />
  </Card>;
}

const styles = StyleSheet.create({
  card: { padding: 16 },
  preview: { height: 320, overflow: 'hidden', borderRadius: 18, backgroundColor: colors.ink },
  shade: { position: 'absolute', inset: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(44, 25, 15, 0.18)' },
  guide: { width: '82%', height: 132, borderWidth: 3, borderColor: colors.onPrimary, borderRadius: 16, backgroundColor: 'transparent' },
  paused: { minHeight: 210, borderRadius: 18, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  zoomControls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 20 },
  zoomButton: { minHeight: 48, minWidth: 48, alignItems: 'center', justifyContent: 'center', borderRadius: 24, backgroundColor: colors.soft },
  disabled: { opacity: 0.4 },
  torch: { minHeight: 48, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 18 },
});
