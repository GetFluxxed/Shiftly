import { Text } from '@/src/ui/Typography';
import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Notice, Pill, Screen, layout } from '@/src/ui/components';
import { colors, friendlyDate } from '@/src/ui/theme';
import { useTask } from '@/src/ui/useTask';
import { ApiError } from '@/src/api/client';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';
import { ShiftReports } from '@/src/reports/ShiftReports';
import { ProductionReports } from '@/src/reports/ProductionReports';

const shiftOptions = ['opening', 'midday', 'closing', 'other'] as const;
type Inbox = 'shift' | 'production';

export function ReportsScreen() {
  const { actor, stores } = useSession();
  const canRead = Boolean(actor?.capabilities.includes('reports.view'));
  const canSubmit = Boolean(actor?.capabilities.includes('reports.submit'));
  const canReadProduction = canRead && Boolean(actor?.capabilities.includes('production.view'));
  const [rememberedWriting, setWriting] = useRememberedState('reports.writing', !canRead);
  const writing = canSubmit && rememberedWriting;
  const [inbox, setInbox] = useRememberedState<Inbox>('reports.inbox', 'shift');
  const store = stores.find(item => item.storeId === actor?.storeId);
  if (!canRead && !canSubmit) return <Screen title="Reports"><Notice message="Your account does not have reporting access for this store." /></Screen>;
  return <Screen title={writing ? 'Write a report' : 'Reports'} eyebrow="Reports"
    subtitle={store?.storeName || 'Current store'}>
    {writing ? <Button title="Back to reports" variant="quiet" icon="arrow-back" onPress={() => setWriting(false)} />
      : canSubmit ? <Button title="Write a report" onPress={() => setWriting(true)} icon="create-outline" /> : null}
    {writing ? <ReportComposer /> : canRead ? <>
      <Card><Heading>Report type</Heading>
        <View style={layout.wrap} accessibilityRole="radiogroup" accessibilityLabel="Report type">
          <Button title="Shift reports" variant={inbox === 'shift' ? 'primary' : 'secondary'} icon="reader-outline" onPress={() => setInbox('shift')} />
          {canReadProduction ? <Button title="Production reports" variant={inbox === 'production' ? 'primary' : 'secondary'} icon="restaurant-outline" onPress={() => setInbox('production')} /> : null}
        </View>
      </Card>
      {inbox === 'production' && canReadProduction ? <ProductionReports /> : <ShiftReports />}
    </> : <ReportComposer />}
  </Screen>;
}

function ReportComposer() {
  const { actor, request, busy } = useSession();
  const task = useTask();
  const checkpoint = useWorkspaceCheckpoint();
  const [draft, setDraft, resetDraft] = useRememberedState('reports.composer', {
    shift: 'closing' as (typeof shiftOptions)[number], notes: '', pending: false,
  });
  const { shift, notes } = draft;
  const [receipt, setReceipt] = useState<{ date: string; status: string } | null>(null);
  const uncertain = 'Submission could not be confirmed. Check the inbox or with your manager before sending again.';
  const send = () => { void task.run(async () => {
    setDraft(value => ({ ...value, pending: true }));
    if (!await checkpoint()) {
      setDraft(value => ({ ...value, pending: false }));
      throw new Error('Your draft could not be saved on this device. Please try again before sending.');
    }
    try {
      const result = await request<{ date: string; status: string }>('/reports', {
        uncertainMessage: uncertain, method: 'POST', body: { employee: actor?.displayName || actor?.username || '', shift, notes },
      });
      resetDraft(); return result;
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === 400 || failure.status === 422)) setDraft(value => ({ ...value, pending: false }));
      throw failure;
    }
  }, setReceipt); };
  const discard = () => { resetDraft(); setReceipt(null); task.setError(null); };
  return <Columns><Column><Card>{receipt ? <>
    <EmptyState icon="checkmark-circle-outline" title="Report sent" description="Your briefing will appear in shift reports when ready." />
    <Pill label={receipt.status} /><Body muted>Sent {friendlyDate(receipt.date)}</Body><Button title="Write another report" variant="secondary" onPress={() => setReceipt(null)} />
  </> : <>
    <Heading>Shift report</Heading><Body muted>Reporting as {actor?.displayName || actor?.username}</Body>
    <Text style={styles.label}>Which shift?</Text><View style={layout.wrap} accessibilityRole="radiogroup" accessibilityLabel="Shift">
      {shiftOptions.map(option => <Pressable key={option} accessibilityRole="radio" accessibilityState={{ checked: shift === option }} accessibilityLabel={`${option} shift`}
        disabled={task.pending} onPress={() => setDraft(value => ({ ...value, shift: option }))} style={({ pressed }) => [styles.shift, shift === option && styles.shiftSelected, pressed && { opacity: 0.7 }]}>
        <Text style={[styles.shiftText, shift === option && { color: colors.white }]}>{option}</Text></Pressable>)}
    </View>
    <Field label="Shift notes" value={notes} onChangeText={value => setDraft(current => ({ ...current, notes: value }))} multiline maxLength={2000} editable={!task.pending}
      placeholder="What went well? What needs attention? What's next?" hint={`${notes.length} / 2,000 characters`} />
    {draft.pending ? <Notice message={uncertain} kind="error" /> : null}<Notice message={task.error} kind="error" />
    {draft.pending ? <Button title="I checked reports — keep editing" variant="secondary" disabled={task.pending} onPress={() => { setDraft(value => ({ ...value, pending: false })); task.setError(null); }} /> : null}
    <Button title="Send shift report" icon="arrow-forward" onPress={send} loading={task.pending || busy} disabled={!notes.trim() || draft.pending} />
    <Button title="Discard draft" variant="quiet" disabled={task.pending || (!notes && shift === 'closing' && !draft.pending)} onPress={discard} />
    <Body muted>Saved on this device until sent or discarded.</Body>
  </>}</Card></Column><Column><Card style={{ backgroundColor: colors.soft, borderColor: colors.soft }}>
    <Heading>What to include</Heading>
    <Body>Wins</Body><Body>Open problems</Body><Body>Next steps</Body>
    <Body muted>Sent from your account.</Body>
  </Card></Column></Columns>;
}

const styles = StyleSheet.create({
  label: { fontSize: 14, fontWeight: '600', color: colors.ink },
  shift: { minHeight: 48, paddingHorizontal: 16, paddingVertical: 14, borderWidth: 1, borderColor: colors.line, borderRadius: 24, backgroundColor: colors.card },
  shiftSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  shiftText: { color: colors.ink, fontSize: 14, fontWeight: '600', textTransform: 'capitalize' },
});
