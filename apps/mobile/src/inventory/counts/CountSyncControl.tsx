import React, { useState } from 'react';
import { Alert, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Body, Button, Heading, Notice } from '../../ui/components';
import { colors } from '../../ui/theme';
import { useTask } from '../../ui/useTask';
import { useOfflineCount } from './OfflineCountsProvider';
import { quantityLabel } from './measurements';
import { Pages } from '../shared';

/** Routine status is an icon. Details and recovery appear only when requested. */
export function CountSyncControl() {
  const queue = useOfflineCount();
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState('');
  const task = useTask();
  const pending = queue.pendingLineIds.length > 0;
  const conflicts = Object.keys(queue.conflicts);
  const incomplete = !!queue.count && (queue.count.totalLines > queue.lines.length || !!queue.count.catalogProductsAvailable);
  const waiting = pending || incomplete || queue.syncing || !!queue.error || queue.status !== 'ready';
  const resolve = (lineId: string, choice: 'local' | 'server') => Alert.alert(
    choice === 'local' ? 'Replace the saved count?' : 'Discard your queued count?',
    choice === 'local' ? 'Your amount will replace the latest entry for this product and shelf.'
      : 'Your queued amount will be removed. The server’s latest count will be kept.',
    [{ text: 'Cancel', style: 'cancel' }, { text: choice === 'local' ? 'Use my count' : 'Use server count',
      style: choice === 'server' ? 'destructive' : 'default',
      onPress: () => { void task.run(() => queue.controller.resolve(lineId, choice)); } }],
  );
  const offset = Number(cursor || 0);
  return <>
    <Pressable accessibilityRole="button" accessibilityLabel={waiting ? conflicts.length ? 'Saved counts need attention' : 'Counts waiting to sync' : 'All saved entries synced'}
      onPress={() => setOpen(true)} style={styles.icon}>
      <Ionicons name={waiting ? 'sync-outline' : 'checkmark-circle-outline'} size={25}
        color={conflicts.length ? colors.danger : waiting ? colors.primary : colors.success} />
    </Pressable>
    <Modal visible={open} transparent animationType="fade" onRequestClose={() => { if (!task.pending) setOpen(false); }} accessibilityViewIsModal>
      <View style={styles.layer}><View style={styles.dialog}>
        <View style={styles.header}><Heading>Saved counts</Heading><Pressable accessibilityRole="button" accessibilityLabel="Close saved counts"
          disabled={task.pending} onPress={() => setOpen(false)} style={styles.icon}><Ionicons name="close" size={24} color={colors.primary} /></Pressable></View>
        <ScrollView contentContainerStyle={styles.content}>
          <Body>{pending ? 'Your entries are saved on this device. Keep Shiftly open with a connection to sync them before review.'
            : incomplete ? 'Connect to load the additional catalog products. Your saved entries are safe.' : 'Every saved entry has reached Shiftly.'}</Body>
          <Notice message={task.error || queue.error} kind="error" />
          {conflicts.slice(offset, offset + 40).map(id => {
            const line = queue.lines.find(item => item.id === id);
            return <View key={id} style={styles.conflict}>
              <Heading>{line?.name || 'Count entry'}</Heading><Body muted>{line?.shelfName}</Body>
              <Body>Your count: {line ? quantityLabel(line.quantity, line.baseUnit) : 'Unavailable'}</Body>
              <Notice message={queue.conflicts[id] ?? null} kind="error" />
              <Button title="Keep my count" disabled={task.pending} onPress={() => resolve(id, 'local')} />
              <Button title="Use server count" variant="secondary" disabled={task.pending} onPress={() => resolve(id, 'server')} />
            </View>;
          })}
          <Pages cursor={cursor} next={offset + 40 < conflicts.length ? String(offset + 40) : null} setCursor={setCursor} />
          <Button title="Sync now" loading={task.pending || queue.syncing} onPress={() => { void task.run(() => queue.controller.sync()); }} />
        </ScrollView>
      </View></View>
    </Modal>
  </>;
}
const styles = StyleSheet.create({
  icon: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  layer: { flex: 1, backgroundColor: 'rgba(45,28,18,0.42)', justifyContent: 'center', alignItems: 'center', padding: 24 },
  dialog: { width: '100%', maxWidth: 520, maxHeight: '85%', backgroundColor: colors.paper, borderRadius: 24, overflow: 'hidden' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderColor: colors.line },
  content: { padding: 16, gap: 14 }, conflict: { paddingVertical: 14, gap: 10, borderTopWidth: 1, borderColor: colors.line },
});
