import React, { useCallback } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, EmptyState, Loading, Notice, layout } from '@/src/ui/components';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { units, containerLabel, type Product, validId } from './api';
import { InventoryItem, InventoryList } from './InventoryItem';
import { ProductForm } from './CatalogProductForm';
import { InventoryPage, InventorySearch, LoadError, Pages, useInventory, useInventoryResource } from './shared';

export function CatalogScreen() {
  return <InventoryPage title="Your company catalog."><CatalogList /></InventoryPage>;
}
function CatalogList() {
  const { api, canEdit } = useInventory(); const router = useRouter();
  const [filters, setFilters] = useRememberedState('inventory.catalog.list', { query: '', search: '', state: 'active', cursor: '' });
  const { query, search, state, cursor } = filters;
  const setQuery = (query: string) => setFilters(value => ({ ...value, query }));
  const setCursor = (cursor: string) => setFilters(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.products(search, state, cursor), [api, search, state, cursor]));
  return <><Card style={{ padding: 14, gap: 10 }}><Body muted>Company products · Sorted A–Z</Body>
    <Button title="Scan product" icon="barcode-outline" onPress={() => router.push('/catalog/scan')} />
    {canEdit ? <Button title="Add product" icon="add" onPress={() => router.push('/catalog/new')} /> : <Body muted>Ask an owner or catalog administrator to add or edit products.</Body>}
    <InventorySearch label="Find a product or SKU" value={query} onChange={setQuery} submitLabel="Search catalog"
      onSubmit={() => { if (search === query.trim() && !cursor) void resource.refresh(); setFilters(value => ({ ...value, cursor: '', search: query.trim() })); }} />
    <View style={layout.wrap}>{['active', 'archived', 'all'].map(item => <Button key={item} title={`${item === state ? '✓ ' : ''}${item[0]!.toUpperCase()}${item.slice(1)}`} variant="quiet" onPress={() => setFilters(value => ({ ...value, cursor: '', state: item }))} />)}</View>
  </Card>
  {resource.loading ? <Loading label="Loading products…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No products here yet" description="Add a company product, change the filter, or try a different name or SKU." /></Card> : null}
    <InventoryList>{resource.data.items.map(item => <ProductCard key={item.id} item={item} onPress={() => router.push({ pathname: '/catalog/[productId]', params: { productId: item.id } })} />)}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}</>;
}
export function ProductCard({ item, onPress }: { item: Product; onPress: () => void }) {
  return <InventoryItem
    title={item.name}
    subtitle={`SKU ${item.sku} · ${units[item.baseUnit]}`}
    detail={containerLabel(item)}
    status={item.active ? undefined : 'Archived'}
    label={`View product: ${item.name}`}
    onPress={onPress}
  />;
}
export function NewProductScreen() {
  return <InventoryPage title="Add a company product."><ProductForm /></InventoryPage>;
}
export function ProductScreen() {
  const { productId } = useLocalSearchParams<{ productId: string }>();
  return <InventoryPage title="Product details.">{validId(productId) ? <ProductDetails id={productId} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}
function ProductDetails({ id }: { id: string }) {
  const { api } = useInventory();
  const resource = useInventoryResource(useCallback(() => api.product(id), [api, id]));
  return resource.loading ? <Loading label="Loading product…" /> : resource.error || !resource.data ? <LoadError {...resource} />
    : <ProductForm key={`${resource.data.id}:${resource.data.version}`} item={resource.data} refresh={resource.refresh} />;
}
