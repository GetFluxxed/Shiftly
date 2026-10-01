import React, { useCallback, useState } from 'react';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Column, Columns, EmptyState, Field, Heading, Loading, Notice, Pill } from '@/src/ui/components';
import { useTask } from '@/src/ui/useTask';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { units, containerLabel, validId, type ShelfDetail } from './api';
import { InventoryItem, InventoryList } from './InventoryItem';
import { InventoryPage, LoadError, Pages, useInventory, useInventoryResource } from './shared';
import { ShelfProductPicker } from './ShelfProductPicker';

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
  if (resource.loading && !resource.data) return <Loading label="Loading shelf…" />;
  if (resource.error || !resource.data || resource.data.storeId !== actor?.storeId) return <LoadError error={resource.error || 'Shelf is unavailable in this store.'} refresh={resource.refresh} />;
  return <ShelfContents key={resource.data.id} item={resource.data} cursor={cursor} setCursor={setCursor}
    refreshing={resource.loading} refresh={() => resource.refresh({ preserveData: true })} />;
}
function ShelfContents({ item, refresh, refreshing, cursor, setCursor }: {
  item: ShelfDetail; refresh: () => Promise<void>; refreshing: boolean; cursor: string; setCursor: (value: string) => void;
}) {
  const { api, identity, canConfigure, canEdit } = useInventory(); const router = useRouter();
  const task = useTask();
  const pending = refreshing || task.pending;
  const [confirmedPlacements, setConfirmedPlacements] = useState<{ version: number; ids: string[] } | null>(null);
  // Remember successful actions even when a new product sorts outside this
  // placement page. This is session-local confirmation, never persisted stock.
  const assigned = new Set(item.products.items.map(product => product.id));
  if (confirmedPlacements?.version === item.version) {
    for (const productId of confirmedPlacements.ids) assigned.add(productId);
  }
  // Assignment versions change independently of the name being edited.
  const [draft, setDraft, resetDraft] = useRememberedState(`inventory.shelf.${item.id}.edit`, { name: item.name }, item.name);
  const name = draft.name; const setName = (name: string) => setDraft({ name });
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
  <Card><Heading>{item.name}</Heading><Pill label="Planned placement · no stock quantity" />
    {canConfigure ? <><Field label="Shelf name" value={name} onChangeText={setName} maxLength={120} editable={!pending} />
      <Button title="Save" variant="secondary" disabled={pending || !name.trim() || name.trim() === item.name} loading={task.pending}
        onPress={() => { void task.run(async () => { await api.editShelf(item, name.trim(), identity); await refresh(); }, resetDraft); }} />
      <Body muted>Draft kept on this device. Save to update this shelf.</Body></> : null}
    <Button title="Cancel" variant="quiet" disabled={pending} onPress={() => { resetDraft(); setConfirmedPlacements(null); task.setError(null); void refresh(); }} />
  </Card>
  <Columns>
  {canConfigure ? <Column><Card>
    <ShelfProductPicker shelfId={item.id} assigned={[...assigned]} disabled={pending} onAdd={id => place(id, true)} />
    {canEdit ? <Button title="Create a company product" variant="quiet" disabled={pending} onPress={() => router.push('/catalog/new')} /> : null}
  </Card></Column> : null}
  <Column><Heading>Assigned products</Heading>
    {!item.products.items.length ? <Body muted>No products assigned on this page.</Body> : null}
    <InventoryList>{item.products.items.map(product => <InventoryItem
      key={product.id}
      title={product.name}
      detail={product.containerAmount === null ? `Container size not set · ${units[product.baseUnit]}` : containerLabel(product)}
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
  </Column></Columns></>;
}
