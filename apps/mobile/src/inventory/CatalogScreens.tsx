import React, { useCallback, useState } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { Body, Button, Card, EmptyState, Loading, Notice, layout } from '@/src/ui/components';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { units, containerLabel, type Product, validId } from './api';
import { InventoryItem, InventoryList } from './InventoryItem';
import { ProductForm } from './CatalogProductForm';
import { ProductMeasurementModal } from './ProductMeasurementModal';
import { InventoryPage, InventorySearch, LoadError, Pages, useInventory, useInventoryNavigation, useInventoryResource } from './shared';

export function CatalogScreen() {
  return <InventoryPage title="Your company catalog."><CatalogList /></InventoryPage>;
}
function CatalogList() {
  const { api, canEdit } = useInventory(); const navigation = useInventoryNavigation();
  const [filters, setFilters] = useRememberedState('inventory.catalog.list', { query: '', search: '', state: 'active', cursor: '' });
  const { query, search, state, cursor } = filters;
  const setQuery = (query: string) => setFilters(value => ({ ...value, query }));
  const setCursor = (cursor: string) => setFilters(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.products(search, state, cursor), [api, search, state, cursor]));
  const [changingMeasurement, setChangingMeasurement] = useState<Product | null>(null);
  return <><Card style={{ padding: 14, gap: 10 }}><Body muted>Company products · Sorted A–Z</Body>
    <Button title="Scan product" icon="barcode-outline" onPress={() => navigation.open('/catalog/scan')} />
    {canEdit ? <Button title="Add product" icon="add" onPress={() => navigation.open('/catalog/new')} /> : <Body muted>Ask an owner or catalog administrator to add or edit products.</Body>}
    <InventorySearch label="Find a product or SKU" value={query} onChange={setQuery} submitLabel="Search catalog"
      onSubmit={() => { if (search === query.trim() && !cursor) void resource.refresh(); setFilters(value => ({ ...value, cursor: '', search: query.trim() })); }} />
    <View style={layout.wrap}>{['active', 'archived', 'all'].map(item => <Button key={item} title={`${item === state ? '✓ ' : ''}${item[0]!.toUpperCase()}${item.slice(1)}`} variant="quiet" onPress={() => setFilters(value => ({ ...value, cursor: '', state: item }))} />)}</View>
  </Card>
  {resource.loading && !resource.data ? <Loading label="Loading products…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No products here yet" description="Add a company product, change the filter, or try a different name or SKU." /></Card> : null}
    <InventoryList>{resource.data.items.map(item => <ProductCard key={item.id} item={item}
      onPress={() => navigation.open({ pathname: '/catalog/[productId]', params: { productId: item.id } })}
      onChange={canEdit ? () => setChangingMeasurement(item) : undefined} changeDisabled={resource.loading} />)}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}
  <ProductMeasurementModal item={changingMeasurement} onClose={() => setChangingMeasurement(null)}
    onSaved={async () => { await resource.refresh({ preserveData: true }); }} />
  </>;
}
export function ProductCard({ item, onPress, onChange, changeDisabled = false }: {
  item: Product; onPress: () => void; onChange?: () => void; changeDisabled?: boolean;
}) {
  return <InventoryItem
    title={item.name}
    subtitle={`SKU ${item.sku} · ${units[item.baseUnit]}`}
    detail={containerLabel(item)}
    status={item.active ? undefined : 'Archived'}
    label={`View product: ${item.name}`}
    onPress={onPress}
    action={onChange ? { label: `Change measurement: ${item.name}`, title: 'Change', icon: 'resize-outline', onPress: onChange, disabled: changeDisabled } : undefined}
  />;
}
export function NewProductScreen() {
  return <InventoryPage title="Add a company product." backTo="/catalog"><ProductForm /></InventoryPage>;
}
export function ProductScreen() {
  const { productId } = useLocalSearchParams<{ productId: string }>();
  return <InventoryPage title="Product details." backTo="/catalog">{validId(productId) ? <ProductDetails id={productId} /> : <Notice message="This product is unavailable." kind="error" />}</InventoryPage>;
}
function ProductDetails({ id }: { id: string }) {
  const { api } = useInventory(); const navigation = useInventoryNavigation();
  const resource = useInventoryResource(useCallback(() => api.product(id), [api, id]));
  return resource.loading && !resource.data ? <Loading label="Loading product…" /> : resource.error || !resource.data ? <LoadError {...resource} />
    : resource.data.canonicalProductId ? <Card><Body>This catalog item is now kept as a package of another item.</Body><Button title="Open the main catalog item" onPress={() => navigation.replace({ pathname: '/catalog/[productId]', params: { productId: resource.data!.canonicalProductId! } })} /></Card>
    : <><ProductForm key={`${resource.data.id}:${resource.data.version}`} item={resource.data} refresh={resource.refresh} refreshing={resource.loading} /><Card style={{ padding: 16, gap: 10 }}><Body>Packages & barcodes</Body><Body muted>Add the containers, boxes, and cases your team receives or counts.</Body><Button title="Manage packages & barcodes" icon="barcode-outline" onPress={() => navigation.open({ pathname: '/catalog/packages/[productId]', params: { productId: id } })} /></Card></>;
}
