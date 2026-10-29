import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { Alert, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Body, Button, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';
import { useTask } from '@/src/ui/useTask';
import { validId, type Package, type StockUnit } from '../api';
import { useInventoryResource } from '../shared';
import { useCounts } from './shared';
import { entryLabel, entryTotal, quantityLabel } from './measurements';
import type { Count, CountLine, Entry } from './api';

type SaveResult = { line: CountLine; count: Count };
type Draft = { mode: 'total' | 'containers' | 'packages'; amount: string; full: string; partial: string; packageCounts: Record<string, string>; unit: StockUnit };
export interface PreparedCountEntry {
  count: Count;
  line: CountLine;
  save: (line: CountLine, entry: Entry) => Promise<SaveResult>;
}

export function CountEntrySheet({ countId, lineId, onClose, onSaved, prepared, pending = false }: {
  countId: string; lineId: string; onClose: () => void; onSaved: (result: SaveResult) => void;
  prepared?: PreparedCountEntry; pending?: boolean;
}) {
  const { api, actor } = useCounts();
  const { width } = useWindowDimensions();
  const closeRequest = useRef(onClose);
  // A prepared editor is a point-in-time local snapshot. Keep it stable while
  // background sync updates the surrounding workspace.
  const preparedSnapshot = useRef(prepared).current;
  const resource = useInventoryResource(useCallback(async () => {
    if (!validId(countId) || !validId(lineId)) throw new Error('This entry is unavailable.');
    const [count, line] = await Promise.all([api.detail(countId), api.line(countId, lineId)]);
    if (count.id !== countId || line.id !== lineId || count.storeId !== actor?.storeId) throw new Error('This entry is unavailable.');
    return { count, line };
  }, [actor?.storeId, api, countId, lineId]), !preparedSnapshot);
  const local = preparedSnapshot ? { count: preparedSnapshot.count, line: preparedSnapshot.line } : null;
  const data = local || resource.data;
  // Keep the native presenter mounted when loading/error/editor content changes.
  // Replacing Modal during its opening animation can strand an iOS touch blocker.
  return <Modal visible transparent animationType={width < 700 ? 'slide' : 'fade'} statusBarTranslucent
    onRequestClose={() => closeRequest.current()} accessibilityViewIsModal>
    <View testID="count-entry-modal" style={[styles.layer, width < 700 ? styles.phoneLayer : styles.wideLayer]}>
      <View style={styles.backdrop} />
      {!preparedSnapshot && resource.loading ? <SheetFrame title="Count entry" onClose={onClose} closeRequest={closeRequest}>
        <Loading label="Loading saved entry…" />
      </SheetFrame> : !preparedSnapshot && (resource.error || !data) ? <SheetFrame title="Count entry" onClose={onClose} closeRequest={closeRequest}>
        <Notice message={resource.error || 'Entry unavailable.'} kind="error" />
        <Button title="Reload entry" variant="secondary" onPress={() => { void resource.refresh(); }} />
      </SheetFrame> : data ? <CountEntryEditor key={`${data.line.id}:${data.line.version}:${data.count.state}`}
        {...data} refresh={preparedSnapshot ? undefined : resource.refresh} preparedSave={preparedSnapshot?.save}
        pending={pending} onClose={onClose} onSaved={onSaved} closeRequest={closeRequest} /> : null}
    </View>
  </Modal>;
}

function CountEntryEditor({ count, line, refresh, preparedSave, pending, onClose, onSaved, closeRequest }: {
  count: Count; line: CountLine; refresh?: () => Promise<void>;
  preparedSave?: PreparedCountEntry['save']; pending: boolean; onClose: () => void; onSaved: (result: SaveResult) => void;
  closeRequest: React.RefObject<() => void>;
}) {
  const { api, identity, canCount } = useCounts();
  const checkpoint = useWorkspaceCheckpoint();
  const task = useTask();
  const initial = line.entry;
  const packages = line.packages || [];
  const activePackages = packages.filter(item => item.active);
  const initialDraft = (): Draft => ({
    mode: initial?.mode || (activePackages.length ? 'packages' : line.containerAmount ? 'containers' : 'total'),
    amount: initial?.mode === 'total' ? initial.amount : '', full: initial?.mode === 'containers' ? String(initial.fullContainers) : '',
    partial: initial?.mode === 'containers' || initial?.mode === 'packages' ? initial.partialAmount : '0',
    packageCounts: Object.fromEntries(activePackages.map(item => [item.id, String(initial?.mode === 'packages' ? initial.packages.find(saved => saved.packageId === item.id)?.count || 0 : 0)])),
    unit: (initial?.mode === 'total' ? initial.unit : initial?.partialUnit || line.baseUnit) as StockUnit,
  });
  const baseline = `${line.version}:${count.state}:${!!count.configurationChanged}:${line.containerAmount ?? 'none'}:${line.baseUnit}:${activePackages.map(item => `${item.id}:${item.version}:${item.amount}`).join(',')}`;
  const [draft, setDraft, resetDraft] = useRememberedState(`inventory.count.${count.id}.line.${line.id}`, initialDraft, baseline);
  const [reloading, setReloading] = useState(false);
  const update = (fields: Partial<Draft>) => setDraft(value => ({ ...value, ...fields }));
  // Keep expansion separate so older quantity drafts retain their exact validated shape.
  const [partialExpanded, setPartialOpen] = useRememberedState(`inventory.count.${count.id}.line.${line.id}.partialExpanded`, false, baseline);
  const partialOpen = draft.partial !== '0' || partialExpanded || initial?.mode === 'containers';
  const entry = makeEntry(draft, activePackages);
  const editable = count.state === 'draft' && canCount && !count.configurationChanged;
  const packageIds = packages.map(item => item.id);
  const dirty = initial === null ? draft.mode === 'total' ? draft.amount !== '' : draft.mode === 'containers' ? draft.full !== '' || draft.partial !== '0' : draft.partial !== '0' || Object.values(draft.packageCounts).some(value => value !== '' && value !== '0') : !sameEntry(entry, initial, packageIds);
  const preservedInactive = initial?.mode === 'packages' ? initial.packages.filter(saved => saved.count > 0 && !activePackages.some(item => item.id === saved.packageId)) : [];
  const total = draft.mode === 'packages' && preservedInactive.length ? null : entryTotal(entry, line);
  const locked = task.pending || reloading;
  const close = () => {
    if (locked) return;
    if (editable && dirty) Alert.alert('Close count entry?', 'Choose what to do with the draft on this device.', [
      { text: 'Keep editing', style: 'cancel' }, { text: 'Keep draft and close', onPress: onClose },
      { text: 'Discard and close', style: 'destructive', onPress: () => { resetDraft(); onClose(); } },
    ]); else onClose();
  };
  const save = () => {
    if (!editable || !dirty || total === null || locked) return;
    void task.run(async () => {
      // The prepared engine performs the authoritative durable local commit.
      // Generic workspace storage is best effort and must not block its queue.
      if (!preparedSave && !await checkpoint()) throw new Error('Your draft could not be secured on this device. Keep it open and try again.');
      return preparedSave ? preparedSave(line, entry) : api.save(count.id, line, entry, identity);
    }, result => { resetDraft(); onSaved(result); });
  };
  const reload = async () => {
    if (locked) return;
    setReloading(true); task.setError(null);
    try { resetDraft(); await refresh?.(); }
    catch (failure) { task.setError(failure instanceof Error ? failure.message : 'The latest entry could not be loaded.'); }
    finally { setReloading(false); }
  };
  return <SheetFrame title="Count entry" onClose={close} closeRequest={closeRequest} locked={locked} footer={editable ? <Button title="Save" loading={task.pending} disabled={!dirty || total === null || reloading} onPress={save} /> : undefined}>
    <View style={styles.productHeader}><View style={styles.flex}><Heading>{line.name}</Heading><Text style={styles.shelf}>{line.shelfName}</Text></View>
      {initial && pending ? <View accessible accessibilityLabel="Waiting to sync" style={styles.pending}><Ionicons name="cloud-upload-outline" size={18} color={colors.muted} /></View>
        : <Text style={[styles.status, initial ? styles.saved : styles.notCounted]}>{initial ? 'Saved' : 'Not counted'}</Text>}
    </View>
    {initial ? <Text style={styles.savedDetail}>{entryLabel(initial, line)}</Text> : null}
    {line.containerAmount && !activePackages.length ? <Text style={styles.reference}>Full container: {quantityLabel(line.containerAmount, line.baseUnit)}</Text> : null}
    {count.configurationChanged ? <Notice message="The store setup changed. Ask an approver to cancel this count and start a fresh one." kind="error" /> : null}
    <Notice message={task.error} kind="error" />
    {editable ? <>
      {(activePackages.length || line.containerAmount || preservedInactive.length) ? <ModeChooser value={draft.mode} packages={activePackages.length > 0} containers={!!line.containerAmount && (!activePackages.length || initial?.mode === 'containers')} disabled={locked} onChange={mode => { update({ mode }); if (mode === 'containers') setPartialOpen(true); }} /> : null}
      {draft.mode === 'packages' ? <View style={styles.entryGroup}>
        {activePackages.map(item => <PackageCount key={item.id} item={item} baseUnit={line.baseUnit} value={draft.packageCounts[item.id] || '0'} disabled={locked} onChange={value => update({ packageCounts: { ...draft.packageCounts, [item.id]: value } })} />)}
        {preservedInactive.length ? <View style={styles.historical}><Text style={styles.historicalTitle}>Saved package details</Text>{preservedInactive.map(saved => <Text key={saved.packageId} style={styles.reference}>{saved.count} × {packages.find(item => item.id === saved.packageId)?.name || 'inactive package'}</Text>)}<Text style={styles.reference}>This package is no longer active. Choose measured total to replace this historical entry before saving.</Text></View> : null}
        <PartialEntry open={partialOpen} setOpen={setPartialOpen} value={draft.partial} unit={draft.unit} baseUnit={line.baseUnit} disabled={locked} label={line.baseUnit === 'each' ? 'Loose items' : 'Loose or partial'} onValue={partial => update({ partial })} onUnit={unit => update({ unit })} />
      </View> : draft.mode === 'containers' ? <View style={styles.entryGroup}>
        <Field label="Full containers" value={draft.full} onChangeText={full => update({ full })} keyboardType="number-pad" maxLength={7} editable={!locked} />
        <PartialEntry open={partialOpen} setOpen={setPartialOpen} value={draft.partial} unit={draft.unit} baseUnit={line.baseUnit} disabled={locked} label="Net partial amount" onValue={partial => update({ partial })} onUnit={unit => update({ unit })} />
      </View> : <View style={styles.amountRow}><View style={styles.flex}><Field label="Measured total" value={draft.amount} onChangeText={amount => update({ amount })} keyboardType={line.baseUnit === 'each' ? 'number-pad' : 'decimal-pad'} maxLength={25} editable={!locked} /></View><UnitControl value={draft.unit} base={line.baseUnit} disabled={locked} onChange={unit => update({ unit })} /></View>}
      <View style={styles.totalRow}><Text style={styles.totalLabel}>Total here</Text><Text style={styles.total}>{total === null ? 'Enter a valid quantity' : quantityLabel(total, line.baseUnit)}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel="Set count to zero" disabled={locked} onPress={() => update({ mode: 'total', amount: '0', unit: line.baseUnit })} style={({ pressed }) => [styles.none, pressed && { opacity: 0.7 }]}><Ionicons name="ban-outline" size={18} color={colors.primary} /><Text style={styles.noneText}>None here</Text></Pressable>
      {task.error && refresh ? <Button title="Reload saved entry" variant="secondary" loading={reloading} disabled={task.pending} onPress={() => { void reload(); }} /> : null}
    </> : <View style={styles.readonly}><Body>Saved total: {quantityLabel(line.quantity, line.baseUnit)}</Body><Body>This saved entry is read-only.</Body><Body muted>An approver can return a submitted count to counting.</Body></View>}
  </SheetFrame>;
}

function SheetFrame({ title, children, footer, onClose, closeRequest, locked = false }: React.PropsWithChildren<{
  title: string; footer?: React.ReactNode; onClose: () => void;
  closeRequest: React.RefObject<() => void>; locked?: boolean;
}>) {
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const phone = width < 700;
  // Android's modal back action must use the same pending/dirty guard as Close.
  useLayoutEffect(() => {
    closeRequest.current = locked ? () => undefined : onClose;
    return () => { closeRequest.current = () => undefined; };
  }, [closeRequest, locked, onClose]);
  return <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    style={[styles.dialog, phone ? [styles.sheet, { maxHeight: Math.max(0, height - insets.top - 12), paddingBottom: insets.bottom }]
      : [styles.centered, { maxHeight: Math.max(0, height - insets.top - insets.bottom - 48) }]]}>
    <View style={styles.header}>
      <Text accessibilityRole="header" style={styles.sheetTitle}>{title}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Close count entry" accessibilityState={{ disabled: locked }}
        disabled={locked} onPress={onClose} style={styles.close}>
        <Ionicons name="close" size={24} color={locked ? colors.muted : colors.primary} />
      </Pressable>
    </View>
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">{children}</ScrollView>
    {footer ? <View style={styles.footer}><View style={styles.saveButton}>{footer}</View></View> : null}
  </KeyboardAvoidingView>;
}

function ModeChooser({ value, packages, containers, disabled, onChange }: { value: Draft['mode']; packages: boolean; containers: boolean; disabled: boolean; onChange: (mode: Draft['mode']) => void }) {
  const options: { mode: Draft['mode']; label: string }[] = [...(packages ? [{ mode: 'packages' as const, label: 'Packages' }] : []), ...(containers ? [{ mode: 'containers' as const, label: 'Containers' }] : []), { mode: 'total', label: 'Measured total' }];
  return <View accessibilityRole="radiogroup" accessibilityLabel="Entry method" style={styles.chooser}>{options.map(option => <Pressable key={option.mode} accessibilityRole="radio" accessibilityLabel={option.label} accessibilityState={{ checked: value === option.mode, disabled }} disabled={disabled} onPress={() => onChange(option.mode)} style={[styles.choice, value === option.mode && styles.choiceSelected]}><Text style={[styles.choiceText, value === option.mode && styles.choiceTextSelected]}>{option.label}</Text></Pressable>)}</View>;
}

function PackageCount({ item, baseUnit, value, disabled, onChange }: { item: Package; baseUnit: StockUnit; value: string; disabled: boolean; onChange: (value: string) => void }) {
  const parsed = /^\d{1,7}$/.test(value) ? Number(value) : 0;
  const detail = item.labelAmount && item.labelUnit ? `${item.labelAmount} ${item.labelUnit === 'lb' ? 'lbs' : item.labelUnit} · ${item.amount} ${baseUnit}` : `${item.amount} ${baseUnit}`;
  return <View style={styles.packageRow}><View style={styles.packageCopy}><Text style={styles.packageName}>{item.name}</Text><Text style={styles.packageDetail}>{detail}</Text></View><View style={styles.packageControls}><Step icon="remove" label={`Remove one ${item.name}`} disabled={disabled || parsed <= 0} onPress={() => onChange(String(parsed - 1))} /><Field label="Count" accessibilityLabel={`${item.name} count`} value={value} onChangeText={onChange} keyboardType="number-pad" maxLength={7} editable={!disabled} style={styles.countField} /><Step icon="add" label={`Add one ${item.name}`} disabled={disabled || parsed >= 1_000_000} onPress={() => onChange(String(parsed + 1))} /></View></View>;
}
function Step({ icon, label, disabled, onPress }: { icon: 'add' | 'remove'; label: string; disabled: boolean; onPress: () => void }) { return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[styles.step, disabled && { opacity: 0.45 }]}><Ionicons name={icon} size={20} color={colors.primary} /></Pressable>; }

