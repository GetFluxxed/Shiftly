import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';

/** Ignore completions after navigation or an account context replacement. */
export function useTask() {
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const generation = useRef(0);
  const focused = useRef(true);
  const foreground = useRef(AppState.currentState === 'active');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useFocusEffect(useCallback(() => {
    focused.current = true;
    return () => { focused.current = false; generation.current += 1; };
  }, []));
  useEffect(() => {
    const change = AppState.addEventListener('change', (state) => {
      foreground.current = state === 'active';
      if (state !== 'active') generation.current += 1;
    });
    const blur = AppState.addEventListener('blur', () => { foreground.current = false; generation.current += 1; });
    const focus = AppState.addEventListener('focus', () => { foreground.current = true; });
    return () => { change.remove(); blur.remove(); focus.remove(); };
  }, []);
  const run = useCallback(async <T,>(operation: () => Promise<T>, onSuccess?: (value: T) => void) => {
    if (inFlight.current || !mounted.current || !focused.current || !foreground.current) return;
    const current = generation.current;
    inFlight.current = true;
    setPending(true); setError(null);
    try {
      const value = await operation();
      if (mounted.current && focused.current && foreground.current && current === generation.current) onSuccess?.(value);
    } catch (failure) {
      if (mounted.current && focused.current && foreground.current && current === generation.current) setError(failure instanceof Error ? failure.message : 'Unable to connect. Please try again.');
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }, []);
  return { pending, error, run, setError };
}
