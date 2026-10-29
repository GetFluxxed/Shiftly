import React from 'react';
import { createRoot } from 'react-dom/client';
import { ExpoRoot } from 'expo-router/build/ExpoRoot';
import { Redirect, Stack, usePathname, useRouter } from 'expo-router';
import { Pressable, Text, View } from 'react-native';
import AppLayout from '../../app/(app)/_layout';
import { TodayScreen } from '../../src/screens/TodayScreen';
import { ReportsScreen } from '../../src/screens/ReportsScreen';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { WorkspaceNavigation, WorkspaceProvider } from '../../src/restoration/WorkspaceProvider';
import IndexScreen from '../../app/index';
import type { Transport } from '../../src/api/client';

const role = new URL(window.location.href).searchParams.get('role') || 'owner';
const capabilities = role === 'crew'
  ? ['reports.view', 'reports.submit', 'inventory.view']
  : role === 'production'
    ? ['production.view']
    : ['reports.view', 'reports.submit', 'inventory.view', 'production.view', 'memberships.manage', 'receipts.draft', 'receipts.post'];
const actor = { userId: 1, businessId: 1, storeId: 1, username: 'fixture', displayName: 'Fixture User', role, provenance: 'named' as const, capabilities };
const stores = [{ ...actor, storeName: 'Fixture Store' }];
const transport: Transport = { send: async <T,>(path: string) => {
  if (path === '/accounts/status') return { authenticated: true, actor, stores } as T;
  if (path === '/reports') {
    await new Promise(resolve => setTimeout(resolve, 100));
    return { reports: [] } as T;
  }
  throw new Error(`Unexpected fixture request: ${path}`);
} };
let token: string | null = 'router-fixture-token';
const controller = new SessionController(transport, {
  read: async () => token,
  write: async (value: string) => { token = value; },
  remove: async () => { token = null; },
});
const workspaceKey = `shiftly.router.workspace.${role}`;
const workspaceStorage = {
  read: async () => sessionStorage.getItem(workspaceKey),
  write: async (value: string) => { sessionStorage.setItem(workspaceKey, value); },
  remove: async () => { sessionStorage.removeItem(workspaceKey); },
};

function RootLayout() {
  React.useEffect(() => { void controller.restore(); }, []);
  return <SessionContext.Provider value={controller}>
    <WorkspaceProvider session={controller} storage={workspaceStorage}>
      <WorkspaceNavigation session={controller} />
      <Stack screenOptions={{ headerShown: false }} />
    </WorkspaceProvider>
  </SessionContext.Provider>;
}
function SectionLayout() { return <Stack screenOptions={{ headerShown: false }} />; }

const destinations = [
  ['Today', '/today'], ['Reports', '/reports'], ['Inventory', '/inventory'],
  ['Catalog', '/catalog'], ['Counts', '/counts'], ['Shelves', '/shelves'],
  ['Team', '/team'], ['Production', '/production'], ['Invoices', '/invoices'], ['Incoming', '/incoming'], ['Account', '/accounts'],
] as const;

function Destination() {
  const pathname = usePathname();
  const router = useRouter();
  return <View style={{ padding: 24, gap: 10 }}>
    <Text accessibilityRole="header">Route {pathname}</Text>
    {destinations.map(([label, href]) => <Pressable key={href} accessibilityRole="button"
      accessibilityLabel={`Go ${label}`} onPress={() => router.push(href)}>
      <Text>Go {label}</Text>
    </Pressable>)}
  </View>;
}

type RouteModule = { default: React.ComponentType };
const modules: Record<string, RouteModule> = {
  './_layout.tsx': { default: RootLayout },
  './index.tsx': { default: IndexScreen },
  './sign-in.tsx': { default: () => <Redirect href="/today" /> },
  './(app)/_layout.tsx': { default: AppLayout },
  './(app)/today.tsx': { default: TodayScreen },
  './(app)/reports.tsx': { default: ReportsScreen },
  './(app)/inventory.tsx': { default: Destination },
  './(app)/accounts.tsx': { default: Destination },
};
for (const section of ['catalog', 'counts', 'shelves', 'team', 'production', 'owner', 'stock', 'heads-up', 'invoices']) {
  modules[`./(app)/${section}/_layout.tsx`] = { default: SectionLayout };
  modules[`./(app)/${section}/index.tsx`] = { default: Destination };
}
modules['./(app)/store.tsx'] = { default: Destination };
modules['./(app)/incoming.tsx'] = { default: Destination };
const context = Object.assign((id: string) => modules[id], {
  resolve: (key: string) => key,
  id: 'shiftly-sdk58-router-regression',
  keys: () => Object.keys(modules),
});

createRoot(document.getElementById('root')!).render(<ExpoRoot context={context} location={window.location.href} />);
