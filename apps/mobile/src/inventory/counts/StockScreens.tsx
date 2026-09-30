import React, { useCallback } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';
import { Body, Button, Card, EmptyState, Heading, Loading, Notice, layout } from '@/src/ui/components';
import { friendlyDate } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId } from '../api';
import { InventoryItem, InventoryList } from '../InventoryItem';
import { InventoryPage, LoadError, Pages, useInventoryResource } from '../shared';
import { useCounts, Search, ShelfFilter } from './shared';
import { quantityLabel, entryLabel } from './measurements';

export function StockScreen() { return <InventoryPage title="Current inventory."><CurrentStock /></InventoryPage>; }
function CurrentStock() {
  const { api, actor } = useCounts(); const router = useRouter();
  const [view, setView] = useRememberedState('inventory.stock.list', { query: '', cursor: '', shelf: '', filters: false });
  const { query, cursor, shelf, filters } = view; const setCursor = (cursor: string) => setView(value => ({ ...value, cursor }));
  const status = useInventoryResource(useCallback(() => api.status(), [api]));
  const resource = useInventoryResource(useCallback(() => api.stock(query, cursor, shelf), [api, query, cursor, shelf]));
  return <><Card style={{ padding: 14, gap: 10 }}>
    {status.data?.storeId === actor?.storeId ? <Body muted>{status.data?.lastCount ? `Last finalized count: ${status.data.lastCount.businessDate}` : 'Your first finalized count will establish opening stock.'}</Body> : null}
    <Notice message={status.error} kind="error" />
    <View style={layout.wrap}>
      <Button title="Count inventory" icon="clipboard-outline" onPress={() => router.push({ pathname: '/counts', params: { returnTo: 'stock' } })} />
      <Button title="Count history" variant="secondary" onPress={() => router.push({ pathname: '/counts/history', params: { returnTo: 'stock' } })} />
    </View>
    <Button title={filters ? 'Hide search and filters' : 'Search and shelf filters'} variant="quiet" onPress={() => setView(value => ({ ...value, filters: !value.filters }))} />
    {filters ? <><Search persistenceKey="inventory.stock.search" onSearch={query => setView(value => ({ ...value, query, cursor: '' }))} /><ShelfFilter persistenceKey="inventory.stock.shelf" value={shelf} onChange={shelf => setView(value => ({ ...value, shelf, cursor: '' }))} /></> : null}
    {query || shelf ? <Body muted>Showing filtered products. Clear search and shelf selection to see all stock.</Body> : null}
  </Card>
  {resource.loading ? <Loading label="Loading current inventory…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No matching store products" description="Assign catalog products to your store's shelves, or change your search." /></Card> : null}
    <InventoryList>{resource.data.items.map(item => <InventoryItem key={item.productId}
      title={item.name}
      detail={item.lastMovement === 'production' || item.lastMovement === 'reversal'
        ? `Updated ${friendlyDate(item.updatedAt || '')} · includes production`
        : item.countedOn ? `Counted for ${item.countedOn}` : 'No finalized count yet'}
      value={quantityLabel(item.quantity, item.baseUnit)}
      status={!item.active ? 'Archived product · previous stock retained' : undefined}
      label={`View stock: ${item.name}`}
      onPress={() => router.push({ pathname: '/stock/[productId]', params: { productId: item.productId } })}
    />)}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}
  </>;
}
export function StockDetailScreen() {
  const { productId } = useLocalSearchParams<{ productId: string }>();
  return <InventoryPage title="Product stock." backTo="/stock">{validId(productId) ? <StockDetails id={productId} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}
function StockDetails({ id }: { id: string }) {
  const { api } = useCounts(); const router = useRouter(); const [cursor, setCursor] = useRememberedState(`inventory.stock.${id}.cursor`, '');
  const resource = useInventoryResource(useCallback(() => api.stockDetail(id, cursor), [api, id, cursor]));
  if (resource.loading) return <Loading label="Loading shelf breakdown…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const item = resource.data;
  return <><Card><Heading>{item.name}</Heading><Heading>{quantityLabel(item.quantity, item.baseUnit)}</Heading>
      <Body muted>{item.countedOn ? `Counted for ${item.countedOn}` : 'No finalized count yet'}</Body>
      <Body muted>{item.updatedAt ? `Stock updated ${friendlyDate(item.updatedAt)}` : ''}</Body>
      <Body>Shelf measurements below are from the last physical count. Current stock also includes confirmed production deductions and corrections.</Body>
      {item.countId ? <Button title="Open last physical count" variant="secondary" onPress={() => router.push({ pathname: '/counts/[countId]/review', params: { countId: item.countId!, returnTo: 'stock' } })} /> : null}
    </Card>
    <InventoryList>{item.locations.items.map(line => <InventoryItem key={line.id}
      title={line.shelfName}
      value={quantityLabel(line.quantity, line.baseUnit)}
      subtitle={entryLabel(line.entry, line)}
      detail={`${line.observedBy ? `Counted by @${line.observedBy}` : ''}${line.observedAt ? ` · ${friendlyDate(line.observedAt)}` : ''}`}
    />)}</InventoryList><Pages next={item.locations.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>;
}
