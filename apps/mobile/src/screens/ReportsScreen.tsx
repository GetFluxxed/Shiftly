import { Text } from '@/src/ui/Typography';
import React, { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill, Screen, layout, useScrollToTop } from '@/src/ui/components';
import { colors, friendlyDate } from '@/src/ui/theme';
import { useResource } from '@/src/ui/useResource';
import { useTask } from '@/src/ui/useTask';
import { ApiError } from '@/src/api/client';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';

type Report = {
  id: string; employee: string; shift: string; notes: string; date: string;
  status: string; error?: string | null; storeId: number; storeName: string;
  briefing?: { summary: string; wins: string[]; risks: string[]; follow_up: string } | null;
};
const shiftOptions = ['opening', 'midday', 'closing', 'other'] as const;

export function ReportsScreen() {
  const { actor, stores } = useSession();
  const canRead = Boolean(actor?.capabilities.includes('reports.view'));
  const canSubmit = Boolean(actor?.capabilities.includes('reports.submit'));
  const [writing, setWriting] = useRememberedState('reports.writing', !canRead);
  const store = stores.find((item) => item.storeId === actor?.storeId);
  if (!canRead && !canSubmit) return <Screen title="Shift reports"><Notice message="Your account does not have reporting access for this store." /></Screen>;
  return <Screen title={writing ? 'Leave a good handoff.' : 'Every shift, in the loop.'} eyebrow="Shift reports"
    subtitle={writing ? `${store?.storeName || 'Current store'} · Share the details that matter to your team.` : `${store?.storeName || 'Current store'} · Your team’s reports.`}>
    {canRead && canSubmit ? <View style={layout.wrap}>
      <Button title="Report inbox" variant={!writing ? 'primary' : 'secondary'} onPress={() => setWriting(false)} icon="reader-outline" />
      <Button title="Write a report" variant={writing ? 'primary' : 'secondary'} onPress={() => setWriting(true)} icon="create-outline" />
    </View> : null}
    {writing ? <ReportComposer /> : <ReportInbox />}
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
        uncertainMessage: uncertain, method: 'POST',
        body: { employee: actor?.displayName || actor?.username || '', shift, notes },
      });
      resetDraft();
      return result;
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === 400 || failure.status === 422)) {
        setDraft(value => ({ ...value, pending: false }));
      }
      throw failure;
    }
  }, setReceipt); };
  const discard = () => { resetDraft(); setReceipt(null); task.setError(null); };
  return <Columns><Column><Card>
    {receipt ? <>
      <EmptyState icon="checkmark-circle-outline" title="Your handoff is in." description="Your report was saved. The briefing will appear in your team's report inbox when processing is complete." />
      <Pill label={receipt.status} /><Body muted>Sent {friendlyDate(receipt.date)}</Body>
      <Button title="Write another report" variant="secondary" onPress={() => setReceipt(null)} />
    </> : <>
      <Heading>Your shift, in your words.</Heading>
      <Body muted>Reporting as {actor?.displayName || actor?.username}</Body>
      <Text style={styles.label}>Which shift?</Text>
      <View style={layout.wrap} accessibilityRole="radiogroup" accessibilityLabel="Shift">
        {shiftOptions.map((option) => <Pressable key={option} accessibilityRole="radio"
          accessibilityState={{ checked: shift === option }} accessibilityLabel={`${option} shift`}
          disabled={task.pending} onPress={() => setDraft(value => ({ ...value, shift: option }))} style={({ pressed }) => [styles.shift,
            shift === option && styles.shiftSelected, pressed && { opacity: 0.7 }]}>
          <Text style={[styles.shiftText, shift === option && { color: colors.white }]}>{option}</Text>
        </Pressable>)}
      </View>
      <Field label="Shift notes" value={notes} onChangeText={value => setDraft(current => ({ ...current, notes: value }))} multiline maxLength={2000} editable={!task.pending}
        placeholder="What went well? What needs attention? What's next?" hint={`${notes.length} / 2,000 characters`} />
      {draft.pending ? <Notice message={uncertain} kind="error" /> : null}
      <Notice message={task.error} kind="error" />
      {draft.pending ? <Button title="I checked — keep editing" variant="secondary" disabled={task.pending} onPress={() => {
        setDraft(value => ({ ...value, pending: false })); task.setError(null);
      }} /> : null}
      <Button title="Send shift report" icon="arrow-forward" onPress={send} loading={task.pending || busy}
        disabled={!notes.trim() || draft.pending} />
      <Button title="Discard draft" variant="quiet" disabled={task.pending || (!notes && shift === 'closing' && !draft.pending)} onPress={discard} />
      <Body muted>This draft is saved securely on this device until you send or discard it.</Body>
    </>}
  </Card></Column><Column><Card style={{ backgroundColor: colors.soft, borderColor: colors.soft }}>
    <Heading>A useful note goes a long way.</Heading>
    <Body>Start with what happened. Add enough detail for someone who wasn't there.</Body>
    <View style={layout.divider} /><Body>Wins worth sharing</Body><Body>Problems and anything still open</Body><Body>What the next shift needs to do</Body>
    <Body muted>Your report is attributed to your individual account.</Body>
  </Card></Column></Columns>;
}

