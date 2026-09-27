// Actual native account screens/controller against the real test API. Navigation
// and device storage are the only platform adapters in this browser renderer.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SignInScreen, ActivateScreen } from '../../src/screens/AuthScreens';
import { InviteScreen, TeamScreen, MemberScreen, BuildTeamScreen, AssignScreen } from '../../src/accounts/TeamScreens';
import { StoreScreen, StoreAccessScreen } from '../../src/screens/StoreScreen';
import AppLayout from '../../app/(app)/_layout';
import { AccountsScreen } from '../../src/screens/AccountsScreen';
import { OwnerScreen } from '../../src/accounts/OwnerScreens';
import { createTransport } from '../../src/api/client';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { RouterContext } from './router';
const testWindow=window as Window & {__testToken?:string};
let token:string|null=testWindow.__testToken||null;
const controller=new SessionController(createTransport(location.origin),{read:async()=>token,write:async v=>{token=v;},remove:async()=>{token=null;}});
declare global { interface Window { __accountsTest: SessionController } }
window.__accountsTest=controller;
const subscribe=AppState.addEventListener.bind(AppState);
AppState.addEventListener=(event,listener)=>event==='change'?subscribe(event,listener):{remove(){}};
Alert.alert=(_title,message,buttons)=>{if(confirm(message))buttons?.at(-1)?.onPress?.();};
function App(){
 const snapshot=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
 type Route = {path:string;params:Record<string,string>};
 const [navigation,setNavigation]=React.useState({route:{path:location.pathname,params:{'#':location.hash.slice(1)}} as Route,history:[] as Route[]});
 const {route}=navigation;
 React.useEffect(()=>{void controller.restore();},[]);
 const destination=(value:unknown):Route=>typeof value==='string'?{path:value,params:{}}:
   {path:(value as {pathname:string}).pathname,params:(value as {params:Record<string,string>}).params};
 const go=React.useCallback((value:unknown)=>{
  setNavigation(current=>({route:destination(value),history:[...current.history,current.route]}));
 },[]);
 const replace=React.useCallback((value:unknown)=>{
  setNavigation(current=>({...current,route:destination(value)}));
 },[]);
 const back=React.useCallback(()=>setNavigation(current=>current.history.length?
   {route:current.history.at(-1)!,history:current.history.slice(0,-1)}:current),[]);
 const setParams=React.useCallback((values:Record<string,string>)=>{
  setNavigation(current=>({...current,route:{...current.route,params:{...current.route.params,...values}}}));history.replaceState(null,'',location.pathname);
 },[]);
 const context=React.useMemo(()=>({go,replace,back,canGoBack:()=>navigation.history.length>0,params:route.params,setParams}),[go,replace,back,navigation.history,route.params,setParams]);
 const Home=()=> <div>Signed in as {snapshot.actor?.username} at store {snapshot.actor?.storeId}</div>;
 const Screen=({'/sign-in':SignInScreen,'/activate':ActivateScreen,'/team/invite':InviteScreen,'/team':TeamScreen,
  '/team/[userId]':MemberScreen,'/team/assign':AssignScreen,'/team/build':BuildTeamScreen,
  '/team/access':StoreAccessScreen,'/owner':OwnerScreen,'/store':StoreScreen,'/accounts':AccountsScreen,'/today':Home} as Record<string,React.ComponentType>)[route.path]||Home;
 const publicRoute=['/sign-in','/activate'].includes(route.path);
 return <SessionContext.Provider value={controller}><SafeAreaProvider><RouterContext.Provider value={context}>
   {!publicRoute ? <AppLayout/> : null}
   {publicRoute || snapshot.status==='ready' ? <Screen key={publicRoute ? route.path : `${route.path}:${JSON.stringify(route.params)}:${snapshot.revision}`}/> : null}
 </RouterContext.Provider></SafeAreaProvider></SessionContext.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
