import React from 'react';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Card, EmptyState, Notice, Pill, Screen } from '@/src/ui/components';

export function InventoryScreen() {
  const { actor, stores } = useSession();
  const store = stores.find((item) => item.storeId === actor?.storeId);
  if (!actor?.capabilities.includes('inventory.view')) return <Screen title="Inventory">
    <Notice message="Your current account does not have inventory access for this store." />
  </Screen>;
  return <Screen title="A place for every product." eyebrow={store?.storeName || 'Inventory'}
    subtitle="Inventory will bring your products, stock, and deliveries together.">
    <Card><Pill label="Coming next" /><EmptyState icon="cube-outline" title="Your inventory workspace"
      description="Stock tracking is being built. No product catalog, stock counts, or delivery records are available in this release." />
      <Body muted>Your inventory access is ready for this store. Product creation and stock tools will arrive with the inventory module.</Body>
    </Card>
  </Screen>;
}
