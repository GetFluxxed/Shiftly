// Actual native account screens/controller against the real test API. Navigation
// and device storage are the only platform adapters in this browser renderer.
import React from 'react';
import { createRoot } from 'react-dom/client';
import { Alert, AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SignInScreen, ActivateScreen } from '../../src/screens/AuthScreens';
import { InviteScreen, TeamScreen, MemberScreen } from '../../src/accounts/TeamScreens';
import { AccountsScreen } from '../../src/screens/AccountsScreen';
import { createTransport } from '../../src/api/client';
import { SessionController } from '../../src/session/controller';
import { SessionContext } from './session';
import { RouterContext } from './router';
const testWindow=window as Window & {__testToken?:string};
let token:string|null=testWindow.__testToken||null;
const controller=new SessionController(createTransport(location.origin),{read:async()=>token,write:async v=>{token=v;},remove:async()=>{token=null;}});
const subscribe=AppState.addEventListener.bind(AppState);
AppState.addEventListener=(event,listener)=>event==='change'?subscribe(event,listener):{remove(){}};
Alert.alert=(_title,message,buttons)=>{if(confirm(message))buttons?.at(-1)?.onPress?.();};
function App(){
 const snapshot=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
 const [route,setRoute]=React.useState({path:location.pathname,params:{'#':location.hash.slice(1)} as Record<string,string>});
 React.useEffect(()=>{void controller.restore();},[]);
 const go=React.useCallback((value:unknown)=>{
  if(typeof value==='string')setRoute({path:value,params:{}});
  else {const r=value as {pathname:string;params:Record<string,string>};setRoute({path:r.pathname,params:r.params});}
 },[]);
 const setParams=React.useCallback((values:Record<string,string>)=>{
  setRoute(r=>({...r,params:{...r.params,...values}}));history.replaceState(null,'',location.pathname);
 },[]);
 const context=React.useMemo(()=>({go,params:route.params,setParams}),[go,route.params,setParams]);
 const Home=()=> <div>Signed in as {snapshot.actor?.username} at store {snapshot.actor?.storeId}</div>;
 const Screen=({'/sign-in':SignInScreen,'/activate':ActivateScreen,'/team/invite':InviteScreen,'/team':TeamScreen,
  '/team/[userId]':MemberScreen,'/accounts':AccountsScreen,'/today':Home} as Record<string,React.ComponentType>)[route.path]||Home;
 return <SessionContext.Provider value={controller}><SafeAreaProvider><RouterContext.Provider value={context}>
   <Screen key={route.path}/>
 </RouterContext.Provider></SafeAreaProvider></SessionContext.Provider>;
}
createRoot(document.getElementById('root')!).render(<App/>);
