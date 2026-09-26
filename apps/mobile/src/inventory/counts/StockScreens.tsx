import React, { useCallback, useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, EmptyState, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { friendlyDate } from '@/src/ui/theme';
import { validId } from '../api';
import { InventoryPage, LoadError, Pages, useInventoryResource } from '../shared';
import { useCounts, Search, ShelfFilter } from './shared';
import { quantityLabel, entryLabel } from './measurements';

export function StockScreen() { return <InventoryPage title="Current inventory."><CurrentStock /></InventoryPage>; }
function CurrentStock() {
  const { api, actor } = useCounts(); const router = useRouter();
  const [query, setQuery] = useState(''), [cursor, setCursor] = useState(''), [shelf, setShelf] = useState(''), [filters, setFilters] = useState(false);
  const status = useInventoryResource(useCallback(() => api.status(), [api]));
  const resource = useInventoryResource(useCallback(() => api.stock(query, cursor, shelf), [api, query, cursor, shelf]));
  return <><Card><Heading>Last counted inventory</Heading><Body>Finalized product totals across your store.</Body>
    {status.data?.storeId === actor?.storeId ? <Body muted>{status.data?.lastCount ? `Last finalized count: ${status.data.lastCount.businessDate}` : 'Your first finalized count will establish opening stock.'}</Body> : null}
    <Notice message={status.error} kind="error" />
    <Button title="Count inventory" icon="clipboard-outline" onPress={() => router.push('/counts')} />
    <Button title="Count history" variant="secondary" onPress={() => router.push('/counts/history')} />
    <Button title={filters ? 'Hide search and filters' : 'Search and shelf filters'} variant="quiet" onPress={() => setFilters(!filters)} />
    {filters ? <><Search onSearch={value => { setQuery(value); setCursor(''); }} /><ShelfFilter value={shelf} onChange={value => { setShelf(value); setCursor(''); }} /></> : null}
    {query || shelf ? <Body muted>Showing filtered products. Clear search and shelf selection to see all stock.</Body> : null}
  </Card>
  {resource.loading ? <Loading label="Loading current inventory…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No matching store products" description="Assign catalog products to your store's shelves, or change your search." /></Card> : null}
    {resource.data.items.map(item => <Card key={item.productId}><Heading>{item.name}</Heading><Body muted>SKU {item.sku}</Body>
      <Heading>{quantityLabel(item.quantity, item.baseUnit)}</Heading><Body muted>{item.countedOn ? `Counted for ${item.countedOn}` : 'No finalized count yet'}</Body>
      {!item.active ? <Pill label="Archived product · previous stock retained" /> : null}
      <Button title={`View stock: ${item.name}`} variant="secondary" onPress={() => router.push({ pathname: '/stock/[productId]', params: { productId: item.productId } })} />
    </Card>)}
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}
  </>;
}
export function StockDetailScreen() {
  const { productId } = useLocalSearchParams<{ productId: string }>();
  return <InventoryPage title="Product stock.">{validId(productId) ? <StockDetails id={productId} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}
function StockDetails({ id }: { id: string }) {
  const { api } = useCounts(); const router = useRouter(); const [cursor, setCursor] = useState('');
  const resource = useInventoryResource(useCallback(() => api.stockDetail(id, cursor), [api, id, cursor]));
  if (resource.loading) return <Loading label="Loading shelf breakdown…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const item = resource.data;
  return <><Button title="Back to current inventory" variant="quiet" onPress={() => router.replace('/stock')} />
    <Card><Heading>{item.name}</Heading><Body>SKU {item.sku}</Body><Heading>{quantityLabel(item.quantity, item.baseUnit)}</Heading>
      <Body muted>{item.countedOn ? `Counted for ${item.countedOn}` : 'No finalized count yet'}</Body>
      <Body>Shelf names and measurements below reflect the finalized count.</Body>
      {item.countId ? <Button title="Open source count" variant="secondary" onPress={() => router.push({ pathname: '/counts/[countId]/review', params: { countId: item.countId! } })} /> : null}
    </Card>
    {item.locations.items.map(line => <Card key={line.id}><Heading>{line.shelfName}</Heading><Body>{quantityLabel(line.quantity, line.baseUnit)}</Body>
      <Body muted>{entryLabel(line.entry, line)}</Body><Body muted>{line.observedBy ? `Counted by @${line.observedBy}` : ''}{line.observedAt ? ` · ${friendlyDate(line.observedAt)}` : ''}</Body>
    </Card>)}<Pages next={item.locations.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>;
}
