import React, { Children, PropsWithChildren, useState } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';

type Icon = React.ComponentProps<typeof Ionicons>['name'];

/** Measure the list itself so shelf sidebars do not inherit a tablet-wide grid. */
export function InventoryList({ children }: PropsWithChildren) {
  const [width, setWidth] = useState(0);
  const { fontScale } = useWindowDimensions();
  const columns = width >= 720 && fontScale < 1.5 ? 2 : 1;
  const items = Children.toArray(children);
  return <View style={styles.list} onLayout={event => setWidth(event.nativeEvent.layout.width)}>
    {items.filter((_, index) => index % columns === 0).map((_, row) =>
      <View key={row} style={styles.row}>
        {items.slice(row * columns, row * columns + columns).map(item =>
          <View key={(item as React.ReactElement).key} style={styles.cell}>{item}</View>)}
        {columns === 2 && row * columns + 1 >= items.length ? <View style={styles.cell} /> : null}
      </View>)}
  </View>;
}

/** Compact repeated records; editing forms keep the full-size shared controls. */
export function InventoryItem({ title, subtitle, detail, value, status, onPress, label, disabled = false,
  icon = 'chevron-forward', action, children }: PropsWithChildren<{
  title: string; subtitle?: string; detail?: string; value?: string; status?: string;
  onPress?: () => void; label?: string; disabled?: boolean; icon?: Icon;
  action?: { label: string; title?: string; icon: Icon; onPress: () => void; disabled?: boolean };
}>) {
  const { fontScale } = useWindowDimensions();
  const content = <>
    <View style={[styles.headingRow, fontScale >= 1.5 && styles.stacked]}>
      <Text accessibilityRole="header" style={styles.title}>{title}</Text>
      {value ? <Text style={[styles.value, fontScale >= 1.5 && styles.stackedValue]}>{value}</Text> : null}
    </View>
    {subtitle ? <Text style={styles.meta}>{subtitle}</Text> : null}
    {detail ? <Text style={styles.meta}>{detail}</Text> : null}
    {status ? <Text style={styles.status}>{status}</Text> : null}
    {children}
  </>;
  return <View style={styles.card}>
    {onPress ? <Pressable accessibilityRole="button" accessibilityLabel={label || title}
      accessibilityHint={[subtitle, value, detail, status].filter(Boolean).join('. ')}
      accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
      style={({ pressed }) => [styles.open, disabled && styles.disabled, pressed && styles.pressed]}>
      <View style={styles.content}>{content}</View>
      <Ionicons name={icon} size={20} color={colors.primary} accessible={false} />
    </Pressable> : <View style={[styles.content, styles.staticContent]}>{content}</View>}
    {action ? <Pressable accessibilityRole="button" accessibilityLabel={action.label}
      accessibilityState={{ disabled: Boolean(action.disabled) }} disabled={action.disabled} onPress={action.onPress}
      style={({ pressed }) => [styles.action, action.disabled && styles.disabled, pressed && styles.pressed]}>
      <Ionicons name={action.icon} size={20} color={colors.primary} accessible={false} />
      {action.title ? <Text style={styles.actionLabel}>{action.title}</Text> : null}
    </Pressable> : null}
  </View>;
}

const styles = StyleSheet.create({
  list: { gap: 8 }, row: { flexDirection: 'row', alignItems: 'stretch', gap: 8 },
  cell: { flex: 1, minWidth: 0 },
  card: { flex: 1, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.line,
    borderRadius: 14, backgroundColor: colors.card, overflow: 'hidden' },
  content: { flex: 1, minWidth: 0, gap: 3 }, staticContent: { padding: 10 },
  open: { flex: 1, minWidth: 0, minHeight: 56, padding: 10, gap: 8, flexDirection: 'row', alignItems: 'center' },
  headingRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  title: { flex: 1, minWidth: 0, fontSize: 18, lineHeight: 23, fontWeight: '600', color: colors.ink },
  value: { maxWidth: '45%', flexShrink: 1, fontSize: 18, lineHeight: 23, fontWeight: '600', color: colors.primary, textAlign: 'right' },
  stacked: { flexDirection: 'column' }, stackedValue: { maxWidth: '100%', textAlign: 'left' },
  meta: { fontSize: 13, lineHeight: 18, color: colors.muted },
  status: { alignSelf: 'flex-start', flexShrink: 1, fontSize: 12, lineHeight: 18, fontWeight: '600',
    color: colors.primary, backgroundColor: colors.soft, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  action: { minWidth: 56, minHeight: 48, paddingHorizontal: 8, paddingVertical: 8, marginRight: 4,
    borderRadius: 10, gap: 2, alignItems: 'center', justifyContent: 'center', flexShrink: 1, maxWidth: '35%' },
  actionLabel: { fontSize: 12, lineHeight: 16, fontWeight: '600', color: colors.primary },
  pressed: { backgroundColor: colors.blush }, disabled: { opacity: 0.55 },
});
