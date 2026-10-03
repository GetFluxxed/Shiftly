import Ionicons from '@expo/vector-icons/Ionicons';
import React, { useCallback } from 'react';
import { Pressable, StyleSheet, View, useWindowDimensions } from 'react-native';

import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { Body, Loading } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import type { Product } from './api';
import { InventorySearch, LoadError, Pages, useInventory, useInventoryResource } from './shared';

type ShelfProductPickerProps = {
  shelfId: string;
  assigned: string[];
  disabled: boolean;
  onAdd: (id: string) => void;
};

function sizeLabel(product: Product): string {
  if (product.containerAmount === null) return 'Size not set';
  return `${product.containerAmount} ${product.baseUnit === 'each' ? 'items' : product.baseUnit}`;
}

export function ShelfProductPicker({ shelfId, assigned, disabled, onAdd }: ShelfProductPickerProps) {
  const { api } = useInventory();
  const { fontScale } = useWindowDimensions();
  const [filters, setFilters] = useRememberedState(`inventory.shelf.${shelfId}.picker`, {
    query: '', search: '', cursor: '',
  });
  const { query, search, cursor } = filters;
  const setQuery = (value: string) => setFilters(current => ({ ...current, query: value }));
  const setCursor = (value: string) => setFilters(current => ({ ...current, cursor: value }));
  const resource = useInventoryResource(useCallback(
    () => api.products(search, 'active', cursor),
    [api, search, cursor],
  ));

  return <View testID="shelf-product-picker" style={styles.picker}>
    <InventorySearch
      label="Find a product to assign"
      value={query}
      onChange={setQuery}
      submitLabel="Find products"
      disabled={disabled}
      onSubmit={() => {
        if (search === query.trim() && !cursor) void resource.refresh();
        setFilters(current => ({ ...current, cursor: '', search: query.trim() }));
      }}
    />
    {resource.loading ? <Loading label="Finding products…" /> : resource.error || !resource.data
      ? <LoadError {...resource} />
      : <>
        {!resource.data.items.length
          ? <Body>No matching products. Try another search or add a product.</Body>
          : <View style={styles.list}>{resource.data.items.map(product => {
            const isAssigned = assigned.includes(product.id);
            const rowDisabled = disabled || isAssigned;
            return <Pressable
              key={product.id}
              accessibilityRole="button"
              accessibilityLabel={isAssigned ? `${product.name} is assigned` : `Assign ${product.name}`}
              accessibilityHint={sizeLabel(product)}
              accessibilityState={{ disabled: rowDisabled }}
              disabled={rowDisabled}
              onPress={() => onAdd(product.id)}
              style={({ pressed }) => [
                styles.row,
                fontScale >= 1.5 && styles.largeTextRow,
                pressed && styles.pressed,
                rowDisabled && styles.disabled,
              ]}
            >
              <View style={[styles.summary, fontScale >= 1.5 && styles.largeTextSummary]}>
                <Text style={styles.name}>{product.name}</Text>
                <Text style={[styles.size, fontScale >= 1.5 && styles.largeTextSize]}>{sizeLabel(product)}</Text>
              </View>
              <View style={styles.icon}><Ionicons
                name={isAssigned ? 'checkmark-circle' : 'add-circle-outline'}
                size={24}
                color={isAssigned ? colors.success : colors.primary}
                accessible={false}
              /></View>
            </Pressable>;
          })}</View>}
        <Pages next={resource.data.nextCursor} cursor={cursor} setCursor={setCursor} disabled={disabled} />
      </>}
  </View>;
}

const styles = StyleSheet.create({
  picker: { gap: 10 },
  list: { gap: 6 },
  row: {
    minHeight: 48,
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 12,
    backgroundColor: colors.card,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  icon: { width: 24, height: 24, flexShrink: 0, alignItems: 'center', justifyContent: 'center' },
  largeTextRow: { alignItems: 'flex-start' },
  summary: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'baseline', gap: 10 },
  largeTextSummary: { flexDirection: 'column', alignItems: 'stretch', gap: 2 },
  name: { flex: 1, minWidth: 0, color: colors.ink, fontSize: 16, lineHeight: 21, fontWeight: '600' },
  size: { flexShrink: 1, color: colors.muted, fontSize: 14, lineHeight: 20, textAlign: 'right' },
  largeTextSize: { textAlign: 'left' },
  pressed: { backgroundColor: colors.blush },
  disabled: { opacity: 0.58 },
});
