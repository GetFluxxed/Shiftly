import React from 'react';
type RouterValue = {
  path?: string; go: (value: unknown) => void; params: Record<string,string>; setParams: (values: Record<string,string>) => void;
  replace?: (value: unknown) => void; canGoBack?: () => boolean; back?: () => void;
};
export const RouterContext = React.createContext<RouterValue>({ go: () => {}, params: {}, setParams: () => {} });
export const useRouter = () => { const r=React.useContext(RouterContext);return {
  push:r.go,replace:r.replace||r.go,setParams:r.setParams,canGoBack:r.canGoBack||(()=>false),back:r.back||(()=>r.go('/accounts')),
}; };
export const usePathname = () => { const r=React.useContext(RouterContext); return (r.path || '/').replace(/\[(\w+)\]/g, (match,key:string)=>r.params[key] || match); };
export const useGlobalSearchParams = () => React.useContext(RouterContext).params;
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

export function destination(value: unknown): { path: string; params: Record<string, string> } {
  const route = typeof value === 'string' ? { path: value, params: {} as Record<string,string> }
    : { path: (value as { pathname:string }).pathname, params: { ...(value as {params?:Record<string,string>}).params } };
  const patterns: [RegExp, string, string[]][] = [
    [/^\/counts\/([0-9a-f-]+)\/line\/([0-9a-f-]+)$/, '/counts/[countId]/line/[lineId]', ['countId','lineId']],
    [/^\/counts\/([0-9a-f-]+)\/review$/, '/counts/[countId]/review', ['countId']],
    [/^\/counts\/([0-9a-f-]{36})$/, '/counts/[countId]', ['countId']],
    [/^\/catalog\/([0-9a-f-]{36})$/, '/catalog/[productId]', ['productId']],
    [/^\/stock\/([0-9a-f-]{36})$/, '/stock/[productId]', ['productId']],
    [/^\/shelves\/([0-9a-f-]{36})$/, '/shelves/[shelfId]', ['shelfId']],
    [/^\/production\/recipes\/([0-9a-f-]{36})$/, '/production/recipes/[recipeId]', ['recipeId']],
    [/^\/production\/logs\/([0-9a-f-]{36})$/, '/production/logs/[logId]', ['logId']],
    [/^\/team\/([0-9]+)$/, '/team/[userId]', ['userId']],
    [/^\/owner\/([0-9]+)$/, '/owner/[userId]', ['userId']],
  ];
  for (const [pattern,path,keys] of patterns) {
    const match=route.path.match(pattern);
    if(match) return {path,params:{...route.params,...Object.fromEntries(keys.map((key,i)=>[key,match[i+1]!]))}};
  }
  return route;
}
