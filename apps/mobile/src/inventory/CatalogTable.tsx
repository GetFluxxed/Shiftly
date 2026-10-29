import React from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Card } from '@/src/ui/components';
import { colors } from '@/src/ui/theme';
import { Text } from '@/src/ui/Typography';
import type { Product } from './api';

type Props = {
  items: Product[];
  onOpen: (item: Product) => void;
  onChange?: (item: Product) => void;
  changeDisabled?: boolean;
};

function containerValue(item: Product): string {
  if (item.containerLabelAmount && item.containerLabelUnit) {
    const unit = item.containerLabelUnit === 'lb' ? 'lbs' : item.containerLabelUnit === 'each' ? 'items' : item.containerLabelUnit;
    return `${item.containerLabelAmount} ${unit}`;
  }
  if (item.containerAmount) {
    const unit = item.baseUnit === 'each' ? 'items' : item.baseUnit;
    return `${item.containerAmount} ${unit}`;
  }
  return 'Not set';
}

export function CatalogTable({ items, onOpen, onChange, changeDisabled = false }: Props) {
  const { fontScale } = useWindowDimensions();
  const largeText = fontScale >= 1.5;
  return <Card style={styles.table}>
    <View style={styles.header} accessibilityRole="header">
      <View style={styles.headerMain}>
        <Text style={[styles.headText, styles.productColumn]}>Product</Text>
        {!largeText ? <Text style={[styles.headText, styles.containerColumn]}>Container</Text> : null}
      </View>
      {onChange ? <Text style={[styles.headText, styles.actionColumn]}>Change</Text> : null}
    </View>
    {items.map(item => {
      const container = containerValue(item);
      return <View key={item.id} style={[styles.row, largeText && styles.largeTextRow]}>
        <Pressable accessibilityRole="button" accessibilityLabel={`View product: ${item.name}`}
          accessibilityHint={`SKU ${item.sku}. Container ${container}.${item.active ? '' : ' Archived.'}`}
          onPress={() => onOpen(item)}
          style={({ pressed }) => [styles.open, largeText && styles.largeTextOpen, pressed && styles.pressed]}>
          <View style={styles.productColumn}>
            <Text numberOfLines={largeText ? 3 : 2} style={styles.product}>{item.name}</Text>
            <Text numberOfLines={2} style={styles.sku}>SKU {item.sku}</Text>
            {!item.active ? <Text style={styles.archived}>Archived</Text> : null}
          </View>
          <Text style={[styles.container, !largeText && styles.containerColumn, largeText && styles.largeTextContainer]}>{container}</Text>
        </Pressable>
        {onChange ? <Pressable accessibilityRole="button" accessibilityLabel={`Change measurement: ${item.name}`}
          accessibilityState={{ disabled: changeDisabled }} disabled={changeDisabled} onPress={() => onChange(item)}
          style={({ pressed }) => [styles.change, styles.actionColumn, changeDisabled && styles.disabled, pressed && styles.pressed]}>
          <Ionicons name="resize-outline" size={18} color={colors.primary} accessible={false} />
          <Text style={styles.changeText}>Change</Text>
        </Pressable> : null}
      </View>;
    })}
  </Card>;
}

const styles = StyleSheet.create({
  table: { padding: 0, gap: 0, overflow: 'hidden' },
  header: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.soft,
    borderBottomWidth: 1, borderBottomColor: colors.line },
  headerMain: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 9 },
  headText: { color: colors.muted, fontSize: 9, lineHeight: 12, fontWeight: '700', textTransform: 'uppercase' },
  row: { flexDirection: 'row', alignItems: 'stretch', minHeight: 64, borderBottomWidth: 1, borderBottomColor: colors.line },
  largeTextRow: { minHeight: 76 },
  open: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 8 },
  largeTextOpen: { flexDirection: 'column', alignItems: 'stretch', gap: 4 },
  productColumn: { flex: 1, minWidth: 0 },
  containerColumn: { width: 76, flexShrink: 0 },
  actionColumn: { width: 62, flexShrink: 0 },
  product: { color: colors.ink, fontSize: 14, lineHeight: 18, fontWeight: '700' },
  sku: { color: colors.muted, fontSize: 11, lineHeight: 15, marginTop: 2 },
  archived: { color: colors.danger, fontSize: 10, lineHeight: 14, fontWeight: '600', marginTop: 1 },
  container: { color: colors.ink, fontSize: 12, lineHeight: 17, fontVariant: ['tabular-nums'] },
  largeTextContainer: { width: '100%', fontSize: 14, lineHeight: 20 },
  change: { minHeight: 44, alignItems: 'center', justifyContent: 'center', gap: 1, paddingVertical: 6, borderLeftWidth: 1, borderLeftColor: colors.line },
  changeText: { color: colors.primary, fontSize: 11, lineHeight: 15, fontWeight: '700' },
  pressed: { backgroundColor: colors.blush },
  disabled: { opacity: 0.55 },
});
