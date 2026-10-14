import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '../session/SessionProvider';
import { useRememberedState } from '../restoration/WorkspaceProvider';
import { newUuid, productionApi, type ProductionLog } from '../production/api';
import { createResponseGuard, forecastApi, type ForecastEnvelope } from './forecastApi';
import { Body, Button, Card, Column, Columns, EmptyState, Heading, Loading, Notice, Pill, layout, useScrollToTop } from '../ui/components';
import { Text } from '../ui/Typography';
import { colors, friendlyDate } from '../ui/theme';
import { LoadError, Pages, useInventoryResource } from '../inventory/shared';

export function ProductionReports() {
  const { actor, request } = useSession();
  const api = useMemo(() => productionApi(request), [request]);
  const [cursor, setCursor] = useRememberedState('reports.production.cursor', '');
  const [selected, setSelected] = useRememberedState<string | null>('reports.production.selected', null);
  const resource = useInventoryResource(useCallback(() => api.logs(cursor), [api, cursor]));
  const { width, fontScale } = useWindowDimensions();
  const wide = width >= 900 && fontScale < 1.5;
  const scrollToTop = useScrollToTop();
  const previous = useRef(selected);
  useEffect(() => { if (!wide && previous.current !== selected) scrollToTop(); previous.current = selected; }, [selected, wide, scrollToTop]);
  const selectedSummary = resource.data?.items.find(item => item.id === selected);
  useEffect(() => { if (!resource.loading && selected && !selectedSummary && !cursor) setSelected(null); }, [resource.loading, selected, selectedSummary, cursor, setSelected]);
  if (!actor?.capabilities.includes('production.view')) return <Notice message="Your account cannot view production reports for this store." kind="error" />;
  return <View style={layout.gap}>
    <ForecastPanel logId={selected || undefined} />
    <Button title="Refresh production reports" variant="secondary" icon="refresh-outline" loading={resource.loading} onPress={() => { void resource.refresh(); }} />
    {resource.loading ? <Card><Loading label="Opening production reports…" /></Card>
      : resource.error || !resource.data ? <LoadError {...resource} />
      : !resource.data.items.length ? <Card><EmptyState icon="time-outline" title="No production reports" description="Confirmed production appears here." /></Card>
      : !wide && selected ? <Card><Button title="Back to production reports" variant="secondary" icon="arrow-back" onPress={() => setSelected(null)} /><ProductionReportDetail id={selected} /></Card>
      : <Columns><Column><Card><View style={layout.row}><Heading>Production reports</Heading><Pill label={`${resource.data.items.length}`} /></View>
        {resource.data.items.map(item => <ProductionRow key={item.id} item={item} selected={selected === item.id} onPress={() => setSelected(item.id)} />)}
        <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={value => { setCursor(value); setSelected(null); }} />
      </Card></Column>{wide ? <Column><Card>{selected ? <ProductionReportDetail id={selected} />
        : <EmptyState icon="restaurant-outline" title="Choose a production report" description="Select one to view details." />}</Card></Column> : null}</Columns>}
  </View>;
}

function ProductionRow({ item, selected, onPress }: { item: ProductionLog; selected: boolean; onPress: () => void }) {
  const totalBatches = item.entries.reduce((sum, entry) => sum + entry.batches, 0);
  return <Pressable accessibilityRole="button" accessibilityState={{ selected }}
    accessibilityLabel={`${item.businessDate}, ${item.entries.length} flavors, ${totalBatches} batches, recorded by ${item.createdBy}, ${item.state}`}
    onPress={onPress} style={({ pressed }) => [styles.row, selected && styles.selected, pressed && { opacity: 0.65 }]}>
    <View style={layout.flex}><Text style={styles.date}>{item.businessDate}</Text>
      <Text style={styles.name}>{item.entries.length} flavor{item.entries.length === 1 ? '' : 's'} · {totalBatches} batch{totalBatches === 1 ? '' : 'es'}</Text>
      <Text style={styles.meta}>Recorded by {item.createdBy} · {friendlyDate(item.createdAt)}</Text>
      <Text style={styles.status}>{item.state}</Text></View>
    <Ionicons name="chevron-forward" size={20} color={colors.primary} />
  </Pressable>;
}

