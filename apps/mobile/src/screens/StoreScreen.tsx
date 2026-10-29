import { usePageBack } from '@/src/navigation/usePageBack';
import React from 'react';
import { useAppNavigation } from '@/src/navigation/useAppNavigation';
import { canViewStore } from '@/src/accounts/navigation';
import { useSession } from '@/src/session/SessionProvider';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { Body, Button, Card, Column, Columns, Heading, Notice, Screen } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';

export function StoreScreen() {
  const { actor, stores } = useSession();
  const nav = useAppNavigation();
  const storeName = stores.find(store => store.storeId === actor?.storeId)?.storeName || 'Your store';
  const isStoreManager = canViewStore(actor?.role);
  const canManageMemberships = Boolean(actor?.capabilities.includes('memberships.manage'));
  const isOwner = actor?.role === 'owner';

  if (!isStoreManager) {
    return <Screen title="Store" eyebrow={storeName}>
      <Notice message="Store management is available to store managers and business owners." />
    </Screen>;
  }

  return <Screen title="Store" eyebrow={storeName}>
    <ActionGrid>
      <ActionTile title="Build team" label={canManageMemberships ? 'Build team' : 'Build team. Permission required.'}
        icon="person-add-outline" disabled={!canManageMemberships} onPress={() => nav.open('/team/build')} />
      <ActionTile title="Team members" label={canManageMemberships ? 'Team members' : 'Team members. Permission required.'}
        icon="people-outline" disabled={!canManageMemberships} onPress={() => nav.open('/team')} />
      {actor?.role === 'manager' ? <ActionTile title="Heads Up" label="Heads Up" icon="megaphone-outline"
        onPress={() => nav.open('/heads-up')} />
        : <ActionTile title="Store access" label="Store access" icon="key-outline"
          onPress={() => nav.open('/team/access')} />}
      <ActionTile title="Owner tools" label={isOwner ? 'Owner tools' : 'Owner tools. Owner only.'}
        icon="shield-checkmark-outline" disabled={!isOwner} onPress={() => nav.open('/owner')}
        footer={!isOwner ? <Text style={{ color: colors.muted, fontSize: 13, lineHeight: 18, paddingHorizontal: 12, paddingBottom: 12 }}>Owner only</Text> : undefined} />
    </ActionGrid>
    {!canManageMemberships ? <Notice message="Team management permission is required to build or view the team." /> : null}
  </Screen>;
}

export function StoreAccessScreen() {
  const { actor, stores } = useSession();
  const nav = useAppNavigation();
  const backTo = canViewStore(actor?.role) ? '/store' : '/today';
  usePageBack(() => nav.back(backTo));
  const storeName = stores.find(store => store.storeId === actor?.storeId)?.storeName || 'Current store';
  if (!canViewStore(actor?.role)) {
    return <Screen title="Store access" eyebrow="Team & access" subtitle={storeName}>
      <Button title={nav.parent(backTo).label} icon="arrow-back" variant="quiet" onPress={() => nav.back(backTo)} />
      <Card><Heading>Access is limited</Heading><Body>Store access information is available to store managers and business owners.</Body></Card>
    </Screen>;
  }
  return <Screen title="Store access" eyebrow="Team & access" subtitle={storeName}>
    <Button title={nav.parent(backTo).label} icon="arrow-back" variant="quiet" onPress={() => nav.back(backTo)} />
    <Columns>
    <Column><Card><Heading>Invitation only</Heading><Body>Join {storeName} with a private, single-use invitation. Staff cannot sign up publicly.</Body></Card></Column>
    <Column><Card><Heading>One store for staff</Heading><Body>Crew and managers have one active store. An administrator must remove the old store before a transfer.</Body></Card></Column>
    <Column><Card><Heading>Permission changes</Heading><Body>Only administrators and owners can change roles, permissions, or store access.</Body></Card></Column>
    </Columns>
  </Screen>;
}