function PartialEntry({ open, setOpen, value, unit, baseUnit, disabled, label, onValue, onUnit }: { open: boolean; setOpen: (open: boolean) => void; value: string; unit: StockUnit; baseUnit: StockUnit; disabled: boolean; label: string; onValue: (value: string) => void; onUnit: (unit: StockUnit) => void }) {
  if (!open) return <Pressable accessibilityRole="button" accessibilityLabel={`Add ${label.toLowerCase()}`} disabled={disabled} onPress={() => setOpen(true)} style={styles.addPartial}><Ionicons name="add-circle-outline" size={19} color={colors.primary} /><Text style={styles.noneText}>Add {label.toLowerCase()}</Text></Pressable>;
  return <View style={styles.amountRow}><View style={styles.flex}><Field label={label} value={value} onChangeText={onValue} keyboardType={baseUnit === 'each' ? 'number-pad' : 'decimal-pad'} maxLength={25} editable={!disabled} /></View><UnitControl value={unit} base={baseUnit} disabled={disabled} onChange={onUnit} /></View>;
}
function UnitControl({ value, base, disabled, onChange }: { value: StockUnit; base: StockUnit; disabled: boolean; onChange: (unit: StockUnit) => void }) {
  if (base === 'each') return <View accessibilityLabel="Unit: items" style={styles.singleUnit}><Text style={styles.unitText}>each</Text></View>;
  return <View accessibilityRole="radiogroup" accessibilityLabel="Quantity unit" style={styles.units}>{(['g', 'kg'] as const).map(unit => <Pressable key={unit} accessibilityRole="radio" accessibilityLabel={unit === 'g' ? 'Grams' : 'Kilograms'} accessibilityState={{ checked: unit === value, disabled }} disabled={disabled} onPress={() => onChange(unit)} style={[styles.unit, unit === value && styles.unitSelected]}><Text style={[styles.unitText, unit === value && styles.unitTextSelected]}>{unit}</Text></Pressable>)}</View>;
}
function makeEntry(draft: Draft, packages: Package[]): Entry {
  if (draft.mode === 'total') return { mode: 'total', amount: draft.amount, unit: draft.unit };
  if (draft.mode === 'containers') return { mode: 'containers', fullContainers: /^\d{1,7}$/.test(draft.full) ? Number(draft.full) : NaN, partialAmount: draft.partial, partialUnit: draft.unit };
  return { mode: 'packages', packages: packages.map(item => ({ packageId: item.id, count: /^\d{1,7}$/.test(draft.packageCounts[item.id] || '0') ? Number(draft.packageCounts[item.id] || 0) : NaN })).sort((a, b) => a.packageId.localeCompare(b.packageId)), partialAmount: draft.partial, partialUnit: draft.unit };
}
function sameEntry(left: Entry, right: Entry, packageIds: string[]) {
  if (left.mode !== right.mode) return false;
  if (left.mode === 'total' && right.mode === 'total') return left.amount === right.amount && left.unit === right.unit;
  if (left.mode === 'containers' && right.mode === 'containers') return left.fullContainers === right.fullContainers && left.partialAmount === right.partialAmount && left.partialUnit === right.partialUnit;
  if (left.mode !== 'packages' || right.mode !== 'packages' || left.partialAmount !== right.partialAmount || left.partialUnit !== right.partialUnit) return false;
  const a = new Map(left.packages.map(item => [item.packageId, item.count])), b = new Map(right.packages.map(item => [item.packageId, item.count]));
  return packageIds.every(id => (a.get(id) || 0) === (b.get(id) || 0)) && [...a.keys(), ...b.keys()].every(id => packageIds.includes(id));
}