function ProductionReportDetail({ id }: { id: string }) {
  const { request } = useSession();
  const api = useMemo(() => productionApi(request), [request]);
  const resource = useInventoryResource(useCallback(() => api.log(id), [api, id]));
  if (resource.loading) return <Loading label="Opening production report…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const item = resource.data;
  return <View style={layout.gap}>
    <Pill label={item.state} /><Heading>{item.businessDate}</Heading>
    <Body muted>Recorded by {item.createdBy} · {friendlyDate(item.createdAt)}</Body>
    {item.reversalReason ? <Notice message={`Reversal reason: ${item.reversalReason}`} kind="error" /> : null}
    <Heading>Flavors and batches</Heading>
    {item.entries.map((entry, index) => <View key={`${entry.recipeId}:${entry.revisionId}:${index}`} style={styles.detailRow}>
      <View style={layout.flex}><Text style={styles.detailName}>{entry.name}</Text><Body muted>Recipe yield {entry.yieldAmount} {entry.yieldUnit}</Body></View>
      <Pill label={`${entry.batches} batch${entry.batches === 1 ? '' : 'es'}`} />
    </View>)}
    <Heading>Ingredient deductions</Heading>
    {item.ingredients.map(ingredient => <View key={ingredient.productId} style={styles.detailRow}>
      <View style={layout.flex}><Text style={styles.detailName}>{ingredient.name}</Text>
        <Body muted>Recipe {ingredient.recipeAmount} + 1% allowance {ingredient.allowanceAmount} {ingredient.baseUnit}</Body></View>
      <Text style={styles.quantity}>{ingredient.quantity} {ingredient.baseUnit}</Text>
    </View>)}
  </View>;
}

