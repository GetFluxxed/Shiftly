import React from 'react';
import { useRouter } from 'expo-router';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Heading, Screen } from '@/src/ui/components';
import { productionApi } from './api';

export function useProduction() {
  const session = useSession();
  const api = React.useMemo(() => productionApi(session.request), [session.request]);
  return { ...session, api, canManageRecipes: !!session.actor?.capabilities.includes('recipes.manage'), canSubmit: !!session.actor?.capabilities.includes('production.submit'), canManage: !!session.actor?.capabilities.includes('production.manage') };
}
export function ProductionPage({ title, children, backTo = '/production' }: React.PropsWithChildren<{ title: string; backTo?: '/production' | '/production/recipes' | '/production/logs' }>) {
  const { actor, stores } = useSession(); const router = useRouter();
  const allowed = !!actor?.capabilities.includes('production.view');
  const store = stores.find(s => s.storeId === actor?.storeId)?.storeName || 'Current store';
  return <Screen title={title} eyebrow="Production" subtitle={store} compact>
    {backTo !== '/production' || title !== 'Production' ? <Button title="Back to production" variant="quiet" icon="arrow-back" onPress={() => router.replace(backTo)} /> : null}
    {allowed ? children : <Card><Heading>Access is limited</Heading><Body>Your account does not have production access at this store.</Body></Card>}
  </Screen>;
}
