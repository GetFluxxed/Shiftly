import React, { useCallback } from 'react';
import { Alert } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId, type StockUnit } from '../api';
import { InventoryPage, LoadError, useInventoryResource } from '../shared';
import { useCounts, UnitButtons, countBackTo, countRouteParams } from './shared';
import { entryLabel, entryTotal, quantityLabel } from './measurements';
import type { Count, CountLine, Entry } from './api';

export function CountEntryScreen() {
  const { countId, lineId, returnTo } = useLocalSearchParams<{ countId: string; lineId: string; returnTo?: string }>();
  return <InventoryPage title="Count this location." backTo={countBackTo(returnTo)}>{validId(countId) && validId(lineId) ? <EntryLoader countId={countId} lineId={lineId} returnTo={returnTo} /> : <Notice message="This entry is unavailable." kind="error" />}</InventoryPage>;
}
function EntryLoader({ countId, lineId, returnTo }: { countId: string; lineId: string; returnTo?: string }) {
  const { api, actor } = useCounts();
  const resource = useInventoryResource(useCallback(async () => {
    const [count, line] = await Promise.all([api.detail(countId), api.line(countId, lineId)]); return { count, line };
  }, [api, countId, lineId]));
  if (resource.loading) return <Loading label="Loading saved entry…" />;
  if (resource.error || !resource.data || resource.data.count.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Entry unavailable.'} refresh={resource.refresh} />;
  return <EntryForm key={`${resource.data.line.id}:${resource.data.line.version}:${resource.data.count.state}`} {...resource.data} returnTo={returnTo} refresh={resource.refresh} />;
}
function EntryForm({ count, line, returnTo, refresh }: { count: Count; line: CountLine; returnTo?: string; refresh: () => Promise<void> }) {
  const { api, identity, canCount } = useCounts(); const router = useRouter(); const task = useTask();
  const initial = line.entry;
  const initialDraft = () => ({ mode: initial?.mode || (line.containerAmount ? 'containers' : 'total') as 'total' | 'containers', amount: initial?.mode === 'total' ? initial.amount : '',
    full: initial?.mode === 'containers' ? String(initial.fullContainers) : '', partial: initial?.mode === 'containers' ? initial.partialAmount : '0',
    unit: (initial?.mode === 'total' ? initial.unit : initial?.partialUnit || line.baseUnit) as StockUnit });
  const baseline = `${line.version}:${count.state}:${!!count.configurationChanged}:${line.containerAmount ?? 'none'}:${line.baseUnit}`;
  const [draft, setDraft, resetDraft] = useRememberedState(`inventory.count.${count.id}.line.${line.id}`, initialDraft, baseline);
  const { mode, amount, full, partial, unit } = draft;
  const update = (fields: Partial<typeof draft>) => setDraft(value => ({ ...value, ...fields }));
  const entry: Entry = mode === 'total' ? { mode, amount, unit } : { mode, fullContainers: /^\d{1,7}$/.test(full) ? Number(full) : NaN, partialAmount: partial, partialUnit: unit };
  const total = entryTotal(entry, line), editable = count.state === 'draft' && canCount && !count.configurationChanged;
  const dirty = initial === null ? amount !== '' || full !== '' || partial !== '0'
    : entry.mode !== initial.mode || (entry.mode === 'total' && initial.mode === 'total'
      ? entry.amount !== initial.amount || entry.unit !== initial.unit
      : entry.mode === 'containers' && initial.mode === 'containers'
        ? entry.fullContainers !== initial.fullContainers || entry.partialAmount !== initial.partialAmount || entry.partialUnit !== initial.partialUnit : true);
  const back = () => router.replace({ pathname: '/counts/[countId]', params: { countId: count.id, ...countRouteParams(returnTo) } });
  const save = (value: Entry) => { void task.run(() => api.save(count.id, line, value, identity), () => { resetDraft(); back(); }); };
  return <><Card><Heading>{line.name}</Heading><Body muted>{line.shelfName}</Body>
    <Body>Saved quantity: {quantityLabel(line.quantity, line.baseUnit)}</Body><Body muted>{entryLabel(initial, line)}</Body>
    {line.containerAmount ? <Body>Full-container reference: {quantityLabel(line.containerAmount, line.baseUnit)}</Body> : null}
    {count.configurationChanged ? <Notice message="The store setup changed. Ask an approver to cancel this count and start a fresh one." kind="error" /> : null}
  </Card>
  {editable ? <Card><Heading>What is here now?</Heading><Body>Include only stock at {line.shelfName}. Enter net product weight, excluding packaging.</Body>
    <Notice message={task.error} kind="error" />
    {line.containerAmount ? <><Button title="Full containers + partial" variant={mode === 'containers' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => update({ mode: 'containers' })} />
      <Button title="Enter a measured total" variant={mode === 'total' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => update({ mode: 'total' })} /></> : null}
    {mode === 'containers' ? <><Field label="Full containers" value={full} onChangeText={full => update({ full })} keyboardType="number-pad" maxLength={7} editable={!task.pending} />
      <Field label="Combined net partial amount" value={partial} onChangeText={partial => update({ partial })} keyboardType="decimal-pad" maxLength={16} editable={!task.pending}
        hint="Add together any open containers at this location. Use zero when there are no partials." /></>
      : <Field label="Measured total" value={amount} onChangeText={amount => update({ amount })} keyboardType="decimal-pad" maxLength={16} editable={!task.pending} />}
    <UnitButtons value={unit} base={line.baseUnit} onChange={unit => update({ unit })} disabled={task.pending} />
    <Heading>{total === null ? 'Enter a valid quantity' : `This location: ${quantityLabel(total, line.baseUnit)}`}</Heading>
    <Body muted>{dirty ? 'Draft kept on this device. Save to update this count entry.' : 'This entry matches the saved count.'}</Body>
    <Button title="Save count entry" loading={task.pending} disabled={total === null} onPress={() => save(entry)} />
    <Button title="None remaining — save zero" variant="secondary" disabled={task.pending} onPress={() => save({ mode: 'total', amount: '0', unit: line.baseUnit })} />
    <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { resetDraft(); void refresh(); }} />
  </Card> : <Card><Body>This entry is read-only. An approver can return a submitted count to counting.</Body></Card>}
  <Button title="Back to count entries" variant="quiet" disabled={task.pending} onPress={() => { if (editable && dirty) Alert.alert('Leave unsaved entry?', 'Your draft is kept on this device unless you discard it.', [{ text: 'Keep editing', style: 'cancel' }, { text: 'Keep draft and go back', onPress: back }, { text: 'Discard and go back', style: 'destructive', onPress: () => { resetDraft(); back(); } }]); else back(); }} />
  </>;
}