function ForecastPanel({ logId }: { logId?: string }) {
  const { actor, request, stores } = useSession();
  const allowed = ['forecasts.view', 'reports.view', 'production.view', 'inventory.view']
    .every(capability => actor?.capabilities.includes(capability));
  const api = useMemo(() => forecastApi(request), [request]);
  const [data, setData] = useState<ForecastEnvelope | null>(null);
  const [loading, setLoading] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showAllFacts, setShowAllFacts] = useState(false);
  const polls = useRef(0);
  const responses = useRef(createResponseGuard());
  const attempt = useRef<{ scope: string; id: string } | null>(null);
  const scope = `${actor?.storeId || 0}:${logId || 'store'}`;
  const load = useCallback(async (poll = false) => {
    if (!allowed) return;
    const current = responses.current.begin();
    if (!poll) setLoading(true); setError(null);
    try { const next = await api.get(logId); if (responses.current.current(current)) setData(next); }
    catch (failure) { if (responses.current.current(current)) setError(failure instanceof Error ? failure.message : 'The production forecast could not be loaded.'); }
    finally { if (!poll && responses.current.current(current)) setLoading(false); }
  }, [allowed, api, logId]);
  useEffect(() => {
    polls.current = 0; responses.current.invalidate(); setData(null); setError(null); setRequesting(false); setShowAllFacts(false); void load();
    return () => { responses.current.invalidate(); };
  }, [load]);
  useEffect(() => {
    if (!data || !['queued', 'processing'].includes(data.status) || polls.current >= 3) return;
    const timer = setTimeout(() => { polls.current += 1; void load(true); }, 2500);
    return () => clearTimeout(timer);
  }, [data, load]);
  if (!allowed || !actor) return null;
  const store = stores.find(item => item.storeId === actor.storeId);
  const requestForecast = async () => {
    const current = responses.current.begin();
    const requestId = attempt.current?.scope === scope ? attempt.current.id : newUuid();
    attempt.current = { scope, id: requestId };
    setRequesting(true); setError(null);
    try {
      const next = await api.request(actor.storeId, logId, requestId);
      if (responses.current.current(current)) { polls.current = 0; setData(next); attempt.current = null; }
    } catch (failure) {
      if (responses.current.current(current)) setError(failure instanceof Error ? failure.message : 'The forecast request is uncertain. Retrying will not create a duplicate.');
    } finally { if (responses.current.current(current)) setRequesting(false); }
  };
  const item = data?.forecast;
  const sparse = Boolean(item && item.coverage.productionDays < 7);
  return <Card style={styles.forecast}>
    <View style={layout.row}><View style={layout.flex}><Heading>Production forecast</Heading><Body muted>{store?.storeName || 'Current store'}{logId ? ' · selected production report' : ''}</Body></View>
      {item?.stale ? <Pill label="Stale" /> : data ? <Pill label={data.status.replace('_', ' ')} /> : null}</View>
    <Body>Planning only. Forecasts never change recipes, production, or inventory.</Body>
    <Button title={expanded ? 'Hide forecast' : 'Show forecast'} variant="secondary" icon={expanded ? 'chevron-up' : 'chevron-down'} onPress={() => setExpanded(value => !value)} />
    {expanded ? <>
    <Notice message={error} kind="error" />
    {loading ? <Loading label="Checking forecast status…" /> : data?.status === 'unavailable' ? <Notice message={data.error || 'Production forecasts are unavailable.'} />
      : data?.status === 'failed' ? <Notice message={data.error || 'The forecast could not be prepared.'} kind="error" />
      : data?.status === 'queued' || data?.status === 'processing' ? <Notice message="Preparing forecast. Refresh to check again." />
      : data?.status === 'not_requested' ? <Body muted>No forecast yet.</Body> : null}
    {item ? <>
      <View style={layout.wrap}><Pill label={`As of ${item.asOf}`} /><Pill label={`${item.coverage.productionDays}/${item.coverage.windowDays} production days`} /><Pill label={`${item.coverage.productionReports} production reports`} /><Pill label={`${item.coverage.shiftReports} shift reports`} />{item.coverage.truncated ? <Pill label="Partial history" /> : null}</View>
      {item.generatedAt ? <Body muted>Generated {friendlyDate(item.generatedAt)}</Body> : null}
      {sparse ? <Notice message="Forecasts need at least 7 production days. Recorded facts remain available." /> : null}
      <Heading>Recorded facts</Heading>
      {!item.facts.daily.length ? <Body muted>No production facts are available in this window.</Body> : item.facts.daily.slice(0, showAllFacts ? undefined : 12).map((fact, index) => <Body key={`${fact.date}:${fact.recipeId}:${index}`}>{fact.date} · {fact.name} · {fact.batches} batch{fact.batches === 1 ? '' : 'es'}</Body>)}
      {item.facts.ingredients.slice(0, showAllFacts ? undefined : 12).map((fact, index) => <Body key={`${fact.productId}:${index}`}>{fact.name} · used {fact.usedAmount} {fact.baseUnit} · available {fact.quantity === null ? 'unknown' : `${fact.quantity} ${fact.baseUnit}`}</Body>)}
      {item.facts.daily.length > 12 || item.facts.ingredients.length > 12 ? <Button title={showAllFacts ? 'Show fewer facts' : `Show all facts (${item.facts.daily.length + item.facts.ingredients.length})`} variant="quiet" onPress={() => setShowAllFacts(value => !value)} /> : null}
      {item.analysis ? <><Heading>Analysis</Heading><Body>{item.analysis.summary}</Body>
        {item.analysis.trends.map((trend, index) => <Body key={`trend:${index}`}>• {trend}</Body>)}
        {item.analysis.recommendations.length ? <Heading>Suggestions</Heading> : null}
        {item.analysis.recommendations.map((recommendation, index) => <Body key={`${recommendation.recipeId}:${index}`}>• {recommendation.day}: {recommendation.name}, {recommendation.batches} batches — {recommendation.rationale}</Body>)}
        {item.analysis.risks.map((risk, index) => <Notice key={`risk:${index}`} message={risk} />)}
        {item.analysis.limitations.map((limitation, index) => <Body key={`limit:${index}`} muted>Limit: {limitation}</Body>)}</> : !sparse && data?.status === 'ready' ? <Body muted>No forecast analysis is available. Recorded facts remain authoritative.</Body> : null}
    </> : null}
    <View style={layout.wrap}>
      <Button title="Refresh forecast" variant="secondary" icon="refresh-outline" disabled={loading || requesting} onPress={() => { polls.current = 0; void load(); }} />
      {data?.status === 'not_requested' || data?.status === 'failed' || item?.stale ? <Button title={item?.stale ? 'Regenerate forecast' : 'Request forecast'} loading={requesting} onPress={() => { void requestForecast(); }} /> : null}
    </View>
    </> : null}
  </Card>;
}

const styles = StyleSheet.create({
  row: { borderWidth: 1, borderColor: colors.line, borderRadius: 16, padding: 16, minHeight: 108, flexDirection: 'row', alignItems: 'center', gap: 12 },
  selected: { backgroundColor: colors.blush, borderColor: colors.primary },
  date: { color: colors.primary, fontSize: 13, fontWeight: '700', marginBottom: 6 },
  name: { color: colors.ink, fontSize: 17, fontWeight: '700', marginBottom: 5 },
  meta: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  status: { color: colors.primary, fontSize: 12, fontWeight: '700', textTransform: 'capitalize', marginTop: 7 },
  detailRow: { borderTopWidth: 1, borderTopColor: colors.line, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 12 },
  detailName: { color: colors.ink, fontSize: 16, fontWeight: '700' },
  quantity: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  forecast: { borderColor: colors.primary },
});
