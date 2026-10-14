// Test-only renderer: real screens/hooks/controller/transport, memory credentials,
// minimal navigation, and native primitives rendered by react-native-web.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { InventoryScreen } from '../../src/screens/InventoryScreen';
import { ReportsScreen } from '../../src/screens/ReportsScreen';
import { CatalogScreen, NewProductScreen, ProductScreen } from '../../src/inventory/CatalogScreens';
import { CatalogScanScreen } from '../../src/inventory/CatalogScanScreen';
import { StockScreen, StockDetailScreen } from '../../src/inventory/counts/StockScreens';
import { CountsScreen, CountSessionScreen, CountReviewScreen, CountHistoryScreen } from '../../src/inventory/counts/CountScreens';
import { CountEntryScreen } from '../../src/inventory/counts/CountEntryScreen';
import { ShelvesScreen, ShelfScreen } from '../../src/inventory/ShelfScreens';
import { PackagesScreen } from '../../src/inventory/PackageScreens';
import { NewRecipeScreen, RecipeScreen, RecipesScreen } from '../../src/production/RecipeScreens';
import { ProductionLogScreen, ProductionLogsScreen, ProductionReviewScreen, ProductionRunScreen, ProductionScreen } from '../../src/production/ProductionScreens';
import { createTransport } from '../../src/api/client';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { RouterContext, destination } from './router';
import { WorkspaceProvider, WorkspaceNavigation } from '../../src/restoration/WorkspaceProvider';
import { WorkspaceGate, workspaceStorage } from './workspace';
import { cameraBoundary } from './camera-module';

const catalogCamera = {
  allow: () => {
    Object.defineProperty(AppState, 'currentState', { configurable: true, get: () => 'active' });
    cameraBoundary.setPermission({ granted: true, canAskAgain: true });
  },
  ready: cameraBoundary.ready,
  scan: cameraBoundary.scan,
  staleScan: cameraBoundary.staleScan,
};
declare global { interface Window {
  __testToken: string; __inventoryTest: SessionController; __catalogCameraTest: typeof catalogCamera;
} }
window.__catalogCameraTest = catalogCamera;
// Android focus/blur events have no browser implementation. State changes and
// workspace invalidation remain exercised through the actual controller.
const subscribe = AppState.addEventListener.bind(AppState);
AppState.addEventListener = (event, listener) => event === 'change' ? subscribe(event, listener) : { remove() {} };
let token: string | null=window.__testToken;
const controller=new SessionController(createTransport(location.origin),{read:async()=>token,write:async value=>{token=value;},remove:async()=>{token=null;}});
window.__inventoryTest=controller;
// React Native Web does not implement the native Alert dialog. Use a browser
// confirmation so the actual screen's confirmation callback is exercised.
Alert.alert=(_title,message,buttons)=>{ if(window.confirm(message)) buttons?.at(-1)?.onPress?.(); };
function App() {
 const snapshot=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
 const [route,setRoute]=React.useState(() => destination(location.pathname === '/' ? '/today' : location.pathname));
 React.useEffect(()=>{void controller.restore();},[]);
 const go=React.useCallback((value:unknown)=>{
   setRoute(destination(value));
 },[]);
 const ctx=React.useMemo(()=>({go,path:route.path,params:route.params,setParams:()=>{}}),[go,route]);
 const Screen=({'/today':InventoryScreen,'/reports':ReportsScreen,'/inventory':InventoryScreen,'/catalog':CatalogScreen,'/catalog/new':NewProductScreen,'/catalog/scan':CatalogScanScreen,
   '/stock':StockScreen,'/stock/[productId]':StockDetailScreen,'/counts':CountsScreen,
   '/counts/[countId]':CountSessionScreen,'/counts/[countId]/review':CountReviewScreen,'/counts/history':CountHistoryScreen,
   '/counts/[countId]/line/[lineId]':CountEntryScreen,'/catalog/[productId]':ProductScreen,'/catalog/packages/[productId]':PackagesScreen,'/shelves':ShelvesScreen,'/shelves/[shelfId]':ShelfScreen,
   '/production':ProductionScreen,'/production/run':ProductionRunScreen,'/production/review':ProductionReviewScreen,
   '/production/recipes':RecipesScreen,'/production/recipes/new':NewRecipeScreen,'/production/recipes/[recipeId]':RecipeScreen,
   '/production/logs':ProductionLogsScreen,'/production/logs/[logId]':ProductionLogScreen} as Record<string,React.ComponentType>)[route.path]!;
 return <SessionContext.Provider value={controller}><WorkspaceProvider session={controller} storage={workspaceStorage}><SafeAreaProvider><RouterContext.Provider value={ctx}>
   <WorkspaceNavigation session={controller}/><WorkspaceGate session={controller}><Screen key={`${route.path}:${JSON.stringify(route.params)}:${snapshot.revision}`} /></WorkspaceGate>
 </RouterContext.Provider></SafeAreaProvider></WorkspaceProvider></SessionContext.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
