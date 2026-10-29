import React from 'react';
import { Pressable, StyleSheet } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useInventoryNavigation } from '@/src/inventory/shared';
import { useSession } from '@/src/session/SessionProvider';
import { Notice, Screen } from '@/src/ui/components';
import { ActionGrid, ActionTile } from '@/src/ui/ActionGrid';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';

export function InventoryScreen() {
  const { actor, stores } = useSession();
  const nav = useInventoryNavigation();
  const store = stores.find(item => item.storeId === actor?.storeId);
  if (!actor?.capabilities.includes('inventory.view')) {
    return <Screen title="Inventory"><Notice message="Your current account does not have inventory access for this store." /></Screen>;
  }
  return <Screen title="Inventory" eyebrow={store?.storeName || 'Your store'}>
    <ActionGrid>
      <ActionTile title="Current Inventory" label="View current inventory" icon="stats-chart-outline"
        onPress={() => nav.open('/stock')} footer={
          <Pressable accessibilityRole="button" accessibilityLabel="Count history" onPress={() => nav.open('/counts/history')}
            style={({ pressed }) => [styles.history, pressed && styles.pressed]}>
            <Text style={styles.historyText}>Count history</Text>
            <Ionicons name="chevron-forward" size={14} color={colors.primary} accessible={false} />
          </Pressable>} />
      <ActionTile title="Begin Count" icon="clipboard-outline" onPress={() => nav.open('/counts')} />
      <ActionTile title="Open Shelves" label="Open shelves" icon="albums-outline" onPress={() => nav.open('/shelves')} />
      <ActionTile title="Catalog" label="Open company catalog" icon="cube-outline" onPress={() => nav.open('/catalog')} />
    </ActionGrid>
  </Screen>;
}

const styles = StyleSheet.create({
  history: { minHeight: 44, paddingVertical: 10, paddingHorizontal: 12, gap: 4,
    borderTopWidth: 1, borderTopColor: colors.line, backgroundColor: colors.soft,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  historyText: { flexShrink: 1, color: colors.primary, fontSize: 13, lineHeight: 18, fontWeight: '600' },
  pressed: { backgroundColor: colors.blush },
});
