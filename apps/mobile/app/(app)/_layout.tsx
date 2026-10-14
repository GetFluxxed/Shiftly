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
import { workspaceScope } from '@/src/restoration/policy';

export default function AppLayout() {
  const { status, actor, message, retry, signOut, busy, revision, stores } = useSession();
  const workspace = useWorkspace();
  const { width, fontScale } = useWindowDimensions();
  if (status === 'loading') return <Loading />;
  if (status === 'signedOut') return <Redirect href="/sign-in" />;
  if (status === 'locked' || !actor) return <Screen title="Reconnect to Shiftly" eyebrow="Access paused"
    subtitle="Confirm your account access to continue.">
    <Card><Notice message={message || 'Your connection is unavailable.'} />
      <Button title="Try again" onPress={() => { void retry(); }} loading={busy} />
      <Button title="Sign out" variant="quiet" onPress={() => Alert.alert('Sign out of this device?', undefined, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign out', style: 'destructive', onPress: () => { void signOut(); } },
      ])} disabled={busy} />
    </Card></Screen>;
  if (workspace.controller && (!workspace.ready || workspace.scope !== workspaceScope(actor, stores))) return <Loading label="Restoring your workspace…" />;
  const canReport = actor.capabilities.some((item) => item === 'reports.submit' || item === 'reports.view');
  const hasInventory = actor.capabilities.includes('inventory.view');
  const hasProduction = actor.capabilities.includes('production.view');
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
      tabBarIcon: ({ color, size }) => <Ionicons name="sunny-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="reports" options={{ title: 'Reports', href: canReport ? '/reports' : null,
      tabBarIcon: ({ color, size }) => <Ionicons name="reader-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="inventory" options={{ title: 'Inventory', href: hasInventory ? '/inventory' : null,
      tabBarIcon: ({ color, size }) => <Ionicons name="cube-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="production" options={{ title: 'Production', href: hasProduction && actor.role === 'production' ? '/production' : null,
      tabBarIcon: ({ color, size }) => <Ionicons name="restaurant-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="store" options={{ title: 'Store', href: canViewStore(actor.role) ? '/store' : null,
      tabBarIcon: ({ color, size }) => <Ionicons name="storefront-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="accounts" options={{ title: 'Account', href: '/accounts',
      tabBarIcon: ({ color, size }) => <Ionicons name="person-circle-outline" color={color} size={size} /> }} />
    <Tabs.Screen name="team" options={{ href: null }} />
    <Tabs.Screen name="owner" options={{ href: null }} />
    <Tabs.Screen name="catalog" options={{ href: null }} />
    <Tabs.Screen name="shelves" options={{ href: null }} />
    <Tabs.Screen name="counts" options={{ href: null }} />
    <Tabs.Screen name="stock" options={{ href: null }} />
    <Tabs.Screen name="heads-up" options={{ href: null }} />
  </Tabs>;
}
