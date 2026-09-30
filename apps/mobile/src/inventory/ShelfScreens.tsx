import React, { useCallback } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { units, containerLabel, validId, type ShelfDetail } from './api';
import { InventoryItem, InventoryList } from './InventoryItem';
import { InventoryPage, InventorySearch, LoadError, Pages, useInventory, useInventoryResource } from './shared';

export function ShelvesScreen() {
  return <InventoryPage title="A place for every product."><ShelfList /></InventoryPage>;
}
function ShelfList() {
  const { api, canConfigure, identity } = useInventory(); const router = useRouter(); const task = useTask();
  const [draft, setDraft, resetDraft] = useRememberedState('inventory.shelves.list', { name: '', cursor: '' });
  const { name, cursor } = draft;
  const setName = (name: string) => setDraft(value => ({ ...value, name }));
  const setCursor = (cursor: string) => setDraft(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.shelves(cursor), [api, cursor]));
  return <><Card><Heading>Your store's shelves</Heading><Body>Give a shelf a name, then assign products from the company catalog. Placements describe where products belong, not how much stock is on hand.</Body>
    {canConfigure ? <><Notice message={task.error} kind="error" /><Field label="New shelf name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} placeholder="For example, Back freezer — top shelf" />
      <Body muted>Draft kept on this device. Save to create the shelf.</Body>
      <Button title="Create shelf" icon="add" loading={task.pending} disabled={!name.trim()} onPress={() => { void task.run(() => api.createShelf(name.trim(), identity), saved => { resetDraft(); router.push({ pathname: '/shelves/[shelfId]', params: { shelfId: saved.id } }); }); }} />
      {name ? <Button title="Discard new shelf draft" variant="quiet" disabled={task.pending} onPress={resetDraft} /> : null}</>
      : <Body muted>A manager or owner can create shelves and assign products.</Body>}
  </Card>
  {resource.loading ? <Loading label="Loading shelves…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="albums-outline" title="Your first shelf starts here" description="Create a shelf and choose which company products belong on it." /></Card> : null}
    <InventoryList>{resource.data.items.map(item => <InventoryItem
      key={item.id}
      title={item.name}
      label={`Open ${item.name}`}
      onPress={() => router.push({ pathname: '/shelves/[shelfId]', params: { shelfId: item.id } })}
    />)}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}</>;
}
export function ShelfScreen() {
  const { shelfId } = useLocalSearchParams<{ shelfId: string }>();
  return <InventoryPage title="Shelf details." backTo="/shelves">{validId(shelfId) ? <ShelfDetails id={shelfId} /> : <Notice message="This shelf is unavailable." kind="error" />}</InventoryPage>;
}
function ShelfDetails({ id }: { id: string }) {
  const { api, actor } = useInventory(); const [cursor, setCursor] = useRememberedState(`inventory.shelf.${id}.cursor`, '');
  const resource = useInventoryResource(useCallback(() => api.shelf(id, cursor), [api, id, cursor]));
  if (resource.loading) return <Loading label="Loading shelf…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Shelf is unavailable in this store.'} refresh={resource.refresh} />;
  return <><ShelfContents key={`${resource.data.id}:${resource.data.version}`} item={resource.data} refresh={resource.refresh} />
    <Pages next={resource.data.products.nextCursor} cursor={cursor} setCursor={setCursor} /></>;
}
function ShelfContents({ item, refresh }: { item: ShelfDetail; refresh: () => Promise<void> }) {
  const { api, identity, canConfigure, canEdit } = useInventory(); const router = useRouter(); const task = useTask();
  const [draft, setDraft, resetDraft] = useRememberedState(`inventory.shelf.${item.id}.edit`, { name: item.name }, String(item.version));
  const name = draft.name; const setName = (name: string) => setDraft({ name });
  const place = (productId: string, active: boolean) => { void task.run(() => api.place(item, productId, active, identity), () => { void refresh(); }); };
  return <><Notice message={task.error} kind="error" /><Columns><Column><Card><Heading>{item.name}</Heading><Pill label="Planned placement · no stock quantity" />
    {canConfigure ? <><Field label="Shelf name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} />
      <Button title="Save" variant="secondary" disabled={!name.trim() || name.trim() === item.name} loading={task.pending}
        onPress={() => { void task.run(() => api.editShelf(item, name.trim(), identity), () => { resetDraft(); void refresh(); }); }} />
      <Body muted>Draft kept on this device. Save to update this shelf.</Body></> : null}
    <Button title="Cancel" variant="quiet" disabled={task.pending} onPress={() => { resetDraft(); void refresh(); }} />
  </Card>
  <Heading>Assigned products</Heading>
  {!item.products.items.length ? <Card><Body>No products on this page. Choose products from the company catalog to assign them here.</Body></Card> : null}
  <InventoryList>{item.products.items.map(product => <InventoryItem
    key={product.id}
    title={product.name}
    detail={product.containerAmount === null ? `Container size not set · ${units[product.baseUnit]}` : containerLabel(product)}
    status={product.active ? undefined : 'Archived'}
    action={canConfigure ? {
      label: `Remove ${product.name} from shelf`,
      title: 'Remove',
      icon: 'remove-circle-outline',
      disabled: task.pending,
      onPress: () => place(product.id, false),
    } : undefined}
  />)}</InventoryList></Column>
  {canConfigure ? <Column><Card><Heading>Add from the company catalog</Heading><Body>The same product can belong on more than one shelf. Removing it here leaves the company product and other shelves unchanged.</Body>
    {canEdit ? <Button title="Create a company product" variant="quiet" disabled={task.pending} onPress={() => router.push('/catalog/new')} /> : null}
    <ProductPicker shelfId={item.id} assigned={item.products.items.map(p => p.id)} disabled={task.pending} onAdd={id => place(id, true)} />
  </Card></Column> : null}</Columns></>;
}
function ProductPicker({ shelfId, assigned, disabled, onAdd }: { shelfId: string; assigned: string[]; disabled: boolean; onAdd: (id: string) => void }) {
  const { api } = useInventory();
  const [filters, setFilters] = useRememberedState(`inventory.shelf.${shelfId}.picker`, { query: '', search: '', cursor: '' });
  const { query, search, cursor } = filters;
  const setQuery = (query: string) => setFilters(value => ({ ...value, query }));
  const setCursor = (cursor: string) => setFilters(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.products(search, 'active', cursor), [api, search, cursor]));
  return <><Body muted>Products A–Z</Body><InventorySearch label="Find a product to assign" value={query} onChange={setQuery} submitLabel="Find products" disabled={disabled}
    onSubmit={() => { if (search === query.trim() && !cursor) void resource.refresh(); setFilters(value => ({ ...value, cursor: '', search: query.trim() })); }} />
    {resource.loading ? <Loading label="Finding products…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
      {!resource.data.items.length ? <Body>No matching active products. Add one to the company catalog or change your search.</Body> : null}
      <InventoryList>{resource.data.items.map(p => {
        const isAssigned = assigned.includes(p.id);
        return <InventoryItem
          key={p.id}
          title={p.name}
          subtitle={`SKU ${p.sku} · ${units[p.baseUnit]}`}
          detail={containerLabel(p)}
          label={isAssigned ? `${p.name} is assigned` : `Assign ${p.name}`}
          icon={isAssigned ? 'checkmark-circle-outline' : 'add-circle-outline'}
          disabled={disabled || isAssigned}
          onPress={() => onAdd(p.id)}
        />;
      })}</InventoryList>
      <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
    </>}</>;
}
