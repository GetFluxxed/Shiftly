import React, { useCallback, useState } from 'react';
import { Alert, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill, layout } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { units, stockUnits, containerLabel, type Product, type StockUnit, validId } from './api';
import { equivalentMass } from './measurements';
import { InventoryPage, LoadError, Pages, useInventory, useInventoryResource } from './shared';

export function CatalogScreen() {
  return <InventoryPage title="Your company catalog."><CatalogList /></InventoryPage>;
}
function CatalogList() {
  const { api, canEdit } = useInventory(); const router = useRouter();
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [state, setState] = useState('active'), [cursor, setCursor] = useState('');
  const resource = useInventoryResource(useCallback(() => api.products(search, state, cursor), [api, search, state, cursor]));
  return <><Card><Heading>One product. Every store.</Heading><Body>Products and SKUs are shared across your company. Each store chooses its own shelf placements.</Body>
    {canEdit ? <Button title="Add product" icon="add" onPress={() => router.push('/catalog/new')} /> : <Body muted>Ask an owner or catalog administrator to add or edit products.</Body>}
    <Field label="Find a product or SKU" value={query} onChangeText={setQuery} maxLength={160} autoCorrect={false} />
    <Button title="Search catalog" variant="secondary" onPress={() => { if (search === query.trim() && !cursor) void resource.refresh(); setCursor(''); setSearch(query.trim()); }} />
    <Body muted>Sorted A–Z by product name.</Body>
    <View style={layout.wrap}>{['active', 'archived', 'all'].map(item => <Button key={item} title={`${item === state ? '✓ ' : ''}${item[0]!.toUpperCase()}${item.slice(1)}`} variant="quiet" onPress={() => { setCursor(''); setState(item); }} />)}</View>
  </Card>
  {resource.loading ? <Loading label="Loading products…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="cube-outline" title="No products here yet" description="Add a company product, change the filter, or try a different name or SKU." /></Card> : null}
    {resource.data.items.map(item => <ProductCard key={item.id} item={item} onPress={() => router.push({ pathname: '/catalog/[productId]', params: { productId: item.id } })} />)}
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}</>;
}
export function ProductCard({ item, onPress, action = 'View product' }: { item: Product; onPress: () => void; action?: string }) {
  return <Card><Heading>{item.name}</Heading><Body muted>SKU {item.sku} · {units[item.baseUnit]}</Body><Body muted>{containerLabel(item)}</Body>
    {!item.active ? <Pill label="Archived" /> : null}<Button title={action} variant="secondary" onPress={onPress} /></Card>;
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
function ProductForm({ item, refresh }: { item?: Product; refresh?: () => Promise<void> }) {
  const { api, identity, canEdit } = useInventory(); const router = useRouter(); const task = useTask();
  const [name, setName] = useState(item?.name || ''), [sku, setSku] = useState(item?.sku || ''), [unit, setUnit] = useState<StockUnit>('each');
  const [amount, setAmount] = useState(item?.containerAmount ?? (item ? '' : '1'));
  const baseUnit = item?.baseUnit || unit;
  const supported = (stockUnits as readonly string[]).includes(baseUnit);
  const equivalent = equivalentMass(amount.trim(), baseUnit);
  if (!canEdit && !item) return <Notice message="Catalog management permission is required to create products." />;
  const save = () => { void task.run(() => item ? api.editProduct(item, name.trim(), sku.trim(), identity, amount.trim() || null)
    : api.createProduct({ name: name.trim(), sku: sku.trim(), baseUnit: unit, containerAmount: amount.trim() || null }, identity), saved => {
      if (refresh) void refresh(); else router.replace({ pathname: '/catalog/[productId]', params: { productId: saved.id } });
    }); };
  const changeState = () => {
    if (!item) return;
    Alert.alert(item.active ? 'Archive this company product?' : 'Restore this company product?',
      item.active ? 'This affects every store in your company. Existing shelf references and history remain, but new placements are blocked.' : 'This makes the product available for shelf placement again.',
      [{ text: 'Cancel', style: 'cancel' }, { text: item.active ? 'Archive product' : 'Restore product', style: item.active ? 'destructive' : 'default',
        onPress: () => { void task.run(() => api.productState(item, !item.active, identity), () => { void refresh?.(); }); } }]);
  };
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card><Heading>{item ? 'Company product' : 'Product identity'}</Heading>
    <Body>Names and SKU edits apply to every store using this product. Old SKUs remain reserved for this product.</Body>
    {item && !item.active ? <Pill label="Archived" /> : null}
    <Field label="Product name" value={name} onChangeText={setName} maxLength={160} editable={canEdit && !task.pending} />
    <Field label="SKU" value={sku} onChangeText={setSku} maxLength={64} editable={canEdit && !task.pending} autoCapitalize="none" autoCorrect={false} hint="Leading zeros are kept. Use letters, numbers, dot, slash, dash or underscore." />
  </Card></Column><Column><Card><Heading>Base stock unit</Heading>
    {item ? <><Body>{units[item.baseUnit]}</Body><Body muted>The base unit stays fixed to protect future stock history. Full and partial containers share this SKU. Grams and kilograms can be converted without changing its base unit.</Body></>
      : <View style={layout.smallGap}>{stockUnits.map(value => <Button key={value} title={`${unit === value ? '✓ ' : ''}${units[value]}`} variant={unit === value ? 'secondary' : 'quiet'} disabled={task.pending} onPress={() => { if (value !== unit) { setUnit(value); setAmount(value === 'each' ? '1' : ''); } }} />)}</View>}
    {supported ? <><Field label={`Full container amount (${baseUnit === 'each' ? 'items' : baseUnit})`} value={amount} onChangeText={setAmount}
      keyboardType="decimal-pad" maxLength={16} editable={canEdit && !task.pending}
      hint="Net contents in one unopened container, excluding packaging. Leave blank if the size is not known yet." />
      {equivalent ? <Body muted>One full container = {amount.trim()} {baseUnit} = {equivalent}.</Body> : null}
      <Body muted>This is the standard container size. Future counts will combine full containers and measured partials under this product.</Body></> : null}
    {canEdit ? <Button title={item ? 'Save company product' : 'Create product'} loading={task.pending} disabled={!name.trim() || !sku.trim()} onPress={save} /> : <Body muted>Your account can view this product.</Body>}
    {item && canEdit ? <Button title={item.active ? 'Archive product' : 'Restore product'} variant={item.active ? 'danger' : 'secondary'} disabled={task.pending} onPress={changeState} /> : null}
    {refresh ? <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { void refresh(); }} /> : null}
    <Button title="Back to catalog" variant="quiet" onPress={() => router.replace('/catalog')} />
  </Card></Column></Columns></>;
}
