import React from 'react';
export const RouterContext = React.createContext({ go: (_: unknown) => {}, params: {} as Record<string,string>, setParams: (_: Record<string,string>) => {} });
export const useRouter = () => { const r=React.useContext(RouterContext);return {push:r.go,replace:r.go,setParams:r.setParams,canGoBack:()=>false,back:()=>r.go('/accounts')}; };
export const useLocalSearchParams = () => React.useContext(RouterContext).params;
export const useFocusEffect = (effect: () => void | (()=>void)) => React.useEffect(effect,[effect]);

export function Redirect({href}:{href:string}) { const {go}=React.useContext(RouterContext);React.useEffect(()=>go(href),[go,href]);return null; }
