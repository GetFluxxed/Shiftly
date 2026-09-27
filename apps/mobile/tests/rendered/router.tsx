import React from 'react';
type RouterValue = {
  go: (value: unknown) => void; params: Record<string,string>; setParams: (values: Record<string,string>) => void;
  replace?: (value: unknown) => void; canGoBack?: () => boolean; back?: () => void;
};
export const RouterContext = React.createContext<RouterValue>({ go: () => {}, params: {}, setParams: () => {} });
export const useRouter = () => { const r=React.useContext(RouterContext);return {
  push:r.go,replace:r.replace||r.go,setParams:r.setParams,canGoBack:r.canGoBack||(()=>false),back:r.back||(()=>r.go('/accounts')),
}; };
export const useLocalSearchParams = () => React.useContext(RouterContext).params;
export const useFocusEffect = (effect: () => void | (()=>void)) => React.useEffect(effect,[effect]);

export function Redirect({href}:{href:string}) { const {go}=React.useContext(RouterContext);React.useEffect(()=>go(href),[go,href]);return null; }

// Expose the actual app layout's tab visibility and destinations without a native navigator.
export function Tabs({children}:React.PropsWithChildren<Record<string,unknown>>) {
  return <nav aria-label="Main navigation" style={{display:'flex',gap:8}}>{children}</nav>;
}
Tabs.Screen=function TabScreen({name,options}:{name:string;options?:{title?:string;href?:string|null}}) {
  const {go}=React.useContext(RouterContext);
  if(options?.href===null)return null;
  return <button onClick={()=>go(options?.href||'/'+name)}>{options?.title||name}</button>;
};
