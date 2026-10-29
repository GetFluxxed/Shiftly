import React, { useEffect, useRef, useState } from 'react';
import { Alert, View } from 'react-native';
import { Body, Button, Card, EmptyState, Field, Heading, Loading, Notice, Screen, layout } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { BarcodeCamera } from '../BarcodeCamera';
import { ScanLookup } from '../CatalogScanScreen';
import { InventoryItem, InventoryList } from '../InventoryItem';
import { useInventoryNavigation } from '../shared';
import { useSavedScans, type SavedScan, type ScanInput } from './SavedScansProvider';

const emptyInput: ScanInput = {
  code: '', barcodeType: '', name: '', baseUnit: 'each', containerAmount: '', containerUnit: 'each',
};

export function SavedScansScreen({ offlineMode = false, onBack }: { offlineMode?: boolean; onBack?: () => void }) {
  const session = useSession();
  const navigation = useInventoryNavigation();
  const { controller, status, items, error, offlineReady, prepareOffline } = useSavedScans();
  const [cameraOpen, setCameraOpen] = useState(false);
  const [manualCode, setManualCode] = useState('');
  const [editing, setEditing] = useState<SavedScan | null>(null);
  const [reviewing, setReviewing] = useState<SavedScan | null>(null);
  const [draft, setDraft] = useState<ScanInput>(emptyInput);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<{ message: string; kind: 'error' | 'success' } | null>(null);
  const prepared = useRef(false);
  const isOffline = offlineMode || session.status === 'offline';
  const allowedOffline = Boolean(session.offlineCatalogCapture);
  const canEdit = Boolean(session.actor?.capabilities.includes('catalog.manage'));

  useEffect(() => {
    if (session.status !== 'ready' || prepared.current) return;
    prepared.current = true;
    void prepareOffline().catch(() => undefined);
  }, [prepareOffline, session.status]);

  const back = onBack || (() => navigation.back('/catalog/scan'));
  const recover = async () => { if (status === 'error') await prepareOffline(); };
  const beginMetadata = (saved: SavedScan) => {
    setEditing(saved);
    setDraft({ code: saved.code, barcodeType: saved.barcodeType, name: saved.name, baseUnit: saved.baseUnit,
      containerAmount: saved.containerAmount, containerUnit: saved.containerUnit });
    setNotice({ message: 'Code saved on this device. Add details now, or save and keep scanning.', kind: 'success' });
  };
  const saveRaw = async (code: string, barcodeType = '') => {
    const exact = code.trim();
    if (!exact) return;
    setPending(true); setNotice(null);
    try {
      await recover();
      const saved = await controller.save({ ...emptyInput, code: exact, barcodeType });
      setManualCode(''); setCameraOpen(false); beginMetadata(saved);
    } catch (caught) { setNotice({ message: caught instanceof Error ? caught.message : 'This code could not be saved.', kind: 'error' }); }
    finally { setPending(false); }
  };
  const saveDetails = async (): Promise<boolean> => {
    if (!editing) return false;
    setPending(true); setNotice(null);
    try {
      await recover();
      const saved = await controller.save({ ...draft, code: editing.code, barcodeType: editing.barcodeType }, editing.id);
      setEditing(saved); setDraft({ code: saved.code, barcodeType: saved.barcodeType, name: saved.name, baseUnit: saved.baseUnit,
        containerAmount: saved.containerAmount, containerUnit: saved.containerUnit });
      setNotice({ message: 'Saved scan details updated.', kind: 'success' }); return true;
    } catch (caught) {
      setNotice({ message: caught instanceof Error ? caught.message : 'The details could not be saved. Your edits are still here.', kind: 'error' });
      return false;
    } finally { setPending(false); }
  };
  const discard = (item: SavedScan) => Alert.alert('Discard this saved scan?', `The code ${item.code} will be removed from this device.`, [
    { text: 'Keep scan', style: 'cancel' },
    { text: 'Discard scan', style: 'destructive', onPress: () => { void recover().then(() => controller.remove(item.id)).then(() => {
      if (editing?.id === item.id) setEditing(null); if (reviewing?.id === item.id) setReviewing(null);
    }).catch(() => setNotice({ message: 'The saved scan could not be discarded.', kind: 'error' })); } },
  ]);
  const done = async (item: SavedScan) => {
    setPending(true); setNotice(null);
    try { await recover(); await controller.remove(item.id); setReviewing(null); setNotice({ message: 'Saved scan completed.', kind: 'success' }); }
    catch { setNotice({ message: 'The completed scan could not be removed. Try again; it is still saved on this device.', kind: 'error' }); }
    finally { setPending(false); }
  };

  if (reviewing && !isOffline) return <ScanLookup key={`${reviewing.id}:${reviewing.updatedAt}`} code={reviewing.code}
    barcodeType={reviewing.barcodeType} savedScan={reviewing} onNext={() => setReviewing(null)} onChange={() => setReviewing(null)}
    onDone={() => { void done(reviewing); }} completing={pending} completionError={notice?.kind === 'error' ? notice.message : null} />;

  return <Screen title="Saved scans" eyebrow="Inventory" subtitle={isOffline ? 'Offline catalog capture' : 'Review before adding to the company catalog'} compact>
    {!offlineMode || onBack ? <Button title={offlineMode ? 'Back to count' : 'Back to scanner'} variant="quiet" icon="arrow-back" disabled={pending} onPress={back} /> : null}
    {isOffline ? <Button title="Reconnect" variant="secondary" icon="cloud-outline" loading={session.busy}
      onPress={() => { void session.retry(); }} /> : null}
    {!isOffline && !canEdit ? <Card><Heading>Catalog management access is required</Heading>
      <Body>Your account can view products, but saved catalog capture is unavailable.</Body></Card>
      : isOffline && !allowedOffline ? <Card><Heading>Reconnect to capture catalog codes</Heading>
      <Body>Connect once with catalog access before saving codes offline.</Body></Card> : <>
      {status === 'loading' ? <Loading label="Opening saved scans…" /> : null}
      <Notice message={error} kind="error" />
      {!isOffline && offlineReady ? <Notice message="Ready for offline scanning." kind="success" /> : null}
      {!isOffline && status !== 'loading' && !offlineReady ? <Notice message="Offline scan capture is not ready on this device. Try again while connected." kind="error" /> : null}
      {(status === 'error' || !isOffline && status !== 'loading' && !offlineReady) ? <Button title="Retry saved scans" variant="secondary" loading={pending}
        onPress={() => { setPending(true); setNotice(null); void prepareOffline().catch(caught => setNotice({
          message: caught instanceof Error ? caught.message : 'Saved scans could not be prepared.', kind: 'error',
        })).finally(() => setPending(false)); }} /> : null}
      <Notice message={notice?.message || null} kind={notice?.kind} />
      {cameraOpen ? <BarcodeCamera onScan={result => { void saveRaw(result.data, result.type); }} onClose={() => setCameraOpen(false)} /> : <Card>
        <Heading>Capture a code</Heading>
        <Body muted>The code is saved on this device before you add optional product details. No product is created until an online review succeeds.</Body>
        <Button title="Open camera" icon="camera-outline" disabled={pending || status !== 'ready'} onPress={() => setCameraOpen(true)} />
        <Field label="Barcode or SKU" value={manualCode} maxLength={64} editable={!pending} autoCapitalize="none" autoCorrect={false}
          returnKeyType="done" hint="Leading zeros are kept." onChangeText={setManualCode}
          onSubmitEditing={() => { void saveRaw(manualCode); }} />
        <Button title="Save code" variant="secondary" loading={pending} disabled={!manualCode.trim() || status !== 'ready'}
          onPress={() => { void saveRaw(manualCode); }} />
      </Card>}
      {editing ? <MetadataEditor draft={draft} setDraft={setDraft} pending={pending} onSave={saveDetails}
        onSaveAndScan={async () => { if (await saveDetails()) { setEditing(null); setNotice(null); setCameraOpen(true); } }}
        onCancel={() => { setEditing(null); setNotice(null); }} onDiscard={() => discard(editing)} /> : null}
      <Card><Heading>Inbox ({items.length}/100)</Heading>
        {items.length === 0 ? <EmptyState icon="barcode-outline" title="No saved scans" description="Scan a barcode or enter a SKU to keep it for review." />
          : <InventoryList>{items.map(item => <InventoryItem key={item.id} title={item.name || item.code}
            subtitle={item.name ? `Code ${item.code}` : 'Product details not added'}
            detail={item.containerAmount ? `${item.containerAmount} ${item.containerUnit} per container · count in ${item.baseUnit}` : undefined}
            label={`Edit saved scan: ${item.name || item.code}`} disabled={pending} onPress={() => beginMetadata(item)}
            action={!isOffline ? { label: `Review saved scan: ${item.name || item.code}`, title: 'Review', icon: 'cloud-outline',
              disabled: pending, onPress: () => { setEditing(null); setReviewing(item); } } : undefined} />)}</InventoryList>}
      </Card>
    </>}
  </Screen>;
}

