import React from 'react';
import { useLocalSearchParams, usePathname, useRouter, type Href } from 'expo-router';
import { appBackLabel, appParent, appRoute, appTarget } from './routes';

function route(href: Href) {
  return appRoute(typeof href === 'string' ? href : href.pathname, typeof href === 'string' ? {} : href.params) || { pathname: '/today' };
}

export function useAppNavigation() {
  const router = useRouter(); const pathname = usePathname(); const params = useLocalSearchParams();
  const currentKey = JSON.stringify(appRoute(pathname, params) || { pathname: '/today' });
  const current = React.useMemo(() => JSON.parse(currentKey) as ReturnType<typeof route>, [currentKey]);
  const trail = typeof params.appTrail === 'string' ? params.appTrail
    : typeof params.inventoryTrail === 'string' ? params.inventoryTrail : undefined;
  const parent = React.useCallback((fallback: Href) => {
    const target = appParent(trail, route(fallback));
    return { href: target as Href, label: appBackLabel(target.pathname) };
  }, [trail]);
  const open = React.useCallback((href: Href) => {
    router.push(appTarget(current, trail, route(href)) as Href);
  }, [current, router, trail]);
  const replace = React.useCallback((href: Href, options?: { dropParents?: number | true; parent?: Href }) => {
    router.replace(appTarget(current, trail, route(href), 'replace', options?.dropParents,
      options?.parent ? route(options.parent) : undefined) as Href);
  }, [current, router, trail]);
  const back = React.useCallback((fallback: Href) => {
    const target = parent(fallback).href;
    const targetPath = typeof target === 'string' ? target : target.pathname;
    if (pathname.split('/')[1] === targetPath.split('/')[1]) router.dismissTo(target);
    else router.replace(target);
  }, [parent, pathname, router]);
  return React.useMemo(() => ({ open, replace, back, parent }), [back, open, parent, replace]);
}
