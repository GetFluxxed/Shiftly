import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { headsUpPath, type HeadsUp } from './api';
import { Body, Card, EmptyState, Heading, Loading, Notice, layout } from '@/src/ui/components';
import { colors, friendlyDate } from '@/src/ui/theme';
import { useResource } from '@/src/ui/useResource';

/** Today shows the current note; managers edit it from Store. */
export function HeadsUpCard() {
  const resource = useResource<HeadsUp>(headsUpPath);
  return <Card>
    <View style={layout.row}>
      <View style={[layout.row, layout.flex]}>
        <Ionicons name="megaphone-outline" color={colors.accentStrong} size={24} accessible={false} />
        <Heading>Heads Up</Heading>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel="Refresh Heads Up"
        accessibilityHint="Get the latest store announcement"
        accessibilityState={{ disabled: resource.loading, busy: resource.loading }} disabled={resource.loading}
        onPress={() => { void resource.refresh(); }}
        style={({ pressed }) => [styles.refresh, pressed && styles.pressed, resource.loading && styles.disabled]}>
        <Ionicons name="refresh-outline" size={22} color={colors.primary} accessible={false} />
      </Pressable>
    </View>
    {resource.loading ? <Loading label="Getting the latest update…" /> : resource.error ?
      <Notice message={resource.error} kind="error" /> : resource.data?.message ? <>
        <Body>{resource.data.message}</Body>
        {resource.data.updatedAt ? <Body muted>Updated {friendlyDate(resource.data.updatedAt)}</Body> : null}
      </> : <EmptyState icon="chatbubble-ellipses-outline" title="No store updates" description="No update from your manager." />}
  </Card>;
}

const styles = StyleSheet.create({
  refresh: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center' },
  pressed: { backgroundColor: colors.blush },
  disabled: { opacity: 0.55 },
});
