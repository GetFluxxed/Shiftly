import React from 'react';
import { createRoot } from 'react-dom/client';
import { ExpoRoot } from 'expo-router/build/ExpoRoot';
import { Stack } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppState } from 'react-native';
import { useFonts } from 'expo-font';
import { WorkSans_400Regular } from '@expo-google-fonts/work-sans/400Regular';
import { WorkSans_600SemiBold } from '@expo-google-fonts/work-sans/600SemiBold';
import { Newsreader_500Medium } from '@expo-google-fonts/newsreader/500Medium';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { WorkspaceNavigation, WorkspaceProvider } from '../../src/restoration/WorkspaceProvider';
import { FontsReadyContext } from '../../src/ui/Typography';
import { modules as appModules, routeKeys } from 'virtual:shiftly-routes';
import { SavedScansProvider } from '../../src/inventory/scans/SavedScansProvider';
import { savedScansStorage } from './saved-scans';
import { OfflineCountsProvider } from '../../src/inventory/counts/OfflineCountsProvider';
import { createOfflineCountStorage } from '../../src/inventory/counts/offline/storage';
import { createNavigationFixture } from './navigation-full-fixtures';

const subscribe = AppState.addEventListener.bind(AppState);
AppState.addEventListener = (event, listener) => event === 'change' ? subscribe(event, listener) : { remove() {} };

const initialUrl = new URL(location.href);
const role = initialUrl.searchParams.get('role') || 'owner';
const signedOut = initialUrl.searchParams.get('auth') === 'signedout';
const fixture = createNavigationFixture({ role: role as 'owner'|'admin'|'manager'|'production'|'crew', signedOut });
const { actor, stores } = fixture;
if (initialUrl.searchParams.get('reports') === 'submit-only') actor.capabilities = ['reports.submit'];
const transport = { send: fixture.send };
let token: string | null = signedOut ? null : 'full-navigation-fixture';
const controller = new SessionController(transport, { read: async () => token, write: async value => { token = value; }, remove: async () => { token = null; } });
const storage = { read: async () => sessionStorage.getItem('full-navigation.workspace'), write: async (value: string) => { sessionStorage.setItem('full-navigation.workspace', value); }, remove: async () => { sessionStorage.removeItem('full-navigation.workspace'); } };
const countStorage = createOfflineCountStorage({ get: async key => localStorage.getItem(key), set: async (key, value) => { localStorage.setItem(key, value); }, remove: async key => { localStorage.removeItem(key); } }, 'full-navigation.counts');

function RootLayout() {
  const [fontsReady] = useFonts({ WorkSans_400Regular, WorkSans_600SemiBold, Newsreader_500Medium });
  React.useEffect(() => { void controller.restore(); }, []);
  return <FontsReadyContext.Provider value={fontsReady}><SafeAreaProvider><SessionContext.Provider value={controller}>
    <SavedScansProvider session={controller} storage={savedScansStorage}><OfflineCountsProvider session={controller} storage={countStorage}>
      <WorkspaceProvider session={controller} storage={storage}><WorkspaceNavigation session={controller}/><Stack screenOptions={{headerShown:false}}/></WorkspaceProvider>
    </OfflineCountsProvider></SavedScansProvider>
  </SessionContext.Provider></SafeAreaProvider></FontsReadyContext.Provider>;
}
const modules = { ...appModules, './_layout.tsx': { default: RootLayout } };
const context = Object.assign((id: string) => modules[id as keyof typeof modules], { resolve: (key: string) => key, id: 'shiftly-full-navigation', keys: () => Object.keys(modules) });
declare global { interface Window { __shiftlyRouteKeys: string[]; __unexpectedFixtureRequests: string[] } }
window.__shiftlyRouteKeys = routeKeys;
window.__unexpectedFixtureRequests = fixture.unexpectedRequests;
createRoot(document.getElementById('root')!).render(<ExpoRoot context={context} location={location.href}/>);
