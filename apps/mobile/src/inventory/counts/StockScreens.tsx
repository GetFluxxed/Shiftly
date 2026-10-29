import React, { useCallback } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { Body, Button, Card, EmptyState, Heading, Loading, Notice, layout } from '@/src/ui/components';
import { colors, friendlyDate } from '@/src/ui/theme';
import { Text } from '@/src/ui/Typography';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId } from '../api';
import { InventoryItem, InventoryList } from '../InventoryItem';
import { InventoryPage, LoadError, Pages, useInventoryNavigation, useInventoryResource } from '../shared';
import { useCounts, Search, ShelfFilter } from './shared';
import { quantityLabel, entryLabel } from './measurements';

export function StockScreen() { return <InventoryPage title="Current inventory."><CurrentStock /></InventoryPage>; }
function CurrentStock() {
  const { api, actor } = useCounts(); const nav = useInventoryNavigation();
  const [view, setView] = useRememberedState('inventory.stock.list', { query: '', cursor: '', shelf: '', filters: false });
  const { query, cursor, shelf, filters } = view; const setCursor = (cursor: string) => setView(value => ({ ...value, cursor }));
  const status = useInventoryResource(useCallback(() => api.status(), [api]));
  const resource = useInventoryResource(useCallback(() => api.stock(query, cursor, shelf), [api, query, cursor, shelf]));
  return <><Card style={{ padding: 14, gap: 10 }}>
    {status.data?.storeId === actor?.storeId ? <Body muted>{status.data?.lastCount ? `Last finalized count: ${status.data.lastCount.businessDate}` : 'Finalize your first count to set opening stock.'}</Body> : null}
    <Notice message={status.error} kind="error" />
    <View style={layout.wrap}>
      <Button title="Count inventory" icon="clipboard-outline" onPress={() => nav.open({ pathname: '/counts', params: { returnTo: 'stock' } })} />
      <Button title="Count history" variant="secondary" onPress={() => nav.open({ pathname: '/counts/history', params: { returnTo: 'stock' } })} />
    </View>
    <Button title={filters ? 'Hide search and filters' : 'Search and shelf filters'} variant="quiet" onPress={() => setView(value => ({ ...value, filters: !value.filters }))} />
    {filters ? <><Search persistenceKey="inventory.stock.search" onSearch={query => setView(value => ({ ...value, query, cursor: '' }))} /><ShelfFilter persistenceKey="inventory.stock.shelf" value={shelf} onChange={shelf => setView(value => ({ ...value, shelf, cursor: '' }))} /></> : null}
    {query || shelf ? <Body muted>Filters applied.</Body> : null}
  </Card>
  {resource.loading ? <Loading label="Loading current inventory…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No matching store products" description="Assign catalog products to your store's shelves, or change your search." /></Card> : null}
    {resource.data.items.length ? <StockTable items={resource.data.items} onOpen={productId => nav.open({ pathname: '/stock/[productId]', params: { productId } })} /> : null}
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}
  </>;
}

function StockTable({ items, onOpen }: { items: import('./api').StockItem[]; onOpen: (id: string) => void }) {
  return <Card style={styles.table}><View style={styles.header} accessibilityRole="header"><Text style={[styles.headText, styles.name]}>Product</Text><Text style={[styles.headText, styles.quantity]}>Quantity</Text><Text style={[styles.headText, styles.unit]}>Unit</Text><Text style={[styles.headText, styles.updated]}>Updated</Text></View>
    {items.map(item => <Pressable key={item.productId} accessibilityRole="button" accessibilityLabel={`View stock: ${item.name}. ${item.quantity === null ? 'N/A' : item.quantity} ${item.baseUnit === 'each' ? 'items' : item.baseUnit}`} onPress={() => onOpen(item.productId)} style={styles.row}>
      <View style={styles.name}><Text numberOfLines={2} style={styles.product}>{item.name}</Text>{!item.active ? <Text style={styles.archived}>Archived</Text> : null}</View>
      <Text style={[styles.cell, styles.quantity, styles.exactQuantity]}>{item.quantity === null ? 'N/A' : item.quantity}</Text>
      <Text style={[styles.cell, styles.unit]} numberOfLines={1}>{item.baseUnit === 'each' ? 'items' : item.baseUnit}</Text>
      <Text style={[styles.cell, styles.updated]} numberOfLines={2}>{item.updatedAt ? friendlyDate(item.updatedAt) : '—'}</Text>
    </Pressable>)}</Card>;
}
export function StockDetailScreen() {
  const { productId } = useLocalSearchParams<{ productId: string }>();
  return <InventoryPage title="Product stock." backTo="/stock">{validId(productId) ? <StockDetails id={productId} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}
const styles = StyleSheet.create({
  table: { padding: 0, overflow: 'hidden' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 9, backgroundColor: colors.soft, borderBottomWidth: 1, borderBottomColor: colors.line },
  row: { flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 54, paddingHorizontal: 10, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.line },
  name: { flex: 1, minWidth: 0 }, quantity: { width: 66, textAlign: 'right' }, unit: { width: 32 }, updated: { width: 50 },
  headText: { color: colors.muted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase' },
  cell: { color: colors.ink, fontSize: 12 }, exactQuantity: { fontSize: 10, fontVariant: ['tabular-nums'] }, product: { color: colors.ink, fontSize: 14, fontWeight: '700' }, archived: { color: colors.danger, fontSize: 11, marginTop: 2 },
});
function StockDetails({ id }: { id: string }) {
  const { api } = useCounts(); const nav = useInventoryNavigation(); const [cursor, setCursor] = useRememberedState(`inventory.stock.${id}.cursor`, '');
  const resource = useInventoryResource(useCallback(() => api.stockDetail(id, cursor), [api, id, cursor]));
  if (resource.loading) return <Loading label="Loading shelf breakdown…" />;
  if (resource.error || !resource.data) return <LoadError {...resource} />;
  const item = resource.data;
  return <><Card><Heading>{item.name}</Heading><Heading>{quantityLabel(item.quantity, item.baseUnit)}</Heading>
      <Body muted>{item.countedOn ? `Counted for ${item.countedOn}` : 'No finalized count yet'}</Body>
      <Body muted>{item.updatedAt ? `Stock updated ${friendlyDate(item.updatedAt)}` : ''}</Body>
      <Body>Shelf amounts show the last count. Current totals include later stock changes.</Body>
      {item.countId ? <Button title="Open last physical count" variant="secondary" onPress={() => nav.open({ pathname: '/counts/[countId]/review', params: { countId: item.countId!, returnTo: 'stock' } })} /> : null}
    </Card>
    <InventoryList>{item.locations.items.map(line => <InventoryItem key={line.id}
      title={line.shelfName}
      value={quantityLabel(line.quantity, line.baseUnit)}
      subtitle={entryLabel(line.entry, line)}
      detail={`${line.observedBy ? `Counted by @${line.observedBy}` : ''}${line.observedAt ? ` · ${friendlyDate(line.observedAt)}` : ''}`}
    />)}</InventoryList><Pages next={item.locations.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>;
}