function ReportInbox() {
  const resource = useResource<{ reports: Report[] }>('/reports');
  const { width, fontScale } = useWindowDimensions();
  const wide = width >= 900 && fontScale < 1.5;
  const [selected, setSelected] = useRememberedState<string | null>('reports.selected', null);
  const scrollToTop = useScrollToTop();
  const previousSelection = useRef(selected);
  useEffect(() => {
    if (!wide && previousSelection.current !== selected) scrollToTop();
    previousSelection.current = selected;
  }, [selected, wide, scrollToTop]);
  const [limit, setLimit] = useRememberedState('reports.limit', 30);
  const reports = resource.data?.reports || [];
  const report = reports.find((item) => item.id === selected);
  return <View style={layout.gap}>
    <Button title="Refresh reports" variant="secondary" icon="refresh-outline" loading={resource.loading} onPress={() => { void resource.refresh(); }} />
    {resource.loading ? <Card><Loading label="Getting your team's reports…" /></Card> : resource.error ? <Notice message={resource.error} kind="error" />
      : reports.length === 0 ? <Card><EmptyState icon="reader-outline" title="Room for your next handoff" description="There are no reports to show yet. Your team's shift reports will appear here." /></Card>
      : !wide && report ? <Card>
        <Button title="Back to inbox" variant="secondary" icon="arrow-back" onPress={() => setSelected(null)} />
        <ReportDetail report={report} />
      </Card> : <Columns><Column><Card>
        <View style={layout.row}><Heading>Report inbox</Heading><Pill label={`${reports.length}`} /></View>
        <Body muted>Store names appear on every report so you can keep each team's context clear.</Body>
        {reports.slice(0, limit).map((item) => <Pressable key={item.id}
          accessibilityRole="button" accessibilityState={{ selected: selected === item.id }}
          accessibilityLabel={`${item.employee}, ${item.shift} shift, ${item.storeName}, ${friendlyDate(item.date)}, ${item.status}`}
          onPress={() => setSelected(item.id)} style={({ pressed }) => [styles.reportRow,
            selected === item.id && styles.reportSelected, pressed && { opacity: 0.65 }]}>
          <View style={layout.flex}><Text style={styles.reportStore}>{item.storeName}</Text>
            <Text style={styles.reportName}>{item.employee}</Text>
            <Text style={styles.reportMeta}>{item.shift} · {friendlyDate(item.date)}</Text>
            <Text style={styles.reportStatus}>{item.status}</Text></View>
          <Ionicons name="chevron-forward" size={20} color={colors.primary} />
        </Pressable>)}
        {reports.length > limit ? <Button title="Show more reports" variant="secondary" onPress={() => setLimit(limit + 30)} /> : null}
      </Card></Column>{wide ? <Column><Card>
        {report ? <ReportDetail report={report} /> : <EmptyState icon="albums-outline" title="The whole story is here" description="Choose a report to read the original shift notes and its briefing." />}
      </Card></Column> : null}</Columns>}
  </View>;
}

function ReportDetail({ report }: { report: Report }) {
  return <View style={layout.gap}>
    <Pill label={report.storeName} /><Heading>{report.employee}'s handoff</Heading>
    <Body muted>{report.shift} shift · {friendlyDate(report.date)}</Body>
    <Heading>Original notes</Heading><Body>{report.notes}</Body><View style={layout.divider} />
    <Pill label={report.status} />
    {report.status === 'pending' || report.status === 'processing' ? <Notice message="The briefing is being prepared. Refresh the inbox to check its progress." />
      : report.status === 'failed' ? <Notice kind="error" message="The report was saved, but its briefing could not be prepared. Your original notes are still available." />
      : report.briefing ? <>
        <Heading>Shift briefing</Heading><Body>{report.briefing.summary}</Body>
        {report.briefing.wins?.length > 0 ? <><Heading>What went well</Heading>
          {report.briefing.wins.map((win, index) => <Body key={index}>• {win}</Body>)}</> : null}
        {report.briefing.risks?.length > 0 ? <><Heading>Needs attention</Heading>
          {report.briefing.risks.map((risk, index) => <Body key={index}>• {risk}</Body>)}</> : null}
        {report.briefing.follow_up ? <Card style={{ backgroundColor: colors.soft }}><Heading>Next steps</Heading><Body>{report.briefing.follow_up}</Body></Card> : null}
        <Body muted>Briefings are generated from shift notes. Check the original report for context.</Body>
      </> : <Body muted>No briefing is available for this report yet.</Body>}
  </View>;
}

const styles = StyleSheet.create({
  label: { fontSize: 14, fontWeight: '600', color: colors.ink },
  shift: { minHeight: 48, paddingHorizontal: 16, paddingVertical: 14, borderWidth: 1, borderColor: colors.line, borderRadius: 24, backgroundColor: colors.card },
  shiftSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  shiftText: { color: colors.ink, fontSize: 14, fontWeight: '600', textTransform: 'capitalize' },
  reportRow: { borderWidth: 1, borderColor: colors.line, borderRadius: 16, padding: 17, minHeight: 110, flexDirection: 'row', alignItems: 'center', gap: 12 },
  reportSelected: { backgroundColor: colors.blush, borderColor: colors.primary },
  reportStore: { color: colors.primary, fontSize: 12, fontWeight: '700', marginBottom: 7 },
  reportName: { fontSize: 18, fontWeight: '600', color: colors.ink, marginBottom: 5 },
  reportMeta: { fontSize: 13, lineHeight: 20, color: colors.muted },
  reportStatus: { marginTop: 8, fontSize: 12, fontWeight: '700', color: colors.primary, textTransform: 'capitalize' },
});
