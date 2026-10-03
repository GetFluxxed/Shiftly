import React from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Button, Field, Heading, Notice } from '@/src/ui/components';
import { colors } from '@/src/ui/theme';
import { useRememberedState } from '@/src/restoration/WorkspaceProvider';
import { ApiError } from '@/src/api/client';
import { type Shelf } from './api';
import { useInventory } from './shared';

export function ShelfNameModal({ item, onClose, onSaved, onLatest }: {
  item: Shelf | null; onClose: () => void; onSaved: () => void; onLatest: (item: Shelf) => void;
}) {
  if (!item) return null;
  return <ShelfNameEditor key={item.id} item={item} onClose={onClose} onSaved={onSaved} onLatest={onLatest} />;
}

function ShelfNameEditor({ item, onClose, onSaved, onLatest }: {
  item: Shelf; onClose: () => void; onSaved: () => void; onLatest: (item: Shelf) => void;
}) {
  const { api, identity, canConfigure } = useInventory();
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [draft, setDraft, reset] = useRememberedState(`inventory.shelf.${item.id}.edit`, { name: item.name }, item.id);
  const [saving, setSaving] = React.useState(false);
  const [reloading, setReloading] = React.useState(false);
  const [stale, setStale] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const locked = saving || reloading;
  const close = () => { if (locked) return; reset(); setError(null); setStale(false); onClose(); };
  const save = async () => {
    const name = draft.name.trim();
    if (!name || name === item.name || locked) return;
    setSaving(true); setError(null);
    try {
      await api.editShelf(item, name, identity);
      reset(); onSaved();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'This shelf name could not be saved.');
      setStale(failure instanceof ApiError && failure.code === 'stale_record');
    } finally { setSaving(false); }
  };
  const reload = async () => {
    setReloading(true); setError(null);
    try { const latest = await api.shelf(item.id); onLatest(latest); setStale(false); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'The latest shelf could not be loaded.'); }
    finally { setReloading(false); }
  };
  if (!canConfigure) return null;
  const phone = width < 700;
  return <Modal visible transparent animationType={phone ? 'slide' : 'fade'} statusBarTranslucent onRequestClose={close} accessibilityViewIsModal>
    <View style={[styles.layer, phone ? styles.phoneLayer : styles.wideLayer]}>
      <View style={styles.backdrop} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[styles.dialog, phone ? [styles.sheet, { maxHeight: Math.max(0, height - insets.top - 12), paddingBottom: insets.bottom }] : [styles.centered, { maxHeight: Math.max(0, height - insets.top - insets.bottom - 48) }]]}>
        <View style={styles.header}><View style={styles.headerTitle}><Heading>Edit shelf name</Heading></View><Pressable accessibilityRole="button" accessibilityLabel="Close shelf name editor" accessibilityState={{ disabled: locked }} disabled={locked} onPress={close} style={styles.close}><Ionicons name="close" size={24} color={locked ? colors.muted : colors.primary} /></Pressable></View>
        <ScrollView style={styles.scroll} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"><Notice message={error} kind="error" />
          <Field label="Shelf name" value={draft.name} onChangeText={name => setDraft({ name })} maxLength={120} editable={!locked} autoFocus />

          {stale ? <Button title="Reload shelf" variant="secondary" loading={reloading} disabled={saving} onPress={() => { void reload(); }} /> : null}
        </ScrollView>
        <View style={styles.footer}><View style={styles.button}><Button title="Cancel" variant="quiet" disabled={locked} onPress={close} /></View><View style={styles.button}><Button title="Save" loading={saving} disabled={locked || !draft.name.trim() || draft.name.trim() === item.name || stale} onPress={() => { void save(); }} /></View></View>
      </KeyboardAvoidingView>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  layer: { flex: 1 }, phoneLayer: { justifyContent: 'flex-end' }, wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 28 },
  backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' },
  dialog: { width: '100%', backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' },
  sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24 }, centered: { maxWidth: 520, borderRadius: 24 },
  header: { minHeight: 68, paddingHorizontal: 18, paddingVertical: 10, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  headerTitle: { flex: 1, minWidth: 0 }, close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  scroll: { flexShrink: 1 }, content: { padding: 18, gap: 14 }, footer: { flexShrink: 0, padding: 12, paddingHorizontal: 18, backgroundColor: colors.card, borderTopWidth: 1, borderTopColor: colors.line, flexDirection: 'row', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 8 },
  button: { flexGrow: 1, flexShrink: 1, minWidth: 112, maxWidth: 220 },
});
