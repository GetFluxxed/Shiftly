import React from 'react';
import { useRouter } from 'expo-router';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Column, Columns, Heading, Notice, Screen } from '@/src/ui/components';

export function InventoryScreen() {
  const { actor, stores } = useSession(); const router = useRouter();
  const store = stores.find(item => item.storeId === actor?.storeId);
  if (!actor?.capabilities.includes('inventory.view')) return <Screen title="Inventory"><Notice message="Your current account does not have inventory access for this store." /></Screen>;
  return <Screen title="Your store, in stock." eyebrow={store?.storeName || 'Inventory'} subtitle="Current inventory, saved counts and a shared company catalog.">
    <Columns><Column><Card><Heading>Current inventory</Heading><Body>See each product’s last finalized quantity and shelf breakdown.</Body>
      <Button title="View current inventory" icon="stats-chart-outline" onPress={() => router.push('/stock')} /></Card></Column>
      <Column><Card><Heading>Count inventory</Heading><Body>Count shelf by shelf, resume saved entries and review changes before updating stock.</Body>
      <Button title="Count inventory" icon="clipboard-outline" onPress={() => router.push('/counts')} />
      <Button title="Count history" variant="secondary" onPress={() => router.push('/counts/history')} /></Card></Column></Columns>
    <Columns><Column><Card><Heading>Company catalog</Heading><Body>Find products and SKUs shared by your stores. Authorized catalog managers can add, edit, archive and restore products.</Body>
      <Button title="Open company catalog" icon="cube-outline" onPress={() => router.push('/catalog')} /></Card></Column>
    <Column><Card><Heading>Your store's shelves</Heading><Body>Create a named shelf and assign products from the catalog. Each store keeps its own arrangement.</Body>
      <Button title="Open shelves" icon="albums-outline" onPress={() => router.push('/shelves')} /></Card></Column></Columns>
    <Notice message="Current quantities come from finalized physical counts. Receiving, waste, transfers and photo-assisted counting will follow separately." />
  </Screen>;
}
