import React from 'react';
import { Stack } from 'expo-router';
import { StatusBar } from 'react-native';
import { useFonts } from 'expo-font';
import { WorkSans_400Regular } from '@expo-google-fonts/work-sans/400Regular';
import { WorkSans_600SemiBold } from '@expo-google-fonts/work-sans/600SemiBold';
import { Newsreader_500Medium } from '@expo-google-fonts/newsreader/500Medium';
import { FontsReadyContext } from '@/src/ui/Typography';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider } from '@/src/session/SessionProvider';
import { colors } from '@/src/ui/theme';

export default function RootLayout() {
  const [loaded] = useFonts({ WorkSans_400Regular, WorkSans_600SemiBold, Newsreader_500Medium });
  return <FontsReadyContext.Provider value={loaded}><SafeAreaProvider><SessionProvider>
    <StatusBar barStyle="dark-content" backgroundColor={colors.paper} />
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }} />
  </SessionProvider></SafeAreaProvider></FontsReadyContext.Provider>;
}
