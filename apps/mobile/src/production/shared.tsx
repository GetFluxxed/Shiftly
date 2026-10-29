import React from 'react';
import type { Href } from 'expo-router';
import { useSession } from '@/src/session/SessionProvider';
import { Body, Button, Card, Heading, Screen } from '@/src/ui/components';
import { productionApi } from './api';
import { useAppNavigation } from '@/src/navigation/useAppNavigation';
import { usePageBack } from '@/src/navigation/usePageBack';

export function useProduction() {
  const session = useSession();
  const api = React.useMemo(() => productionApi(session.request), [session.request]);
  return { ...session, api, canManageRecipes: !!session.actor?.capabilities.includes('recipes.manage'), canSubmit: !!session.actor?.capabilities.includes('production.submit'), canManage: !!session.actor?.capabilities.includes('production.manage') };
}
export function ProductionPage({ title, children, backTo = '/production', backDisabled = false }: React.PropsWithChildren<{
  title: string; backTo?: Href; backDisabled?: boolean;
}>) {
  const { actor, stores } = useSession(); const navigation = useAppNavigation();
  const allowed = !!actor?.capabilities.includes('production.view');
  const store = stores.find(s => s.storeId === actor?.storeId)?.storeName || 'Current store';
  const parent = navigation.parent(backTo);
  const back = () => { if (!backDisabled) navigation.back(backTo); };
  usePageBack(back);
  return <Screen title={title} eyebrow="Production" subtitle={store} compact>
    <Button title={parent.label} variant="quiet" icon="arrow-back" disabled={backDisabled} onPress={back} />
    {allowed ? children : <Card><Heading>Access is limited</Heading><Body>Your account does not have production access at this store.</Body></Card>}
  </Screen>;
}
