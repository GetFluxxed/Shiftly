import React, { useCallback, useState } from 'react';
import { Alert } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { validId, type StockUnit } from '../api';
import { InventoryPage, LoadError, useInventoryResource } from '../shared';
import { useCounts, UnitButtons } from './shared';
import { entryLabel, entryTotal, quantityLabel } from './measurements';
import type { Count, CountLine, Entry } from './api';

export function CountEntryScreen() {
  const { countId, lineId } = useLocalSearchParams<{ countId: string; lineId: string }>();
  return <InventoryPage title="Count this location.">{validId(countId) && validId(lineId) ? <EntryLoader countId={countId} lineId={lineId} /> : <Notice message="This entry is unavailable." kind="error" />}</InventoryPage>;
}
function EntryLoader({ countId, lineId }: { countId: string; lineId: string }) {
  const { api, actor } = useCounts();
  const resource = useInventoryResource(useCallback(async () => {
    const [count, line] = await Promise.all([api.detail(countId), api.line(countId, lineId)]); return { count, line };
  }, [api, countId, lineId]));
  if (resource.loading) return <Loading label="Loading saved entry…" />;
  if (resource.error || !resource.data || resource.data.count.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Entry unavailable.'} refresh={resource.refresh} />;
  return <EntryForm key={`${resource.data.line.id}:${resource.data.line.version}:${resource.data.count.state}`} {...resource.data} refresh={resource.refresh} />;
}
function EntryForm({ count, line, refresh }: { count: Count; line: CountLine; refresh: () => Promise<void> }) {
  const { api, identity, canCount } = useCounts(); const router = useRouter(); const task = useTask();
  const initial = line.entry;
  const [mode, setMode] = useState<'total' | 'containers'>(initial?.mode || (line.containerAmount ? 'containers' : 'total'));
  const [amount, setAmount] = useState(initial?.mode === 'total' ? initial.amount : '');
  const [full, setFull] = useState(initial?.mode === 'containers' ? String(initial.fullContainers) : '');
  const [partial, setPartial] = useState(initial?.mode === 'containers' ? initial.partialAmount : '0');
  const [unit, setUnit] = useState<StockUnit>(initial?.mode === 'total' ? initial.unit : initial?.partialUnit || line.baseUnit);
  const entry: Entry = mode === 'total' ? { mode, amount, unit } : { mode, fullContainers: /^\d{1,7}$/.test(full) ? Number(full) : NaN, partialAmount: partial, partialUnit: unit };
  const total = entryTotal(entry, line), editable = count.state === 'draft' && canCount && !count.configurationChanged;
  const dirty = initial === null ? amount !== '' || full !== '' || partial !== '0'
    : entry.mode !== initial.mode || (entry.mode === 'total' && initial.mode === 'total'
      ? entry.amount !== initial.amount || entry.unit !== initial.unit
      : entry.mode === 'containers' && initial.mode === 'containers'
        ? entry.fullContainers !== initial.fullContainers || entry.partialAmount !== initial.partialAmount || entry.partialUnit !== initial.partialUnit : true);
  const back = () => router.replace({ pathname: '/counts/[countId]', params: { countId: count.id } });
  const save = (value: Entry) => { void task.run(() => api.save(count.id, line, value, identity), back); };
  return <><Card><Heading>{line.name}</Heading><Body muted>SKU {line.sku} · {line.shelfName}</Body>
    <Body>Saved quantity: {quantityLabel(line.quantity, line.baseUnit)}</Body><Body muted>{entryLabel(initial, line)}</Body>
    {line.containerAmount ? <Body>Full-container reference: {quantityLabel(line.containerAmount, line.baseUnit)}</Body> : null}
    {count.configurationChanged ? <Notice message="The store setup changed. Ask an approver to cancel this count and start a fresh one." kind="error" /> : null}
  </Card>
  {editable ? <Card><Heading>What is here now?</Heading><Body>Include only stock at {line.shelfName}. Enter net product weight, excluding packaging.</Body>
    <Notice message={task.error} kind="error" />
    {line.containerAmount ? <><Button title="Full containers + partial" variant={mode === 'containers' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => setMode('containers')} />
      <Button title="Enter a measured total" variant={mode === 'total' ? 'primary' : 'secondary'} disabled={task.pending} onPress={() => setMode('total')} /></> : null}
    {mode === 'containers' ? <><Field label="Full containers" value={full} onChangeText={setFull} keyboardType="number-pad" maxLength={7} editable={!task.pending} />
      <Field label="Combined net partial amount" value={partial} onChangeText={setPartial} keyboardType="decimal-pad" maxLength={16} editable={!task.pending}
        hint="Add together any open containers at this location. Use zero when there are no partials." /></>
      : <Field label="Measured total" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" maxLength={16} editable={!task.pending} />}
    <UnitButtons value={unit} base={line.baseUnit} onChange={setUnit} disabled={task.pending} />
    <Heading>{total === null ? 'Enter a valid quantity' : `This location: ${quantityLabel(total, line.baseUnit)}`}</Heading>
    <Body muted>{dirty ? 'This entry has unsaved changes. Save before leaving; only confirmed saves can be resumed.' : 'This entry matches the saved count.'}</Body>
    <Button title="Save count entry" loading={task.pending} disabled={total === null} onPress={() => save(entry)} />
    <Button title="None remaining — save zero" variant="secondary" disabled={task.pending} onPress={() => save({ mode: 'total', amount: '0', unit: line.baseUnit })} />
    <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { void refresh(); }} />
  </Card> : <Card><Body>This entry is read-only. An approver can return a submitted count to counting.</Body></Card>}
  <Button title="Back to count entries" variant="quiet" disabled={task.pending} onPress={() => { if (editable && dirty) Alert.alert('Leave unsaved entry?', 'Only saved quantities can be resumed.', [{ text: 'Keep counting', style: 'cancel' }, { text: 'Discard and go back', onPress: back }]); else back(); }} />
  </>;
}
