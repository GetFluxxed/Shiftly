import React from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider } from '@/src/session/SessionProvider';
import { colors } from '@/src/ui/theme';

export default function RootLayout() {
  return <SafeAreaProvider><SessionProvider>
    <StatusBar barStyle="dark-content" backgroundColor={colors.paper} />
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }} />
  </SessionProvider></SafeAreaProvider>;
}
