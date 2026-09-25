// Test-only renderer: real screens/hooks/controller/transport, memory credentials,
// minimal navigation, and native primitives rendered by react-native-web.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { InventoryScreen } from '../../src/screens/InventoryScreen';
import { CatalogScreen, NewProductScreen, ProductScreen } from '../../src/inventory/CatalogScreens';
import { ShelvesScreen, ShelfScreen } from '../../src/inventory/ShelfScreens';
import { createTransport } from '../../src/api/client';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { RouterContext } from './router';

declare global { interface Window { __testToken: string; __inventoryTest: SessionController } }
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
 const [route,setRoute]=React.useState({path:'/inventory',params:{} as Record<string,string>});
 React.useEffect(()=>{void controller.restore();},[]);
 const go=React.useCallback((value:unknown)=>{
   if(typeof value==='string') setRoute({path:value,params:{}});
   else {const r=value as {pathname:string;params:Record<string,string>};setRoute({path:r.pathname,params:r.params});}
 },[]);
 const ctx=React.useMemo(()=>({go,params:route.params,setParams:()=>{}}),[go,route.params]);
 if(snapshot.status!=='ready') return <div>Workspace {snapshot.status}</div>;
 const Screen=({'/inventory':InventoryScreen,'/catalog':CatalogScreen,'/catalog/new':NewProductScreen,
   '/catalog/[productId]':ProductScreen,'/shelves':ShelvesScreen,'/shelves/[shelfId]':ShelfScreen} as Record<string,React.ComponentType>)[route.path]!;
 return <SessionContext.Provider value={controller}><SafeAreaProvider><RouterContext.Provider value={ctx}>
   <Screen key={`${route.path}:${JSON.stringify(route.params)}:${snapshot.revision}`} />
 </RouterContext.Provider></SafeAreaProvider></SessionContext.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
