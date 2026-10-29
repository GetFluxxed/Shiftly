import React from 'react';
import { Redirect, Tabs } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Alert, useWindowDimensions } from 'react-native';
import { useSession } from '@/src/session/SessionProvider';
import { Button, Card, Loading, Notice, Screen } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { canViewStore } from '@/src/accounts/navigation';
import { useWorkspace } from '@/src/restoration/WorkspaceProvider';
import { OfflineInventoryWorkspace } from '@/src/inventory/OfflineInventoryWorkspace';
import { workspaceScope } from '@/src/restoration/policy';

// These sections are reached from workspace buttons. SDK 58 treats href:null
// as an unavailable route and redirects it to Today; hide only their tab items.
const detailTabOptions = {
  tabBarButton: () => null,
  tabBarItemStyle: { display: 'none' as const },
};

export default function AppLayout() {
  const { status, actor, message, retry, signOut, busy, revision, stores, offlineCountId, offlineCatalogCapture } = useSession();
  const workspace = useWorkspace();
  const { width, fontScale } = useWindowDimensions();
  if (status === 'loading') return <Loading />;
  if (status === 'signedOut') return <Redirect href="/sign-in" />;
  if (status === 'locked' || !actor || status === 'offline' && !offlineCountId && !offlineCatalogCapture) return <Screen title="Reconnect to Shiftly" eyebrow="Access paused"
    subtitle="Confirm your account access to continue.">
    <Card><Notice message={message || 'Your connection is unavailable.'} />
      <Button title="Try again" onPress={() => { void retry(); }} loading={busy} />
      <Button title="Sign out" variant="quiet" onPress={() => Alert.alert('Sign out of this device?', undefined, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign out', style: 'destructive', onPress: () => { void signOut(); } },
      ])} disabled={busy} />
    </Card></Screen>;
  if (workspace.controller && (!workspace.ready || workspace.scope !== workspaceScope(actor, stores))) return <Loading label="Restoring your workspace…" />;
  if (status === 'offline') return <OfflineInventoryWorkspace key={`${actor.userId}:${actor.businessId}:${actor.storeId}`} />;
  const canReport = actor.capabilities.some((item) => item === 'reports.submit' || item === 'reports.view');
  const hasInventory = actor.capabilities.includes('inventory.view');
  const hasProduction = actor.capabilities.includes('production.view');
  const canReceive = ['manager', 'owner'].includes(actor.role)
    && ['inventory.view', 'receipts.draft', 'receipts.post'].every(permission => actor.capabilities.includes(permission));
  return <Tabs key={`${revision}:${actor.userId}:${actor.storeId}:${actor.capabilities.join(',')}`}
    screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: colors.paper },
      tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted,
      tabBarHideOnKeyboard: true,
      tabBarPosition: width >= 1000 && fontScale < 1.5 ? 'left' : 'bottom',
      tabBarLabel: ({ children, color }) => <Text style={{ color, fontSize: 12, fontWeight: '600' }}>{children}</Text>,
      tabBarActiveBackgroundColor: colors.blush,
      tabBarStyle: { backgroundColor: colors.card, borderColor: colors.line },
      tabBarItemStyle: { minHeight: 54, borderRadius: 16, marginHorizontal: 3, marginTop: 5, marginBottom: 3 },
    }}>
    <Tabs.Screen name="today" options={{ title: 'Today', href: '/today',
      tabBarIcon: ({ focused, size }) => <Ionicons name="sunny-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="reports" options={{ title: 'Reports', href: canReport ? '/reports' : null,
      tabBarIcon: ({ focused, size }) => <Ionicons name="reader-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="inventory" options={{ title: 'Inventory', href: hasInventory ? '/inventory' : null,
      tabBarIcon: ({ focused, size }) => <Ionicons name="cube-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="production" options={{ title: 'Production',
      ...(hasProduction ? actor.role === 'production' ? { href: '/production' as const } : detailTabOptions : { href: null }),
      tabBarIcon: ({ focused, size }) => <Ionicons name="restaurant-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="store" options={{ title: 'Store', href: canViewStore(actor.role) ? '/store' : null,
      tabBarIcon: ({ focused, size }) => <Ionicons name="storefront-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="accounts" options={{ title: 'Account', href: '/accounts',
      tabBarIcon: ({ focused, size }) => <Ionicons name="person-circle-outline" color={focused ? colors.primary : colors.muted} size={size} /> }} />
    <Tabs.Screen name="team" options={detailTabOptions} />
    <Tabs.Screen name="owner" options={detailTabOptions} />
    <Tabs.Screen name="time-tracking" options={actor.role === 'owner' ? detailTabOptions : { href: null }} />
    <Tabs.Screen name="catalog" options={detailTabOptions} />
    <Tabs.Screen name="shelves" options={detailTabOptions} />
    <Tabs.Screen name="counts" options={detailTabOptions} />
    <Tabs.Screen name="stock" options={detailTabOptions} />
    <Tabs.Screen name="heads-up" options={detailTabOptions} />
    <Tabs.Screen name="invoices" options={canReceive ? detailTabOptions : { href: null }} />
    <Tabs.Screen name="incoming" options={canReceive ? detailTabOptions : { href: null }} />
  </Tabs>;
}
