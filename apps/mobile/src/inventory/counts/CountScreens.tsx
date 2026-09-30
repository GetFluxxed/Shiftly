import React, { useCallback } from 'react';
import { Alert } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { friendlyDate } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId } from '../api';
import { InventoryItem, InventoryList } from '../InventoryItem';
import { InventoryPage, LoadError, Pages, useInventoryResource } from '../shared';
import { useCounts, CountHeading, Search, ShelfFilter, countBackTo, countRouteParams } from './shared';
import { quantityLabel } from './measurements';
import type { Count } from './api';

function today() { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`; }
export function CountsScreen() {
  const { returnTo } = useLocalSearchParams<{ returnTo?: string }>();
  return <InventoryPage title="Count inventory." backTo={countBackTo(returnTo)}><CountStart returnTo={returnTo} /></InventoryPage>;
}
function CountStart({ returnTo }: { returnTo?: string }) {
  const { api, identity, canCount, actor } = useCounts(); const task = useTask(); const router = useRouter();
  const [day, setDay, resetDay] = useRememberedState('inventory.count.start-day', today);
  const resource = useInventoryResource(useCallback(() => api.status(), [api]));
  if (resource.loading) return <Loading label="Checking open counts…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Count status is unavailable.'} refresh={resource.refresh} />;
  const open = resource.data.openCount;
  return <><Notice message={task.error} kind="error" />
    {open ? <><CountHeading item={open} /><Card><Body>This store already has an open count. Continue its saved entries.</Body>
      <Button title={open.state === 'review' ? 'Review open count' : 'Resume count'} onPress={() => router.push({ pathname: open.state === 'review' ? '/counts/[countId]/review' : '/counts/[countId]', params: { countId: open.id, ...countRouteParams(returnTo) } })} />
    </Card></> : <Card><Heading>Start a fresh store count</Heading><Body>Your current inventory stays unchanged. Every shelf entry starts as not counted; confirm zero only when none remains.</Body>
      <Body muted>Count at a stable cutoff, normally after service. Save each entry before leaving its screen. Finalizing a complete count updates the store totals.</Body>
      {canCount ? <><Field label="Count date (YYYY-MM-DD)" value={day} onChangeText={setDay} maxLength={10} editable={!task.pending} autoCorrect={false} />
        <Button title="Start store count" loading={task.pending} disabled={!/^\d{4}-\d{2}-\d{2}$/.test(day)} onPress={() => { void task.run(() => api.start(day, identity), count => { resetDay(); router.replace({ pathname: '/counts/[countId]', params: { countId: count.id, ...countRouteParams(returnTo) } }); }); }} />
      </> : <Body muted>Ask an administrator for permission to enter inventory counts.</Body>}
    </Card>}
    <Button title="Count history" variant="secondary" onPress={() => router.push({ pathname: '/counts/history', params: countRouteParams(returnTo) })} />
  </>;
}
export function CountSessionScreen() {
  const { countId, returnTo } = useLocalSearchParams<{ countId: string; returnTo?: string }>();
  return <InventoryPage title="Your store count." backTo={countBackTo(returnTo)}>{validId(countId) ? <CountWorkspace id={countId} returnTo={returnTo} /> : <Notice message="This count is unavailable." kind="error" />}</InventoryPage>;
}
function CountWorkspace({ id, returnTo }: { id: string; returnTo?: string }) {
  const { api, actor } = useCounts();
  const resource = useInventoryResource(useCallback(() => api.detail(id), [api, id]));
  if (resource.loading) return <Loading label="Loading saved count…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Count unavailable.'} refresh={resource.refresh} />;
  return <><CountHeading item={resource.data} /><CountEntries count={resource.data} returnTo={returnTo} /></>;
}
function CountEntries({ count, returnTo }: { count: Count; returnTo?: string }) {
  const { api, canCount } = useCounts(); const router = useRouter();
  const [filters, setFilters] = useRememberedState(`inventory.count.${count.id}.entries`, { query: '', cursor: '', shelf: '', missing: false });
  const { query, cursor, shelf, missing } = filters;
  const setCursor = (cursor: string) => setFilters(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.lines(count.id, query, cursor, shelf, missing), [api, count.id, query, cursor, shelf, missing]));
  return <><Card><Button title={count.state === 'posted' ? 'View count comparison' : 'Review count'} onPress={() => router.push({ pathname: '/counts/[countId]/review', params: { countId: count.id, ...countRouteParams(returnTo) } })} />
    <Body>Count only what is physically at each listed location. Quantities on different shelves add to the same product total.</Body>
    <Search persistenceKey={`inventory.count.${count.id}.entries.search`} onSearch={query => setFilters(value => ({ ...value, query, cursor: '' }))} /><ShelfFilter persistenceKey={`inventory.count.${count.id}.entries.shelf`} value={shelf} onChange={shelf => setFilters(value => ({ ...value, shelf, cursor: '' }))} />
    <Button title={missing ? 'Show all entries' : 'Show not counted'} variant="secondary" onPress={() => setFilters(value => ({ ...value, missing: !value.missing, cursor: '' }))} />
  </Card>
  {resource.loading ? <Loading label="Loading count entries…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><Body>No matching entries. Change your filters to see the rest of the count.</Body></Card> : null}
    <InventoryList>{resource.data.items.map(line => <InventoryItem key={line.id}
      title={line.name}
      subtitle={line.shelfName}
      status={line.quantity === null ? 'Not counted' : `Saved: ${quantityLabel(line.quantity, line.baseUnit)}`}
      label={`${count.state === 'draft' && canCount ? 'Count' : 'View'} ${line.name} · ${line.shelfName}`}
      onPress={() => router.push({ pathname: '/counts/[countId]/line/[lineId]', params: { countId: count.id, lineId: line.id, ...countRouteParams(returnTo) } })}
    />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}</>;
}
export function CountReviewScreen() {
  const { countId, returnTo } = useLocalSearchParams<{ countId: string; returnTo?: string }>();
  return <InventoryPage title="Review your count." backTo={countBackTo(returnTo)}>{validId(countId) ? <CountReview id={countId} returnTo={returnTo} /> : <Notice message="This count is unavailable." kind="error" />}</InventoryPage>;
}
function CountReview({ id, returnTo }: { id: string; returnTo?: string }) {
  const { api, identity, canCount, canApprove, actor } = useCounts(); const router = useRouter(); const task = useTask();
  const [filters, setFilters] = useRememberedState(`inventory.count.${id}.review`, { query: '', cursor: '' });
  const { query, cursor } = filters; const setCursor = (cursor: string) => setFilters(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.detail(id), [api, id]));
  const comparisons = useInventoryResource(useCallback(() => api.comparison(id, query, cursor), [api, id, query, cursor]));
  if (resource.loading) return <Loading label="Loading count review…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Count unavailable.'} refresh={resource.refresh} />;
  const count = resource.data, complete = count.totalLines > 0 && count.countedLines === count.totalLines;
  const act = (action: 'review' | 'post' | 'reopen' | 'cancel') => { void task.run(() => api.transition(count, action, identity), () => { void resource.refresh(); void comparisons.refresh(); }); };
  return <><CountHeading item={count} /><Notice message={task.error} kind="error" />
    <Button title="Back to count entries" variant="quiet" disabled={task.pending} onPress={() => router.replace({ pathname: '/counts/[countId]', params: { countId: id, ...countRouteParams(returnTo) } })} />
    <Card><Heading>Changes since the previous count</Heading><Body>These are stock changes, not ingredient usage. Deliveries, waste and transfers are not recorded in this first version.</Body>
      {!complete ? <Notice message="Some locations have not been counted. Complete them or explicitly confirm zero before submitting." /> : null}
      {count.state === 'draft' && canCount ? <Button title="Submit for review" loading={task.pending} disabled={!complete || count.configurationChanged} onPress={() => act('review')} /> : null}
      {count.state === 'review' && canApprove ? <><Button title="Finalize inventory count" loading={task.pending} disabled={!complete || count.configurationChanged} onPress={() => Alert.alert('Finalize this count?', 'This replaces the counted products’ current stock with these reviewed totals and saves permanent history.', [{ text: 'Keep reviewing', style: 'cancel' }, { text: 'Finalize count', onPress: () => act('post') }])} />
        <Button title="Return to counting" variant="secondary" disabled={task.pending} onPress={() => act('reopen')} /></> : null}
      {count.state === 'review' && !canApprove ? <Body muted>An account with count-approval permission must finalize this count.</Body> : null}
      {['draft', 'review'].includes(count.state) && canApprove ? <Button title="Cancel this count" variant="quiet" disabled={task.pending} onPress={() => Alert.alert('Cancel this count?', 'Saved entries will stay in history. Current inventory will not change.', [{ text: 'Keep count', style: 'cancel' }, { text: 'Cancel count', style: 'destructive', onPress: () => act('cancel') }])} /> : null}
      {count.state === 'posted' ? <><Notice message="Count finalized. Current inventory now shows these totals." /><Button title="View current inventory" onPress={() => router.replace('/stock')} /></> : null}
      <Search persistenceKey={`inventory.count.${id}.review.search`} onSearch={query => setFilters(value => ({ ...value, query, cursor: '' }))} />
    </Card>
    {comparisons.loading ? <Loading label="Comparing quantities…" /> : comparisons.error || !comparisons.data ? <LoadError {...comparisons} /> : <>
      {!comparisons.data.items.length ? <Card><Body>No matching products.</Body></Card> : null}
      <InventoryList>{comparisons.data.items.map(item => <InventoryItem key={item.productId}
        title={item.name}
        subtitle={`${item.locations} locations`}
        detail={`Previous: ${item.previousQuantity === null ? 'No previous count' : quantityLabel(item.previousQuantity, item.baseUnit)} · New count: ${quantityLabel(item.quantity, item.baseUnit)}`}
        status={item.missing ? `${item.missing} locations not counted` : item.previousQuantity === null ? 'Opening balance' : `Change: ${item.difference && !item.difference.startsWith('-') && item.difference !== '0' ? '+' : ''}${quantityLabel(item.difference, item.baseUnit)}`}
      />)}</InventoryList><Pages next={comparisons.data.nextCursor} cursor={cursor} setCursor={setCursor} />
    </>}
  </>;
}
export function CountHistoryScreen() {
  const { returnTo } = useLocalSearchParams<{ returnTo?: string }>();
  return <InventoryPage title="Count history." backTo={countBackTo(returnTo)}><History returnTo={returnTo} /></InventoryPage>;
}
function History({ returnTo }: { returnTo?: string }) {
  const { api } = useCounts(); const router = useRouter(); const [cursor, setCursor] = useRememberedState('inventory.count.history.cursor', '');
  const resource = useInventoryResource(useCallback(() => api.history(cursor), [api, cursor]));
  if (resource.loading) return <Loading label="Loading count history…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  return <><Card><Heading>A record of every completed count</Heading><Body>Finalized and cancelled counts remain available. Catalog edits do not change their recorded quantities or container references.</Body></Card>
    {!resource.data.items.length ? <Card><Body>No completed counts yet.</Body></Card> : null}
    <InventoryList>{resource.data.items.map(item => <InventoryItem key={item.id}
      title={item.businessDate}
      subtitle={`${item.totalProducts} products · Started by @${item.startedBy}`}
      detail={friendlyDate(item.startedAt)}
      status={item.state === 'posted' ? 'Finalized' : 'Cancelled'}
      label={`Open count ${item.businessDate}`}
      onPress={() => router.push({ pathname: '/counts/[countId]/review', params: { countId: item.id, ...countRouteParams(returnTo) } })}
    />)}</InventoryList><Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>;
}
