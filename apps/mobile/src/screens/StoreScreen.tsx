import React from 'react';
import { useRouter } from 'expo-router';
import { canViewStore } from '@/src/accounts/navigation';
import { useSession } from '@/src/session/SessionProvider';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { Body, Button, Card, Column, Columns, Heading, Notice, Screen } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';

export function StoreScreen() {
  const { actor, stores } = useSession();
  const router = useRouter();
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
        icon="person-add-outline" disabled={!canManageMemberships} onPress={() => router.push('/team/build')} />
      <ActionTile title="Team members" label={canManageMemberships ? 'Team members' : 'Team members. Permission required.'}
        icon="people-outline" disabled={!canManageMemberships} onPress={() => router.push('/team')} />
      {actor?.role === 'manager' ? <ActionTile title="Heads Up" label="Heads Up" icon="megaphone-outline"
        onPress={() => router.push('/heads-up')} />
        : <ActionTile title="Store access" label="Store access" icon="key-outline"
          onPress={() => router.push('/team/access')} />}
      <ActionTile title="Owner tools" label={isOwner ? 'Owner tools' : 'Owner tools. Owner only.'}
        icon="shield-checkmark-outline" disabled={!isOwner} onPress={() => router.push('/owner')}
        footer={!isOwner ? <Text style={{ color: colors.muted, fontSize: 13, lineHeight: 18, paddingHorizontal: 12, paddingBottom: 12 }}>Owner only</Text> : undefined} />
    </ActionGrid>
    {!canManageMemberships ? <Notice message="Team management permission is required to build or view the team." /> : null}
  </Screen>;
}

export function StoreAccessScreen() {
  const { actor, stores } = useSession();
  const router = useRouter();
  const storeName = stores.find(store => store.storeId === actor?.storeId)?.storeName || 'Current store';
  if (!canViewStore(actor?.role)) {
    return <Screen title="Store access" eyebrow="Team & access" subtitle={storeName}>
      <Button title="Back to store" icon="arrow-back" variant="quiet" onPress={() => router.replace('/store')} />
      <Card><Heading>Access is limited</Heading><Body>Store access information is available to store managers and business owners.</Body></Card>
    </Screen>;
  }
  return <Screen title="Store access" eyebrow="Team & access" subtitle={storeName}>
    <Button title="Back to store" icon="arrow-back" variant="quiet" onPress={() => router.replace('/store')} />
    <Columns>
    <Column><Card><Heading>Invitation only</Heading><Body>Join {storeName} with a private, single-use invitation. Staff cannot sign up publicly.</Body></Card></Column>
    <Column><Card><Heading>One store for staff</Heading><Body>Crew and managers have one active store. An administrator must remove the old store before a transfer.</Body></Card></Column>
    <Column><Card><Heading>Permission changes</Heading><Body>Only administrators and owners can change roles, permissions, or store access.</Body></Card></Column>
    </Columns>
  </Screen>;
}
