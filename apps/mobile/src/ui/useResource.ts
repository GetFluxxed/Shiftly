import { useCallback, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import { useSession } from '@/src/session/SessionProvider';

/** Private data is refreshed on entry and discarded when the view loses focus. */
export function useResource<T>(path: string, enabled = true) {
  const { request } = useSession();
  return useLoaderResource(useCallback(() => request<T>(path), [request, path]), enabled);
}

/** Typed feature loaders share the same focus and stale-response protection. */
export function useLoaderResource<T>(load: () => Promise<T>, enabled = true) {
  const active = useRef(false);
  const generation = useRef(0);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    if (!enabled || !active.current) return;
    const current = ++generation.current;
    setLoading(true); setError(null); setData(null);
    try {
      const result = await load();
      if (active.current && generation.current === current) setData(result);
    } catch (failure) {
      if (active.current && generation.current === current) {
        setError(failure instanceof Error ? failure.message : 'Unable to connect. Please try again.');
      }
    } finally {
      if (active.current && generation.current === current) setLoading(false);
    }
  }, [enabled, load]);
  useFocusEffect(useCallback(() => {
    active.current = true;
    void refresh();
    return () => { active.current = false; generation.current += 1; setData(null); setError(null); };
  }, [refresh]));
  return { data, loading, error, refresh };
}