const styles = StyleSheet.create({
  layer: { flex: 1 }, phoneLayer: { justifyContent: 'flex-end' }, wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 28 }, backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' }, dialog: { width: '100%', backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }, sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24 }, centered: { maxWidth: 600, borderRadius: 24 },
  header: { minHeight: 62, paddingLeft: 18, paddingRight: 10, paddingVertical: 7, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', alignItems: 'center', gap: 8 }, sheetTitle: { flex: 1, minWidth: 0, fontSize: 18, fontWeight: '700', color: colors.ink }, close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }, scroll: { flexShrink: 1 }, content: { padding: 18, gap: 14 }, footer: { flexShrink: 0, padding: 12, paddingHorizontal: 18, backgroundColor: colors.card, borderTopWidth: 1, borderTopColor: colors.line, alignItems: 'flex-end' }, saveButton: { width: '100%', maxWidth: 240 },
  flex: { flex: 1, minWidth: 0 }, productHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 }, shelf: { color: colors.muted, fontSize: 14, lineHeight: 20, marginTop: 2 }, status: { flexShrink: 0, borderRadius: 14, paddingHorizontal: 9, paddingVertical: 5, fontSize: 12, fontWeight: '700', overflow: 'hidden' }, pending: { width: 32, height: 32, flexShrink: 0, alignItems: 'center', justifyContent: 'center' }, saved: { color: colors.success, backgroundColor: colors.successPaper }, notCounted: { color: colors.muted, backgroundColor: colors.soft }, savedDetail: { color: colors.muted, fontSize: 13, lineHeight: 19 }, reference: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  chooser: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, choice: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 13, borderRadius: 22, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.card }, choiceSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, choiceText: { color: colors.primary, fontSize: 13, fontWeight: '700' }, choiceTextSelected: { color: colors.onPrimary },
  entryGroup: { gap: 10 }, packageRow: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 }, packageCopy: { flex: 1, minWidth: 130 }, packageName: { color: colors.ink, fontSize: 15, fontWeight: '700' }, packageDetail: { color: colors.muted, fontSize: 12, marginTop: 2 }, packageControls: { flexDirection: 'row', alignItems: 'flex-end', gap: 6 }, step: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center', marginBottom: 1 }, countField: { width: 70, minHeight: 44, paddingHorizontal: 6, paddingVertical: 8, textAlign: 'center' }, historical: { padding: 10, gap: 3, borderRadius: 12, backgroundColor: colors.soft }, historicalTitle: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  amountRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 }, units: { flexDirection: 'row', borderWidth: 1, borderColor: colors.controlLine, borderRadius: 12, overflow: 'hidden', marginBottom: 1 }, unit: { minWidth: 46, height: 52, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.card }, unitSelected: { backgroundColor: colors.primary }, unitText: { color: colors.primary, fontSize: 14, fontWeight: '700' }, unitTextSelected: { color: colors.onPrimary }, singleUnit: { height: 52, minWidth: 58, paddingHorizontal: 8, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: colors.soft, marginBottom: 1 }, addPartial: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 7, alignSelf: 'flex-start', paddingHorizontal: 3 },
  totalRow: { padding: 12, borderRadius: 14, backgroundColor: colors.blush, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }, totalLabel: { color: colors.primary, fontSize: 13, fontWeight: '700' }, total: { color: colors.ink, fontSize: 18, fontWeight: '700' }, none: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7 }, noneText: { color: colors.primary, fontSize: 14, fontWeight: '700' }, readonly: { padding: 14, borderRadius: 14, backgroundColor: colors.soft, gap: 4 },
});
