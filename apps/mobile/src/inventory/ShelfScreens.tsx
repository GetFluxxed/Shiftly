import React, { useCallback, useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { units, containerLabel, validId, type ShelfDetail } from './api';
import { InventoryPage, LoadError, Pages, useInventory, useInventoryResource } from './shared';

export function ShelvesScreen() {
  return <InventoryPage title="A place for every product."><ShelfList /></InventoryPage>;
}
function ShelfList() {
  const { api, canConfigure, identity } = useInventory(); const router = useRouter(); const task = useTask();
  const [name, setName] = useState(''), [cursor, setCursor] = useState('');
  const resource = useInventoryResource(useCallback(() => api.shelves(cursor), [api, cursor]));
  return <><Card><Heading>Your store's shelves</Heading><Body>Give a shelf a name, then assign products from the company catalog. Placements describe where products belong, not how much stock is on hand.</Body>
    {canConfigure ? <><Notice message={task.error} kind="error" /><Field label="New shelf name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} placeholder="For example, Back freezer — top shelf" />
      <Button title="Create shelf" icon="add" loading={task.pending} disabled={!name.trim()} onPress={() => { void task.run(() => api.createShelf(name.trim(), identity), saved => router.push({ pathname: '/shelves/[shelfId]', params: { shelfId: saved.id } })); }} /></>
      : <Body muted>A manager or owner can create shelves and assign products.</Body>}
  </Card>
  {resource.loading ? <Loading label="Loading shelves…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="albums-outline" title="Your first shelf starts here" description="Create a shelf and choose which company products belong on it." /></Card> : null}
    {resource.data.items.map(item => <Card key={item.id}><Heading>{item.name}</Heading><Button title={`Open ${item.name}`} variant="secondary" onPress={() => router.push({ pathname: '/shelves/[shelfId]', params: { shelfId: item.id } })} /></Card>)}
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}</>;
}
export function ShelfScreen() {
  const { shelfId } = useLocalSearchParams<{ shelfId: string }>();
  return <InventoryPage title="Shelf details.">{validId(shelfId) ? <ShelfDetails id={shelfId} /> : <Notice message="This shelf is unavailable." kind="error" />}</InventoryPage>;
}
function ShelfDetails({ id }: { id: string }) {
  const { api, actor } = useInventory(); const [cursor, setCursor] = useState('');
  const resource = useInventoryResource(useCallback(() => api.shelf(id, cursor), [api, id, cursor]));
  if (resource.loading) return <Loading label="Loading shelf…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Shelf is unavailable in this store.'} refresh={resource.refresh} />;
  return <><ShelfContents key={`${resource.data.id}:${resource.data.version}`} item={resource.data} refresh={resource.refresh} />
    <Pages next={resource.data.products.nextCursor} cursor={cursor} setCursor={setCursor} /></>;
}
function ShelfContents({ item, refresh }: { item: ShelfDetail; refresh: () => Promise<void> }) {
  const { api, identity, canConfigure, canEdit } = useInventory(); const router = useRouter(); const task = useTask();
  const [name, setName] = useState(item.name);
  const place = (productId: string, active: boolean) => { void task.run(() => api.place(item, productId, active, identity), () => { void refresh(); }); };
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card><Heading>{item.name}</Heading><Pill label="Planned placement · no stock quantity" />
    {canConfigure ? <><Field label="Shelf name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} />
      <Button title="Save shelf name" variant="secondary" disabled={!name.trim() || name.trim() === item.name} loading={task.pending}
        onPress={() => { void task.run(() => api.editShelf(item, name.trim(), identity), () => { void refresh(); }); }} /></> : null}
    <Button title="Discard edits and reload" variant="quiet" disabled={task.pending} onPress={() => { void refresh(); }} />
  </Card>
  <Heading>Assigned products</Heading>
  {!item.products.items.length ? <Card><Body>No products on this page. Choose products from the company catalog to assign them here.</Body></Card> : null}
  {item.products.items.map(product => <Card key={product.id}><Heading>{product.name}</Heading><Body muted>SKU {product.sku} · {units[product.baseUnit]}</Body><Body muted>{containerLabel(product)}</Body>
    {!product.active ? <Pill label="Archived company product" /> : null}
    {canConfigure ? <Button title={`Remove ${product.name} from shelf`} variant="secondary" disabled={task.pending} onPress={() => place(product.id, false)} /> : null}
  </Card>)}</Column>
  {canConfigure ? <Column><Card><Heading>Add from the company catalog</Heading><Body>The same product can belong on more than one shelf. Removing it here leaves the company product and other shelves unchanged.</Body>
    {canEdit ? <Button title="Create a company product" variant="quiet" disabled={task.pending} onPress={() => router.push('/catalog/new')} /> : null}
    <ProductPicker assigned={item.products.items.map(p => p.id)} disabled={task.pending} onAdd={id => place(id, true)} />
  </Card></Column> : null}</Columns></>;
}
function ProductPicker({ assigned, disabled, onAdd }: { assigned: string[]; disabled: boolean; onAdd: (id: string) => void }) {
  const { api } = useInventory();
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [cursor, setCursor] = useState('');
  const resource = useInventoryResource(useCallback(() => api.products(search, 'active', cursor), [api, search, cursor]));
  return <><Field label="Find a product to assign" value={query} onChangeText={setQuery} maxLength={160} editable={!disabled} autoCorrect={false} />
    <Button title="Find products" variant="secondary" disabled={disabled} onPress={() => { if (search === query.trim() && !cursor) void resource.refresh(); setCursor(''); setSearch(query.trim()); }} />
    {resource.loading ? <Loading label="Finding products…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
      {!resource.data.items.length ? <Body>No matching active products. Add one to the company catalog or change your search.</Body> : null}
      {resource.data.items.map(p => <React.Fragment key={p.id}><Body>{p.name} · SKU {p.sku}</Body>
        <Button title={assigned.includes(p.id) ? `${p.name} is assigned` : `Assign ${p.name}`} variant="secondary" disabled={disabled || assigned.includes(p.id)} onPress={() => onAdd(p.id)} /></React.Fragment>)}
      <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
    </>}</>;
}
