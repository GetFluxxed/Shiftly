import React, { useCallback } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useLocalSearchParams, type Href } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId, type StockUnit } from '../api';
import { InventoryPage, LoadError, useInventoryNavigation, useInventoryResource } from '../shared';
import { useCounts, UnitButtons, countBackTo, countRouteParams } from './shared';
import { entryLabel, entryTotal, quantityLabel } from './measurements';
import type { Count, CountLine, Entry } from './api';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';

export function CountEntryScreen() {
  const { countId, lineId, returnTo } = useLocalSearchParams<{ countId: string; lineId: string; returnTo?: string }>();
  const fallback = validId(countId) ? ({ pathname: '/counts/[countId]', params: { countId, ...countRouteParams(returnTo) } } as Href) : countBackTo(returnTo);
  return validId(countId) && validId(lineId) ? <EntryLoader countId={countId} lineId={lineId} returnTo={returnTo} /> : <InventoryPage title="Count this location." backTo={fallback}><Notice message="This entry is unavailable." kind="error" /></InventoryPage>;
}
function EntryLoader({ countId, lineId, returnTo }: { countId: string; lineId: string; returnTo?: string }) {
  const { api, actor } = useCounts();
  const resource = useInventoryResource(useCallback(async () => {
    const [count, line] = await Promise.all([api.detail(countId), api.line(countId, lineId)]); return { count, line };
  }, [api, countId, lineId]));
  const fallback = { pathname: '/counts/[countId]', params: { countId, ...countRouteParams(returnTo) } } as const;
  if (resource.loading) return <InventoryPage title="Count this location." backTo={fallback}><Loading label="Loading saved entry…" /></InventoryPage>;
  if (resource.error || !resource.data || resource.data.count.storeId !== actor?.storeId) return <InventoryPage title="Count this location." backTo={fallback}><LoadError error={resource.error || 'Entry unavailable.'} refresh={resource.refresh} /></InventoryPage>;
  return <EntryForm key={`${resource.data.line.id}:${resource.data.line.version}:${resource.data.count.state}`} {...resource.data} returnTo={returnTo} refresh={resource.refresh} />;
}
function EntryForm({ count, line, returnTo, refresh }: { count: Count; line: CountLine; returnTo?: string; refresh: () => Promise<void> }) {
  const { api, identity, canCount } = useCounts(); const nav = useInventoryNavigation(); const task = useTask();
  const initial = line.entry;
  const activePackages = (line.packages || []).filter(item => item.active);
  const initialDraft = () => ({ mode: initial?.mode || (activePackages.length ? 'packages' : line.containerAmount ? 'containers' : 'total') as 'total' | 'containers' | 'packages', amount: initial?.mode === 'total' ? initial.amount : '',
    full: initial?.mode === 'containers' ? String(initial.fullContainers) : '', partial: initial?.mode === 'containers' || initial?.mode === 'packages' ? initial.partialAmount : '0',
    packageCounts: Object.fromEntries(activePackages.map(item => [item.id, String(initial?.mode === 'packages' ? initial.packages.find(saved => saved.packageId === item.id)?.count || 0 : 0)])),
    unit: (initial?.mode === 'total' ? initial.unit : initial?.partialUnit || line.baseUnit) as StockUnit });
  const baseline = `${line.version}:${count.state}:${!!count.configurationChanged}:${line.containerAmount ?? 'none'}:${line.baseUnit}:${activePackages.map(item => `${item.id}:${item.version}:${item.amount}`).join(',')}`;
  const [draft, setDraft, resetDraft] = useRememberedState(`inventory.count.${count.id}.line.${line.id}`, initialDraft, baseline);
  const { mode, amount, full, partial, unit, packageCounts } = draft;
  const update = (fields: Partial<typeof draft>) => setDraft(value => ({ ...value, ...fields }));
  const entry: Entry = mode === 'total' ? { mode, amount, unit } : mode === 'containers' ? { mode, fullContainers: /^\d{1,7}$/.test(full) ? Number(full) : NaN, partialAmount: partial, partialUnit: unit }
    : { mode, packages: activePackages.map(item => ({ packageId: item.id, count: /^\d{1,7}$/.test(packageCounts[item.id] || '0') ? Number(packageCounts[item.id] || 0) : NaN })).sort((a, b) => a.packageId.localeCompare(b.packageId)), partialAmount: partial, partialUnit: unit };
  const total = entryTotal(entry, line), editable = count.state === 'draft' && canCount && !count.configurationChanged;
  const dirty = initial === null ? amount !== '' || full !== '' || partial !== '0' || Object.values(packageCounts).some(value => value !== '' && value !== '0') : !sameEntry(entry, initial, activePackages.map(item => item.id));
  const fallback = { pathname: '/counts/[countId]', params: { countId: count.id, ...countRouteParams(returnTo) } } as const;
  const back = () => nav.back(fallback);
  const leave = () => { if (editable && dirty) Alert.alert('Leave unsaved entry?', 'Your draft is kept on this device unless you discard it.', [{ text: 'Keep editing', style: 'cancel' }, { text: 'Keep draft and go back', onPress: back }, { text: 'Discard and go back', style: 'destructive', onPress: () => { resetDraft(); back(); } }]); else back(); };
  const save = (value: Entry) => { void task.run(() => api.save(count.id, line, value, identity), () => { resetDraft(); back(); }); };
  return <InventoryPage title="Count this location." backTo={fallback} onBack={leave} backDisabled={task.pending}><Card><Heading>{line.name}</Heading><Body muted>{line.shelfName}</Body>
    <Body>Saved quantity: {quantityLabel(line.quantity, line.baseUnit)}</Body><Body muted>{entryLabel(initial, line)}</Body>
    {line.containerAmount ? <Body>Full-container reference: {quantityLabel(line.containerAmount, line.baseUnit)}</Body> : null}
    {count.configurationChanged ? <Notice message="The store setup changed. Ask an approver to cancel this count and start a fresh one." kind="error" /> : null}
  </Card>
  {editable ? <Card><Heading>What is here now?</Heading><Body>At {line.shelfName} only. Exclude packaging weight.</Body>
    <Notice message={task.error} kind="error" />
    {activePackages.length ? <Button title="Packages + loose amount" variant={mode === 'packages' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => update({ mode: 'packages' })} /> : null}
    {line.containerAmount && (!activePackages.length || initial?.mode === 'containers') ? <Button title="Full containers + partial" variant={mode === 'containers' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => update({ mode: 'containers' })} /> : null}
    {(line.containerAmount || activePackages.length) ? <Button title="Enter a measured total" variant={mode === 'total' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => update({ mode: 'total' })} /> : null}
    {mode === 'containers' ? <><Field label="Full containers" value={full} onChangeText={full => update({ full })} keyboardType="number-pad" maxLength={7} editable={!task.pending} />
      <Field label="Combined net partial amount" value={partial} onChangeText={partial => update({ partial })} keyboardType="decimal-pad" maxLength={16} editable={!task.pending}
        hint="Combined net weight of open containers, or zero." /></>
      : mode === 'packages' ? <><Body muted>Count sealed cases once. Count only boxes outside those cases.</Body>{activePackages.map(item => <PackageCount key={item.id} name={item.name} detail={item.labelAmount && item.labelUnit ? `${item.labelAmount} ${item.labelUnit === 'lb' ? 'lbs' : item.labelUnit} · ${item.amount} ${line.baseUnit}` : `${item.amount} ${line.baseUnit}`} value={packageCounts[item.id] || '0'} disabled={task.pending} onChange={value => update({ packageCounts: { ...packageCounts, [item.id]: value } })} />)}<Field label={line.baseUnit === 'each' ? 'Loose items' : 'Combined loose or partial amount'} value={partial} onChangeText={partial => update({ partial })} keyboardType="decimal-pad" maxLength={25} editable={!task.pending} /></>
      : <Field label="Measured total" value={amount} onChangeText={amount => update({ amount })} keyboardType="decimal-pad" maxLength={25} editable={!task.pending} />}
    <UnitButtons value={unit} base={line.baseUnit} onChange={unit => update({ unit })} disabled={task.pending} />
    <Heading>{total === null ? 'Enter a valid quantity' : `This location: ${quantityLabel(total, line.baseUnit)}`}</Heading>
    <Body muted>{dirty ? 'Unsaved changes.' : 'Saved.'}</Body>
    <Button title="Save count entry" loading={task.pending} disabled={total === null} onPress={() => save(entry)} />
    <Button title="None remaining — save zero" variant="secondary" disabled={task.pending} onPress={() => save({ mode: 'total', amount: '0', unit: line.baseUnit })} />
    <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { resetDraft(); void refresh(); }} />
  </Card> : <Card><Body>This entry is read-only. An approver can return a submitted count to counting.</Body></Card>}
  <Button title={nav.parent(fallback).label} variant="quiet" disabled={task.pending} onPress={leave} />
  </InventoryPage>;
}

