import React from 'react';
export const RouterContext = React.createContext({ go: (_: unknown) => {}, params: {} as Record<string,string> });
export const useRouter = () => { const r=React.useContext(RouterContext);return {push:r.go,replace:r.go}; };
export const useLocalSearchParams = () => React.useContext(RouterContext).params;
export const useFocusEffect = (effect: () => void | (()=>void)) => React.useEffect(effect,[effect]);
