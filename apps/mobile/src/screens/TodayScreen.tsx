import { Text } from '@/src/ui/Typography';
import React from 'react';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSession } from '@/src/session/SessionProvider';
import { Card, Pill, Screen, layout } from '@/src/ui/components';
import { colors, fonts, roleLabels } from '@/src/ui/theme';
import { HeadsUpCard } from '@/src/headsUp/HeadsUpCard';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';

export function TodayScreen() {
  const { actor, stores } = useSession();
  const router = useRouter();
  const can = (permission: string) => Boolean(actor?.capabilities.includes(permission));
  const reports = can('reports.view') || can('reports.submit');
  const showHeadsUp = actor?.role === 'crew' || actor?.role === 'manager' || actor?.role === 'production';
  const store = stores.find((item) => item.storeId === actor?.storeId);
  const firstName = (actor?.displayName || actor?.username || 'there').split(' ')[0];
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  return <Screen title={`${greeting},\n${firstName}.`} eyebrow={new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
    subtitle="A little clarity for the shift ahead.">
    {showHeadsUp ? <HeadsUpCard /> : null}
    <Card style={styles.storeCard}>
      <View style={layout.row}><Ionicons name="storefront-outline" size={25} color={colors.onPrimary} />
        <View style={layout.flex}><Text style={styles.storeLabel}>YOUR WORKSPACE</Text>
          <Text style={styles.storeName}>{store?.storeName || 'Current store'}</Text></View>
      </View>
      <View style={[layout.wrap, { alignItems: 'center', justifyContent: 'space-between' }]}>
        <Text style={styles.storeDescription}>{actor?.displayName || actor?.username}</Text>
        <Pill label={roleLabels[actor?.role || ''] || 'Team member'} />
      </View>
      {stores.length > 1 ? <Pressable accessibilityRole="button" accessibilityLabel="Change your store" onPress={() => router.push('/accounts')}
        style={({ pressed }) => [styles.storeSwitch, pressed && { opacity: 0.7 }]}>
        <Text style={styles.storeSwitchText}>Change store</Text><Ionicons name="swap-horizontal" size={20} color={colors.onPrimary} />
      </Pressable> : null}
    </Card>
    <ActionGrid>
      {reports ? <ActionTile title={can('reports.view') ? 'Read Shift Reports' : 'Write a Shift Report'}
        icon={can('reports.view') ? 'reader-outline' : 'create-outline'} onPress={() => router.push('/reports')} /> : null}
      {can('inventory.view') ? <ActionTile title="Visit Inventory" icon="cube-outline"
        onPress={() => router.push('/inventory')} /> : null}
      {can('production.view') ? <ActionTile title="Open Production" icon="restaurant-outline"
        onPress={() => router.push('/production')} /> : null}
      {can('memberships.manage') || actor?.role === 'manager' ? <ActionTile
        title={actor?.role === 'owner' ? 'Owner Workspace' : 'Manage Your Team'}
        label={can('memberships.manage') ? (actor?.role === 'owner' ? 'Owner Workspace' : 'Manage Your Team') : 'Manage Your Team. Team management permission required.'}
        icon="people-outline" disabled={!can('memberships.manage')}
        onPress={() => router.push(actor?.role === 'owner' ? '/owner' : '/team')} /> : null}
      <ActionTile title="Your Account" icon="person-circle-outline" onPress={() => router.push('/accounts')} />
    </ActionGrid>
  </Screen>;
}

const styles = StyleSheet.create({
  storeCard: { backgroundColor: colors.primary, borderColor: colors.primary, gap: 16 },
  storeLabel: { color: colors.onPrimaryMuted, fontSize: 11, letterSpacing: 1.5, fontWeight: '700', marginBottom: 7 },
  storeName: { color: colors.onPrimary, fontFamily: fonts.display, fontSize: 30, lineHeight: 34 },
  storeDescription: { color: colors.onPrimaryMuted, fontSize: 15, lineHeight: 23 },
  storeSwitch: { minHeight: 48, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10, paddingHorizontal: 16, borderRadius: 24, borderWidth: 1, borderColor: colors.onPrimaryMuted },
  storeSwitchText: { color: colors.onPrimary, fontSize: 15, fontWeight: '700' },
});
