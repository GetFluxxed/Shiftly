import { useCallback, useEffect, useRef } from 'react';
import { useLocalSearchParams } from 'expo-router';
import type { ScrollView } from 'react-native';
import { useWorkspace } from './WorkspaceProvider';

/** Screen instances retain only their offset, not the server data they display. */
export function useScrollRestoration(title: string, scroll: React.RefObject<ScrollView | null>) {
  const { controller, scope, ready, resume } = useWorkspace();
  const params = useLocalSearchParams();
  const ids = ['productId', 'shelfId', 'countId', 'lineId', 'userId'].map(key => {
    const value = params[key]; return typeof value === 'string' && /^[a-zA-Z0-9-]{1,40}$/.test(value) ? value : '';
  }).join(':');
  const key = `scroll:${title}:${ids}`;
  const identity = useRef(key);
  const offset = useRef(controller?.read(key, 0) || 0);
  const pending = useRef(offset.current > 0), viewport = useRef(0), height = useRef(0);
  const frame = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (identity.current !== key) {
      identity.current = key; offset.current = controller?.read(key, 0) || 0;
      pending.current = offset.current > 0;
      scroll.current?.scrollTo({ y: offset.current, animated: false });
    }
  }, [controller, key, scroll]);
  const restore = useCallback(() => {
    if (!pending.current || !ready || !viewport.current) return;
    const available = Math.max(0, height.current - viewport.current);
    cancelAnimationFrame(frame.current || 0);
    frame.current = requestAnimationFrame(() => scroll.current?.scrollTo({ y: Math.min(offset.current, available), animated: false }));
    // A loading state can be shorter than the final list. Keep the requested
    // position until the content reaches it, or the user starts scrolling.
  }, [ready, scroll]);
  useEffect(() => () => cancelAnimationFrame(frame.current || 0), []);
  const save = (y: number) => {
    if (!controller || !ready || !Number.isFinite(y) || y < 0 || y > 1_000_000 || controller.getSnapshot().resume !== resume) return;
    offset.current = y; controller.write(key, y, '', scope);
  };
  return {
    onLayout: (event: { nativeEvent: { layout: { height: number } } }) => { viewport.current = event.nativeEvent.layout.height; restore(); },
    onContentSizeChange: (_width: number, newHeight: number) => { height.current = newHeight; restore(); },
    onScrollBeginDrag: () => { pending.current = false; },
    onTouchStart: () => { pending.current = false; },
    onScroll: (event: { nativeEvent: { contentOffset: { y: number } } }) => {
      if (!pending.current) save(event.nativeEvent.contentOffset.y);
    },
    toTop: () => { pending.current = false; save(0); scroll.current?.scrollTo({ y: 0, animated: false }); },
  };
}
