import React, { useRef } from 'react';
import { useRouter } from 'expo-router';
import { Body, Button, Card, Heading, Notice, Screen } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { inventoryApi, MutationIdentity } from './api';

export function useInventory() {
  const session = useSession();
  const { request } = session;
  const api = React.useMemo(() => inventoryApi(request), [request]);
  const identity = useRef(new MutationIdentity()).current;
  return { ...session, api, identity, canEdit: !!session.actor?.capabilities.includes('catalog.manage'),
    canConfigure: !!session.actor?.capabilities.includes('configuration.manage') };
}
export function InventoryPage({ title, children }: React.PropsWithChildren<{ title: string }>) {
  const { actor, stores } = useSession(); const router = useRouter();
  const allowed = actor?.capabilities.includes('inventory.view');
  const name = stores.find(s => s.storeId === actor?.storeId)?.storeName || 'Current store';
  return <Screen title={title} eyebrow="Inventory" subtitle={name}>
    <Button title="Back to inventory" variant="quiet" icon="arrow-back" onPress={() => router.replace('/inventory')} />
    {allowed ? children : <Card><Heading>Access is limited</Heading><Body>Your account does not have inventory access at this store.</Body></Card>}
  </Screen>;
}
export { useLoaderResource as useInventoryResource } from '@/src/ui/useResource';
export function LoadError({ error, refresh }: { error: string | null; refresh: () => Promise<void> }) {
  return <Card><Notice message={error || 'This record is unavailable.'} kind="error" /><Button title="Reload" onPress={() => { void refresh(); }} /></Card>;
}
export function Pages({ next, setCursor, cursor }: { next: string | null; cursor: string; setCursor: (value: string) => void }) {
  return <>{next ? <Button title="Next page" variant="secondary" onPress={() => setCursor(next)} /> : null}
    {cursor ? <Button title="Back to first page" variant="quiet" onPress={() => setCursor('')} /> : null}</>;
}
