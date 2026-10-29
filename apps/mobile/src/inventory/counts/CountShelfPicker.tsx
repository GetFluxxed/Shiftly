import React, { useCallback, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Body, Heading, Loading } from '@/src/ui/components';
import { Text } from '@/src/ui/Typography';
import { colors } from '@/src/ui/theme';
import { LoadError, Pages, useInventory, useInventoryResource } from '../shared';

export interface CountShelfChoice { id: string; name: string }

export function CountShelfPicker({ value, onChange, choices }: {
  value: CountShelfChoice; onChange: (value: CountShelfChoice) => void; choices?: CountShelfChoice[];
}) {
  const { api } = useInventory();
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState('');
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const resource = useInventoryResource(useCallback(() => api.shelves(cursor), [api, cursor]), open && !choices);
  const suppliedChoices = choices?.filter(choice => choice.id && choice.id !== 'unassigned');
  const requestedOffset = /^\d+$/.test(cursor) ? Number(cursor) : 0;
  const localOffset = suppliedChoices && requestedOffset < suppliedChoices.length ? requestedOffset : 0;
  const localChoices = suppliedChoices?.slice(localOffset, localOffset + 40);
  const localNext = suppliedChoices && localOffset + 40 < suppliedChoices.length ? String(localOffset + 40) : null;
  const choose = (choice: CountShelfChoice) => { onChange(choice); setOpen(false); };
  const option = (choice: CountShelfChoice) => <Pressable key={choice.id}
    accessibilityRole="radio" accessibilityLabel={choice.name} accessibilityState={{ checked: value.id === choice.id }}
    onPress={() => choose(choice)} style={({ pressed }) => [styles.option, pressed && styles.pressed]}>
    <Text style={styles.optionText}>{choice.name}</Text>
    {value.id === choice.id ? <Ionicons name="checkmark" size={20} color={colors.primary} /> : null}
  </Pressable>;
  return <>
    <Pressable accessibilityRole="button" accessibilityLabel={`Choose shelf: ${value.name}`}
      accessibilityState={{ expanded: open }} onPress={() => setOpen(true)}
      style={({ pressed }) => [styles.trigger, pressed && styles.pressed]}>
      <Text style={styles.label}>{value.name}</Text><Ionicons name="chevron-down" size={16} color={colors.primary} />
    </Pressable>
    <Modal visible={open} transparent animationType={width < 700 ? 'slide' : 'fade'}
      onRequestClose={() => setOpen(false)} accessibilityViewIsModal>
      <View style={[styles.layer, width >= 700 && styles.wide]}>
        <View style={styles.backdrop} />
        <View style={[styles.sheet, { maxHeight: height - insets.top - 24, paddingBottom: insets.bottom }, width >= 700 && styles.dialog]}>
          <View style={styles.header}><Heading>Choose a shelf</Heading>
            <Pressable accessibilityRole="button" accessibilityLabel="Close shelf picker" onPress={() => setOpen(false)} style={styles.close}>
              <Ionicons name="close" size={24} color={colors.primary} />
            </Pressable>
          </View>
          <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.options}>
            <View accessibilityRole="radiogroup" accessibilityLabel="Count shelf">
              {option({ id: '', name: 'All shelves' })}
              {option({ id: 'unassigned', name: 'No shelf assigned' })}
              {(localChoices || resource.data?.items || []).map(shelf => option({ id: shelf.id, name: shelf.name }))}
            </View>
            {!choices && resource.loading ? <Loading label="Loading shelves…" /> : !choices && resource.error ? <LoadError {...resource} /> : null}
            {!resource.loading && (localChoices || resource.data?.items)?.length === 0 ? <Body muted>No shelves on this page.</Body> : null}
            <Pages next={choices ? localNext : resource.data?.nextCursor ?? null} cursor={cursor} setCursor={setCursor} disabled={!choices && resource.loading} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  </>;
}

const styles = StyleSheet.create({
  trigger: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44, flexShrink: 1, paddingVertical: 8 },
  label: { flexShrink: 1, fontSize: 16, fontWeight: '600', color: colors.ink },
  layer: { flex: 1, justifyContent: 'flex-end' }, wide: { alignItems: 'center', justifyContent: 'center', padding: 24 },
  backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' },
  sheet: { width: '100%', backgroundColor: colors.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, overflow: 'hidden' },
  dialog: { maxWidth: 520, borderRadius: 24 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, gap: 12, borderBottomWidth: 1, borderBottomColor: colors.line },
  close: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  options: { padding: 16, gap: 12 }, option: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12, borderRadius: 10 },
  optionText: { flex: 1, fontSize: 16, color: colors.ink }, pressed: { backgroundColor: colors.soft },
});
