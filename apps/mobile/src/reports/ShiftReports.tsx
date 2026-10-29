import React, { useEffect, useRef } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Text } from '../ui/Typography';
import { Body, Button, Card, Column, Columns, EmptyState, Heading, Loading, Notice, Pill, layout, useScrollToTop } from '../ui/components';
import { colors, friendlyDate } from '../ui/theme';
import { useResource } from '../ui/useResource';
import { useRememberedState } from '../restoration/WorkspaceProvider';

export type ShiftReport = {
  id: string; employee: string; shift: string; notes: string; date: string;
  status: string; error?: string | null; storeId: number; storeName: string;
  briefing?: { summary: string; wins: string[]; risks: string[]; follow_up: string } | null;
};

export function ShiftReports() {
  const resource = useResource<{ reports: ShiftReport[] }>('/reports');
  const { width, fontScale } = useWindowDimensions();
  const wide = width >= 900 && fontScale < 1.5;
  const [selected, setSelected] = useRememberedState<string | null>('reports.shift.selected', null);
  const scrollToTop = useScrollToTop();
  const previousSelection = useRef(selected);
  useEffect(() => {
    if (!wide && previousSelection.current !== selected) scrollToTop();
    previousSelection.current = selected;
  }, [selected, wide, scrollToTop]);
  const [limit, setLimit] = useRememberedState('reports.shift.limit', 30);
  const reports = resource.data?.reports || [];
  const report = reports.find(item => item.id === selected);
  useEffect(() => { if (!resource.loading && selected && !report) setSelected(null); }, [resource.loading, selected, report, setSelected]);
  return <View style={layout.gap}>
    <Button title="Refresh shift reports" variant="secondary" icon="refresh-outline" loading={resource.loading} onPress={() => { void resource.refresh(); }} />
    {resource.loading ? <Card><Loading label="Getting your team's shift reports…" /></Card> : resource.error ? <Notice message={resource.error} kind="error" />
      : reports.length === 0 ? <Card><EmptyState icon="reader-outline" title="No shift reports" description="New handoffs appear here." /></Card>
      : !wide && report ? <Card>
        <Button title="Back to shift reports" variant="secondary" icon="arrow-back" onPress={() => setSelected(null)} />
        <ShiftReportDetail report={report} />
      </Card> : <Columns><Column><Card>
        <View style={layout.row}><Heading>Shift reports</Heading><Pill label={`${reports.length}`} /></View>
        {reports.slice(0, limit).map(item => <Pressable key={item.id}
          accessibilityRole="button" accessibilityState={{ selected: selected === item.id }}
          accessibilityLabel={`${item.employee}, ${item.shift} shift, ${item.storeName}, ${friendlyDate(item.date)}, ${item.status}`}
          onPress={() => setSelected(item.id)} style={({ pressed }) => [styles.row,
            selected === item.id && styles.selected, pressed && { opacity: 0.65 }]}>
          <View style={layout.flex}><Text style={styles.store}>{item.storeName}</Text>
            <Text style={styles.name}>{item.employee}</Text>
            <Text style={styles.meta}>{item.shift} · {friendlyDate(item.date)}</Text>
            <Text style={styles.status}>{item.status}</Text></View>
          <Ionicons name="chevron-forward" size={20} color={colors.primary} />
        </Pressable>)}
        {reports.length > limit ? <Button title="Show more shift reports" variant="secondary" onPress={() => setLimit(limit + 30)} /> : null}
      </Card></Column>{wide ? <Column><Card>
        {report ? <ShiftReportDetail report={report} /> : <EmptyState icon="albums-outline" title="Choose a shift report" description="Select one to read it." />}
      </Card></Column> : null}</Columns>}
  </View>;
}

function ShiftReportDetail({ report }: { report: ShiftReport }) {
  return <View style={layout.gap}>
    <Pill label={report.storeName} /><Heading>{report.employee}'s handoff</Heading>
    <Body muted>{report.shift} shift · {friendlyDate(report.date)}</Body>
    <Heading>Original notes</Heading><Body>{report.notes}</Body><View style={layout.divider} />
    <Pill label={report.status} />
    {report.status === 'pending' || report.status === 'processing' ? <Notice message="Preparing briefing. Refresh to check again." />
      : report.status === 'failed' ? <Notice kind="error" message="Briefing failed. The original report is still available." />
      : report.briefing ? <>
        <Heading>Shift briefing</Heading><Body>{report.briefing.summary}</Body>
        {report.briefing.wins?.length ? <><Heading>What went well</Heading>{report.briefing.wins.map((win, index) => <Body key={index}>• {win}</Body>)}</> : null}
        {report.briefing.risks?.length ? <><Heading>Needs attention</Heading>{report.briefing.risks.map((risk, index) => <Body key={index}>• {risk}</Body>)}</> : null}
        {report.briefing.follow_up ? <Card style={{ backgroundColor: colors.soft }}><Heading>Next steps</Heading><Body>{report.briefing.follow_up}</Body></Card> : null}
        <Body muted>Check the original report for context.</Body>
      </> : <Body muted>No briefing is available for this report yet.</Body>}
  </View>;
}

const styles = StyleSheet.create({
  row: { borderWidth: 1, borderColor: colors.line, borderRadius: 16, padding: 17, minHeight: 108, flexDirection: 'row', alignItems: 'center', gap: 12 },
  selected: { backgroundColor: colors.blush, borderColor: colors.primary },
  store: { color: colors.primary, fontSize: 12, fontWeight: '700', marginBottom: 7 },
  name: { fontSize: 18, fontWeight: '600', color: colors.ink, marginBottom: 5 },
  meta: { fontSize: 13, lineHeight: 20, color: colors.muted },
  status: { marginTop: 8, fontSize: 12, fontWeight: '700', color: colors.primary, textTransform: 'capitalize' },
});
