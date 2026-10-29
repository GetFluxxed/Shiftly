import React from 'react';
import { BackHandler, Platform } from 'react-native';
import { useFocusEffect, useIsFocused, usePathname, usePreventRemove } from 'expo-router';
import { isPageBackAction } from './pageBack';

/** Align Android system Back and iOS stack gestures with the page's visible Back action. */
export function usePageBack(onBack: () => void, enabled = true): void {
  const latest = React.useRef(onBack);
  latest.current = onBack;
  const focused = useIsFocused();
  const pathname = usePathname();
  const [bypass, setBypass] = React.useState(false);

  useFocusEffect(React.useCallback(() => {
    setBypass(false);
    if (Platform.OS !== 'android' || !enabled) return undefined;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      latest.current();
      return true;
    });
    return () => subscription.remove();
  }, [enabled]));

  React.useEffect(() => {
    if (focused) setBypass(false);
  }, [focused, pathname]);

  usePreventRemove(Platform.OS === 'ios' && enabled && focused && !bypass, ({ data, repeat }) => {
    if (isPageBackAction(data.action.type)) {
      latest.current();
      return;
    }
    setBypass(true);
    repeat();
  });
}
