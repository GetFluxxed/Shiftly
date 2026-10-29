import React, { Children, PropsWithChildren } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Text } from './Typography';
import { colors, fonts } from './theme';

export function ActionGrid({ children }: PropsWithChildren) {
  const tiles = Children.toArray(children);
  return <View style={styles.grid}>{tiles.filter((_, index) => index % 2 === 0).map((_, row) =>
    <View key={row} style={styles.row}>{tiles.slice(row * 2, row * 2 + 2)}
      {row * 2 + 1 >= tiles.length ? <View style={styles.space} /> : null}
    </View>)}</View>;
}

export function ActionTile({ title, label = title, icon, onPress, disabled = false, footer }: {
  title: string; label?: string; icon: React.ComponentProps<typeof Ionicons>['name'];
  onPress: () => void; disabled?: boolean; footer?: React.ReactNode;
}) {
  const { width, height } = useWindowDimensions();
  const compact = width < 360 || height < 700;
  return <View style={[styles.tile, compact && styles.compactTile]}>
    <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }}
      disabled={disabled} onPress={onPress}
      style={({ pressed }) => [styles.action, compact && styles.compactAction, disabled && styles.disabled, pressed && styles.pressed]}>
      <View style={styles.iconRow} accessible={false}>
        <Ionicons name={icon} size={compact ? 22 : 28} color={colors.primary} />
        <Ionicons name={disabled ? 'lock-closed-outline' : 'arrow-forward-outline'} size={18} color={colors.muted} />
      </View>
      <Text style={[styles.title, compact && styles.compactTitle]}>{title}</Text>
    </Pressable>
    {footer}
  </View>;
}

const styles = StyleSheet.create({
  grid: { gap: 12 }, row: { flexDirection: 'row', alignItems: 'stretch', gap: 12 }, space: { flex: 1 },
  tile: { flex: 1, minWidth: 0, minHeight: 180, borderWidth: 1, borderColor: colors.line,
    borderRadius: 20, backgroundColor: colors.card, overflow: 'hidden' },
  compactTile: { minHeight: 144 },
  action: { flex: 1, padding: 16, gap: 12, justifyContent: 'space-between' },
  compactAction: { padding: 12, gap: 8 },
  iconRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { fontFamily: fonts.display, fontSize: 24, lineHeight: 28, color: colors.ink },
  compactTitle: { fontSize: 20, lineHeight: 22 },
  disabled: { opacity: 0.55 }, pressed: { backgroundColor: colors.blush },
});
