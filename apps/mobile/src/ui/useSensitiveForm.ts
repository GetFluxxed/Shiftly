import { useCallback, useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useFocusEffect } from 'expo-router';

/** Passwords, recovery codes and unsent notes never survive leaving a view. */
export function useSensitiveForm(clear: () => void) {
  const latest = useRef(clear);
  latest.current = clear;
  useFocusEffect(useCallback(() => () => { latest.current(); }, []));
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      if (state !== 'active') latest.current();
    });
    const blur = AppState.addEventListener('blur', () => latest.current());
    return () => { subscription.remove(); blur.remove(); };
  }, []);
}
