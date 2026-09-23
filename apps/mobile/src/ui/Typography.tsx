import React, { createContext, useContext } from 'react';
import { Platform, StyleSheet, Text as NativeText, type TextProps } from 'react-native';
import { fonts } from './theme';

export const FontsReadyContext = createContext(false);
export const useFontsReady = () => useContext(FontsReadyContext);

/** Use actual bundled font weights; keep native fallbacks usable if loading fails. */
export function Text({ style, ...props }: TextProps) {
  const ready = useFontsReady();
  const flat = StyleSheet.flatten(style) || {};
  const family = flat.fontFamily;
  const display = family === fonts.display;
  const custom = family && !Object.values(fonts).includes(family);
  const strong = Number(flat.fontWeight) >= 500 || flat.fontWeight === 'bold';
  const fontFamily = custom ? family : ready ? (display ? fonts.display : strong ? fonts.strong : fonts.body)
    : display ? (Platform.OS === 'ios' ? 'Georgia' : 'serif') : undefined;
  return <NativeText {...props} style={[style, { fontFamily, ...(ready && !custom ? { fontWeight: 'normal' } as const : {}) }]} />;
}