function PackageCount({ name, detail, value, disabled, onChange }: { name: string; detail: string; value: string; disabled: boolean; onChange: (value: string) => void }) {
  const parsed = /^\d{1,7}$/.test(value) ? Number(value) : 0;
  return <View style={styles.packageBlock}><View><Text style={styles.packageName}>{name}</Text><Text style={styles.packageDetail}>{detail}</Text></View><View style={styles.packageControls}><Pressable accessibilityRole="button" accessibilityLabel={`Remove one ${name}`} accessibilityState={{ disabled: disabled || parsed <= 0 }} disabled={disabled || parsed <= 0} onPress={() => onChange(String(parsed - 1))} style={styles.step}><Ionicons name="remove" size={20} color={colors.primary} /></Pressable><Field label="Full packages" accessibilityLabel={`${name} count`} value={value} onChangeText={onChange} keyboardType="number-pad" maxLength={7} editable={!disabled} style={styles.countField} /><Pressable accessibilityRole="button" accessibilityLabel={`Add one ${name}`} accessibilityState={{ disabled: disabled || parsed >= 1_000_000 }} disabled={disabled || parsed >= 1_000_000} onPress={() => onChange(String(parsed + 1))} style={styles.step}><Ionicons name="add" size={20} color={colors.primary} /></Pressable></View></View>;
}
function sameEntry(left: Entry, right: Entry, packageIds: string[]) {
  if (left.mode !== right.mode) return false;
  if (left.mode === 'total' && right.mode === 'total') return left.amount === right.amount && left.unit === right.unit;
  if (left.mode === 'containers' && right.mode === 'containers') return left.fullContainers === right.fullContainers && left.partialAmount === right.partialAmount && left.partialUnit === right.partialUnit;
  if (left.mode !== 'packages' || right.mode !== 'packages' || left.partialAmount !== right.partialAmount || left.partialUnit !== right.partialUnit) return false;
  const a = new Map(left.packages.map(item => [item.packageId, item.count])), b = new Map(right.packages.map(item => [item.packageId, item.count]));
  return packageIds.every(id => (a.get(id) || 0) === (b.get(id) || 0)) && [...a.keys(), ...b.keys()].every(id => packageIds.includes(id));
}
const styles = StyleSheet.create({ packageBlock: { gap: 8, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.line }, packageControls: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 }, packageName: { color: colors.ink, fontSize: 15, fontWeight: '700' }, packageDetail: { color: colors.muted, fontSize: 12, marginTop: 3 }, step: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.controlLine, backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center', marginBottom: 1 }, countField: { width: 92, minHeight: 46, paddingHorizontal: 8, textAlign: 'center' } });
