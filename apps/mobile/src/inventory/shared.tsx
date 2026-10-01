import React, { useRef } from 'react';
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { colors } from '@/src/ui/theme';
import { Body, Button, Card, Field, Heading, Notice, Screen } from '@/src/ui/components';
import { useSession } from '@/src/session/SessionProvider';
import { inventoryApi, MutationIdentity } from './api';

export function useInventory() {
  const session = useSession();
  const { request } = session;
  const api = React.useMemo(() => inventoryApi(request), [request]);
  const identity = useRef(new MutationIdentity()).current;
  return { ...session, api, identity, canEdit: !!session.actor?.capabilities.includes('catalog.manage'),
    canConfigure: !!session.actor?.capabilities.includes('configuration.manage') };
}
const inventoryBackLabels = {
  '/inventory': 'Back to inventory', '/catalog': 'Back to catalog', '/stock': 'Back to current inventory', '/shelves': 'Back to Open Shelves',
} as const;
export function InventoryPage({ title, children, backTo = '/inventory' }: React.PropsWithChildren<{
  title: string; backTo?: keyof typeof inventoryBackLabels;
}>) {
  const { actor, stores } = useSession(); const router = useRouter();
  const allowed = actor?.capabilities.includes('inventory.view');
  const name = stores.find(s => s.storeId === actor?.storeId)?.storeName || 'Current store';
  return <Screen title={title} eyebrow="Inventory" subtitle={name} compact>
    <Button title={inventoryBackLabels[backTo]} variant="quiet" icon="arrow-back" onPress={() => router.replace(backTo)} />
    {allowed ? children : <Card><Heading>Access is limited</Heading><Body>Your account does not have inventory access at this store.</Body></Card>}
  </Screen>;
}
export { useLoaderResource as useInventoryResource } from '@/src/ui/useResource';
export function LoadError({ error, refresh }: { error: string | null; refresh: () => Promise<void> }) {
  return <Card><Notice message={error || 'This record is unavailable.'} kind="error" /><Button title="Reload" onPress={() => { void refresh(); }} /></Card>;
}
export function Pages({ next, setCursor, cursor, disabled = false }: { next: string | null; cursor: string; setCursor: (value: string) => void; disabled?: boolean }) {
  return <>{next ? <Button title="Next page" variant="secondary" disabled={disabled} onPress={() => setCursor(next)} /> : null}
    {cursor ? <Button title="Back to first page" variant="quiet" disabled={disabled} onPress={() => setCursor('')} /> : null}</>;
}

export function InventorySearch({ label, value, onChange, onSubmit, submitLabel, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void; onSubmit: () => void; submitLabel: string; disabled?: boolean;
}) {
  return <View style={searchStyles.row}>
    <View style={searchStyles.field}><Field label={label} value={value} onChangeText={onChange} maxLength={160}
      editable={!disabled} autoCorrect={false} returnKeyType="search" onSubmitEditing={() => { if (!disabled) onSubmit(); }} /></View>
    <Pressable accessibilityRole="button" accessibilityLabel={submitLabel} accessibilityState={{ disabled }}
      disabled={disabled} onPress={onSubmit}
      style={({ pressed }) => [searchStyles.button, pressed && { backgroundColor: colors.blush }, disabled && { opacity: 0.55 }]}>
      <Ionicons name="search-outline" size={22} color={colors.primary} accessible={false} />
    </Pressable>
  </View>;
}
const searchStyles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 }, field: { flex: 1, minWidth: 0 },
  button: { width: 48, height: 54, borderRadius: 12, borderWidth: 1, borderColor: colors.controlLine,
    backgroundColor: colors.soft, alignItems: 'center', justifyContent: 'center' },
});