function MetadataEditor({ draft, setDraft, pending, onSave, onSaveAndScan, onCancel, onDiscard }: {
  draft: ScanInput; setDraft: React.Dispatch<React.SetStateAction<ScanInput>>; pending: boolean;
  onSave: () => Promise<boolean>; onSaveAndScan: () => Promise<void>; onCancel: () => void; onDiscard: () => void;
}) {
  const units: Array<{ label: string; baseUnit: ScanInput['baseUnit']; containerUnit: ScanInput['containerUnit'] }> = [
    { label: 'Each', baseUnit: 'each', containerUnit: 'each' }, { label: 'Grams', baseUnit: 'g', containerUnit: 'g' },
    { label: 'Kilograms', baseUnit: 'kg', containerUnit: 'kg' }, { label: 'Pounds (lbs)', baseUnit: 'kg', containerUnit: 'lb' },
  ];
  return <Card><Heading>Optional details</Heading>
    <Field label="Product name" value={draft.name} maxLength={160} editable={!pending}
      onChangeText={name => setDraft(value => ({ ...value, name }))} />
    <View style={layout.wrap}>{units.map(unit => {
      const selected = draft.baseUnit === unit.baseUnit && draft.containerUnit === unit.containerUnit;
      return <Button key={unit.containerUnit} title={`${selected ? '✓ ' : ''}${unit.label}`} variant={selected ? 'secondary' : 'quiet'} disabled={pending}
        onPress={() => setDraft(value => ({ ...value, baseUnit: unit.baseUnit, containerUnit: unit.containerUnit,
          containerAmount: unit.baseUnit === 'each' ? '1' : value.containerAmount }))} />;
    })}</View>
    <Field label={`Full container amount (${draft.containerUnit})`} value={draft.containerAmount} keyboardType="decimal-pad" maxLength={19}
      editable={!pending} hint="Leave blank if unknown." onChangeText={containerAmount => setDraft(value => ({ ...value, containerAmount }))} />
    <Button title="Save optional details" loading={pending} onPress={() => { void onSave(); }} />
    <Button title="Save and scan another" variant="secondary" icon="camera-outline" disabled={pending} onPress={() => { void onSaveAndScan(); }} />
    <Button title="Cancel detail edits" variant="quiet" disabled={pending} onPress={onCancel} />
    <Button title="Discard saved scan" variant="danger" disabled={pending} onPress={onDiscard} />
  </Card>;
}
