import React, { useRef, useState } from 'react';
import { AppState, Image, Linking, StyleSheet, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import { Body, Button, Card, Heading, Loading, Notice } from '@/src/ui/components';
import { colors } from '@/src/ui/theme';
import { useTask } from '@/src/ui/useTask';
import { InventoryPage, LoadError, useInventory, useInventoryNavigation, useInventoryResource } from '../shared';
import { MutationIdentity, validId } from '../api';
import { receivingApi } from './api';

type Capture = { uri: string; base64: string };
function preferredSize(sizes: string[]) {
  const parsed = sizes.map(value => { const [width, height] = value.split('x').map(Number); return { value, width, height }; })
    .filter(item => Number.isFinite(item.width) && Number.isFinite(item.height) && item.width! * item.height! <= 20_000_000);
  return parsed.sort((a, b) => Math.abs(Math.max(a.width!, a.height!) - 2200) - Math.abs(Math.max(b.width!, b.height!) - 2200))[0]?.value;
}

export function InvoicePhotoScreen() {
  const { invoiceId } = useLocalSearchParams<{ invoiceId: string }>();
  return <InventoryPage title="Scan invoice." backTo={validId(invoiceId) ? { pathname: '/invoices/[invoiceId]', params: { invoiceId } } : '/invoices'}>{validId(invoiceId) ? <PhotoCapture invoiceId={invoiceId} /> : <Notice message="This invoice is unavailable." kind="error" />}</InventoryPage>;
}

function PhotoCapture({ invoiceId }: { invoiceId: string }) {
  const { request, actor } = useInventory(); const api = React.useMemo(() => receivingApi(request), [request]); const identity = useRef(new MutationIdentity()).current; const task = useTask(); const nav = useInventoryNavigation();
  const allowed = !!actor && ['manager', 'owner'].includes(actor.role) && ['receipts.draft', 'receipts.post', 'inventory.view'].every(capability => actor.capabilities.includes(capability));
  const invoice = useInventoryResource(React.useCallback(() => api.invoice(invoiceId), [api, invoiceId]), allowed);
  const [permission, askPermission] = useCameraPermissions(); const camera = useRef<CameraView>(null); const [ready, setReady] = useState(false); const [pictureSize, setPictureSize] = useState<string>(); const [capture, setCapture] = useState<Capture | null>(null); const [focused, setFocused] = useState(true); const [foreground, setForeground] = useState(AppState.currentState === 'active'); const [cameraError, setCameraError] = useState<string | null>(null); const [cameraKey, setCameraKey] = useState(0);
  useFocusEffect(React.useCallback(() => { setFocused(true); return () => { setFocused(false); setReady(false); }; }, []));
  React.useEffect(() => { const listener = AppState.addEventListener('change', state => { const active = state === 'active'; setForeground(active); if (!active) setReady(false); }); return () => listener.remove(); }, []);
  if (!allowed) return <Card><Heading>Receiving access is limited</Heading><Body>Invoice photos are available to managers and owners with inventory receiving access.</Body></Card>;
  if (invoice.loading || !permission) return <Loading label="Preparing invoice camera…" />;
  if (invoice.error || !invoice.data) return <LoadError {...invoice} />;
  if (invoice.data.state === 'closed') return <Card><Heading>Invoice closed</Heading><Body>Closed invoices are read-only. Start a new invoice draft to scan another photo.</Body></Card>;
  if (!invoice.data.photoReadingAvailable) return <Card><Heading>Photo reading unavailable</Heading><Body>You can still enter and match invoice lines manually.</Body><Button title="Back to invoice" variant="secondary" onPress={() => nav.replace({ pathname: '/invoices/[invoiceId]', params: { invoiceId } })} /></Card>;
  if (!permission.granted) return <Card><Heading>Camera permission</Heading><Body>Shiftly needs camera access only while you photograph this invoice. The photo is uploaded only after you choose Read invoice.</Body>{permission.canAskAgain === false ? <Button title="Open settings" onPress={() => { void Linking.openSettings(); }} /> : <Button title="Allow camera" onPress={() => { void askPermission(); }} />}</Card>;
  const take = () => void task.run(async () => { const photo = await camera.current?.takePictureAsync({ base64: true, quality: 0.72, exif: false, skipProcessing: false }); if (!photo?.base64) throw new Error('The invoice photo could not be captured. Please try again.'); const bytes = Math.ceil(photo.base64.length * 0.75); if (bytes > 5 * 1024 * 1024) throw new Error('This photo is too large. Move farther away and retake it.'); return { uri: photo.uri, base64: photo.base64 }; }, setCapture);
  const read = () => { if (!capture) return; void task.run(() => api.uploadPhoto(invoice.data!, capture.base64, identity), () => nav.replace({ pathname: '/invoices/[invoiceId]', params: { invoiceId } })); };
  return <><Notice message={task.error || cameraError} kind="error" />{capture ? <><Card><Heading>Photo preview</Heading><Image source={{ uri: capture.uri }} resizeMode="contain" style={styles.preview} /><Body>This preview is read-only and is not saved for offline use. Retake it if the full invoice is not sharp and visible.</Body></Card><Card><Button title="Read invoice" loading={task.pending} onPress={read} /><Body muted>Read invoice uploads this photo to Shiftly's configured AI provider. It returns suggestions for you to review; it does not change the draft or inventory automatically.</Body><Button title="Retake" variant="secondary" disabled={task.pending} onPress={() => { setCapture(null); setReady(false); setCameraError(null); setCameraKey(value => value + 1); }} /></Card></> : <Card><Heading>Frame the full invoice</Heading><Body>Use even light and keep supplier, invoice number, and every line inside the frame. Photos are not available offline.</Body>{focused && foreground ? <View style={styles.camera}><CameraView key={cameraKey} ref={camera} style={StyleSheet.absoluteFill} facing="back" pictureSize={pictureSize} onMountError={() => { setReady(false); setCameraError('The camera could not start. Check camera access and try again.'); }} onCameraReady={() => { setCameraError(null); setReady(true); void camera.current?.getAvailablePictureSizesAsync().then(sizes => setPictureSize(preferredSize(sizes))).catch(() => undefined); }} /></View> : <Notice message="Return to Shiftly to use the camera." />}<Button title="Take photo" icon="camera-outline" loading={task.pending} disabled={!ready || !focused || !foreground} onPress={take} /></Card>}</>;
}

const styles = StyleSheet.create({ camera: { minHeight: 420, borderRadius: 18, overflow: 'hidden', backgroundColor: colors.ink }, preview: { width: '100%', minHeight: 420, borderRadius: 14, backgroundColor: colors.soft } });
