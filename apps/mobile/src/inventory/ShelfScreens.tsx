import React, { useCallback, useState } from 'react';
import { useLocalSearchParams } from 'expo-router';
import { Body, Button, Card, EmptyState, Field, Heading, Loading, Notice } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { validId, type Shelf, type ShelfDetail } from './api';
import { InventoryItem, InventoryList } from './InventoryItem';
import { InventoryPage, LoadError, Pages, useInventory, useInventoryNavigation, useInventoryResource } from './shared';
import { ShelfProductPicker } from './ShelfProductPicker';
import { quantityLabel } from './counts/measurements';
import { ShelfNameModal } from './ShelfNameModal';

export function ShelvesScreen() {
  return <InventoryPage title="A place for every product."><ShelfList /></InventoryPage>;
}
function ShelfList() {
  const { api, canConfigure, identity } = useInventory(); const navigation = useInventoryNavigation(); const task = useTask();
  const [draft, setDraft, resetDraft] = useRememberedState('inventory.shelves.list', { name: '', cursor: '' });
  const { name, cursor } = draft;
  const setName = (name: string) => setDraft(value => ({ ...value, name }));
  const setCursor = (cursor: string) => setDraft(value => ({ ...value, cursor }));
  const resource = useInventoryResource(useCallback(() => api.shelves(cursor), [api, cursor]));
  const [editing, setEditing] = useState<Shelf | null>(null);
  return <><Card><Heading>Shelves</Heading><Body>Assign products here; record quantities in Count inventory.</Body>
    {canConfigure ? <><Notice message={task.error} kind="error" /><Field label="New shelf name" value={name} onChangeText={setName} maxLength={120} editable={!task.pending} placeholder="For example, Back freezer — top shelf" />

      <Button title="Create shelf" icon="add" loading={task.pending} disabled={!name.trim()} onPress={() => { void task.run(() => api.createShelf(name.trim(), identity), saved => { resetDraft(); navigation.open({ pathname: '/shelves/[shelfId]', params: { shelfId: saved.id } }); }); }} />
      {name ? <Button title="Discard new shelf draft" variant="quiet" disabled={task.pending} onPress={resetDraft} /> : null}</>
      : <Body muted>A manager or owner can create shelves and assign products.</Body>}
  </Card>
  {resource.loading ? <Loading label="Loading shelves…" /> : resource.error || !resource.data ? <LoadError {...resource} /> : <>
    {!resource.data.items.length ? <Card><EmptyState icon="albums-outline" title="Your first shelf starts here" description="Create a shelf and choose which company products belong on it." /></Card> : null}
    <InventoryList>{resource.data.items.map(item => <InventoryItem
      key={item.id}
      title={item.name}
      label={`Open ${item.name}`}
      onPress={() => navigation.open({ pathname: '/shelves/[shelfId]', params: { shelfId: item.id } })}
      action={canConfigure ? { label: `Edit shelf name: ${item.name}`, icon: 'create-outline', disabled: task.pending, onPress: () => setEditing(item) } : undefined}
    />)}</InventoryList>
    <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} />
  </>}
  <ShelfNameModal item={editing} onClose={() => setEditing(null)} onLatest={setEditing} onSaved={() => { setEditing(null); void resource.refresh(); }} /></>;
}
export function ShelfScreen() {
  const { shelfId } = useLocalSearchParams<{ shelfId: string }>();
  return <InventoryPage title="Shelf details." backTo="/shelves">{validId(shelfId) ? <ShelfDetails id={shelfId} /> : <Notice message="This shelf is unavailable." kind="error" />}</InventoryPage>;
}
function ShelfDetails({ id }: { id: string }) {
  const { api, actor } = useInventory(); const [cursor, setCursor] = useRememberedState(`inventory.shelf.${id}.cursor`, '');
  const resource = useInventoryResource(useCallback(() => api.shelf(id, cursor), [api, id, cursor]));
  if (resource.loading && !resource.data) return <Loading label="Loading shelf…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Shelf is unavailable in this store.'} refresh={resource.refresh} />;
  return <ShelfContents key={resource.data.id} item={resource.data} cursor={cursor} setCursor={setCursor}
    refreshing={resource.loading} refresh={() => resource.refresh({ preserveData: true })} />;
}
function ShelfContents({ item, refresh, refreshing, cursor, setCursor }: {
  item: ShelfDetail; refresh: () => Promise<void>; refreshing: boolean; cursor: string; setCursor: (value: string) => void;
}) {
  const { api, identity, canConfigure, canEdit } = useInventory(); const navigation = useInventoryNavigation();
  const task = useTask();
  const pending = refreshing || task.pending;
  const [confirmedPlacements, setConfirmedPlacements] = useState<{ version: number; ids: string[] } | null>(null);
  // Remember successful actions even when a new product sorts outside this
  // placement page. This is session-local confirmation, never persisted stock.
  const assigned = new Set(item.products.items.map(product => product.id));
  if (confirmedPlacements?.version === item.version) {
    for (const productId of confirmedPlacements.ids) assigned.add(productId);
  }
  const place = (productId: string, active: boolean) => {
    if (pending) return;
    void task.run(async () => {
      const saved = await api.place(item, productId, active, identity);
      // Retain the picker while reading the authoritative page and next version.
      // Await it so the next write cannot submit the previous shelf version.
      await refresh();
      return saved;
    }, saved => setConfirmedPlacements(current => {
      // Carry confirmations forward only through our own version-checked writes.
      // A newer read/version from another editor always invalidates this bridge.
      const ids = new Set(current?.version === item.version ? current.ids : []);
      if (active) ids.add(productId); else ids.delete(productId);
      return { version: saved.version, ids: [...ids] };
    }));
  };
  return <><Notice message={task.error} kind="error" />
  <Heading>Assigned products</Heading>
  <Body muted>Amounts shown are storewide.</Body>
  <InventoryList>{!item.products.items.length
    ? <InventoryItem title="No assigned products" detail="Choose products below." /> : null}{item.products.items.map(product => <InventoryItem
    key={product.id}
    title={product.name}
    value={product.storeQuantity === null ? 'N/A' : quantityLabel(product.storeQuantity, product.baseUnit)}
    detail="Storewide current inventory"
    status={product.active ? undefined : 'Archived'}
    action={canConfigure ? {
      label: `Remove ${product.name} from shelf`,
      title: 'Remove',
      icon: 'remove-circle-outline',
      disabled: pending,
      onPress: () => place(product.id, false),
    } : undefined}
  />)}</InventoryList>
  <Pages next={item.products.nextCursor} cursor={cursor} setCursor={setCursor} disabled={pending} />
  <Heading>{item.name}</Heading>
  {canConfigure ? <Card>
    <ShelfProductPicker shelfId={item.id} assigned={[...assigned]} disabled={pending} onAdd={id => place(id, true)} />
    {canEdit ? <Button title="Create a company product" variant="quiet" disabled={pending} onPress={() => navigation.open('/catalog/new')} /> : null}
  </Card> : null}</>;
}
