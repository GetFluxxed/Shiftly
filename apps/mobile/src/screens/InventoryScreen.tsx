import React from 'react';
import { useRouter } from 'expo-router';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, Heading, Notice, Screen } from '@/src/ui/components';

export function InventoryScreen() {
  const { actor, stores } = useSession(); const router = useRouter();
  const store = stores.find(item => item.storeId === actor?.storeId);
  if (!actor?.capabilities.includes('inventory.view')) return <Screen title="Inventory"><Notice message="Your current account does not have inventory access for this store." /></Screen>;
  return <Screen title="A place for every product." eyebrow={store?.storeName || 'Inventory'} subtitle="One company catalog. Shelves arranged for your store.">
    <Columns><Column><Card><Heading>Company catalog</Heading><Body>Find products and SKUs shared by your stores. Authorized catalog managers can add, edit, archive and restore products.</Body>
      <Button title="Open company catalog" icon="cube-outline" onPress={() => router.push('/catalog')} /></Card></Column>
    <Column><Card><Heading>Your store's shelves</Heading><Body>Create a named shelf and assign products from the catalog. Each store keeps its own arrangement.</Body>
      <Button title="Open shelves" icon="albums-outline" onPress={() => router.push('/shelves')} /></Card></Column></Columns>
    <Notice message="Shelf placement describes where a product belongs. Quantities, receiving and photo-assisted counts will follow separately." />
  </Screen>;
}
