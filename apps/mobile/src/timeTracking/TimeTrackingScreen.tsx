import React from 'react';
import { AppState, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Text } from '@/src/ui/Typography';
import { Body, Button, Card, EmptyState, Field, Heading, Notice, Screen } from '@/src/ui/components';
import { colors, fonts } from '@/src/ui/theme';
import { useSession } from '@/src/session/SessionProvider';
import { useRememberedState, useWorkspaceCheckpoint } from '@/src/restoration/WorkspaceProvider';
import {
  MAX_MEMBERS, PRESETS, activeShift, addMember, clockIn, clockOut, elapsedMs, emptyState, formatDuration,
  isTrackingState, remainingMs, removeMember, renameMember, resetTimer, startTimer, workedTodayMs,
  type CrewMember, type TimerId, type TrackingState,
} from './model';

type Editor = { kind: 'add' } | { kind: 'edit'; memberId: string } | null;
type TimerDialog = { memberId: string; timerId: TimerId } | null;

function newId(prefix: string) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0] || '?';
  const last = words[words.length - 1] || first;
  return (words.length > 1 ? `${first.charAt(0)}${last.charAt(0)}` : first.slice(0, 2)).toUpperCase();
}

function safeMessage(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback; }

export function TimeTrackingScreen() {
  const { actor } = useSession();
  const router = useRouter();
  const checkpoint = useWorkspaceCheckpoint();
  const [tracking, setTracking] = useRememberedState('timeTracking.demo', emptyState, 'v1', isTrackingState);
  const [now, setNow] = React.useState(Date.now);
  const [editor, setEditor] = React.useState<Editor>(null);
  const [timerDialog, setTimerDialog] = React.useState<TimerDialog>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [deviceNotice, setDeviceNotice] = React.useState<string | null>(null);
  const [completion, setCompletion] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const pendingRef = React.useRef(false);
  const { width } = useWindowDimensions();

  React.useEffect(() => {
    const update = () => setNow(Date.now());
    const interval = setInterval(update, 1_000);
    const appState = AppState.addEventListener('change', state => { if (state === 'active') update(); });
    return () => { clearInterval(interval); appState.remove(); };
  }, []);

  const mutate = async (change: (state: TrackingState) => TrackingState, fallback: string): Promise<{ ok: boolean; message: string | null }> => {
    if (pendingRef.current) return { ok: false, message: 'Another change is still being saved. Try again in a moment.' };
    pendingRef.current = true; setPending(true);
    setError(null);
    try {
      let changed = false;
      setTracking(current => { const next = change(current); changed = next !== current; return next; });
      if (changed) {
        if (await checkpoint()) setDeviceNotice(null);
        else setDeviceNotice('Change kept while the app is open, but it could not save on this device. Keep the app open and try another change to save again.');
      }
      return { ok: true, message: null };
    } catch (failure) {
      const message = safeMessage(failure, fallback); setError(message); return { ok: false, message };
    } finally { pendingRef.current = false; setPending(false); }
  };

  if (actor?.role !== 'owner') return <Screen title="Time Tracking" eyebrow="Owner tools">
    <Notice message="Time tracking is available to business owners." kind="error" />
    <Button title="Back to Today" variant="secondary" icon="arrow-back" onPress={() => router.replace('/today')} />
  </Screen>;

  const selectedMember = editor?.kind === 'edit' ? tracking.members.find(member => member.id === editor.memberId) : undefined;
  const timerMember = timerDialog ? tracking.members.find(member => member.id === timerDialog.memberId) : undefined;
  return <Screen title="Time Tracking" eyebrow="Owner tools" subtitle="Run simple, device-only shift clocks for your crew." compact
    trailing={width < 520 ? <Pressable accessibilityRole="button" accessibilityLabel="Back to Today" onPress={() => router.replace('/today')} style={styles.headerBackIcon}><Ionicons name="arrow-back" size={24} color={colors.primary} /></Pressable> : <View style={styles.back}><Button title="Back to Today" variant="quiet" icon="arrow-back" onPress={() => router.replace('/today')} /></View>}>
    <Notice message={error} kind="error" />
    <Notice message={deviceNotice} kind="error" />
    <Notice message={completion} kind="success" />
    <Card style={styles.demoCard}>
      <View style={styles.demoIcon}><Ionicons name="phone-portrait-outline" size={23} color={colors.primary} /></View>
      <View style={styles.flex}><Text style={styles.demoLabel}>DEVICE DEMO</Text>
        <Body>Names need no accounts. Everything is saved on this device, and no push notifications are sent.</Body></View>
    </Card>
    <View style={styles.rosterHeader}><View style={styles.flex}><Heading>Crew</Heading><Text style={styles.count}>{tracking.members.filter(member => !!activeShift(member)).length} on shift · {formatDuration(tracking.members.reduce((total, member) => total + workedTodayMs(member, now), 0))} today</Text></View>
      <Button title="Add member" icon="person-add-outline" disabled={pending || tracking.members.length >= MAX_MEMBERS} onPress={() => { setError(null); setEditor({ kind: 'add' }); }} />
    </View>
    {tracking.members.length === 0 ? <Card><EmptyState icon="people-outline" title="No crew members yet" description="Add someone to start tracking a shift on this device." /></Card>
      : <View style={styles.list}>{tracking.members.map(member => <MemberCard key={member.id} member={member} now={now}
        disabled={pending} onEdit={() => { setError(null); setEditor({ kind: 'edit', memberId: member.id }); }}
        onClock={async () => { const shift = activeShift(member); await mutate(state => shift ? clockOut(state, member.id, Date.now()) : clockIn(state, member.id, newId('shift'), Date.now()), `Could not ${shift ? 'clock out' : 'clock in'} ${member.name}.`); }}
        onTimer={async timerId => {
          const shift = activeShift(member); if (!shift) return;
          if (shift.timers[timerId].startedAt !== null) { setTimerDialog({ memberId: member.id, timerId }); return; }
          setCompletion(null); await mutate(state => startTimer(state, member.id, timerId, Date.now()), 'The timer could not be started.');
        }} />)}</View>}
    <Text style={styles.disclaimer}>Demo data clears on sign-out or store change.</Text>
    <MemberEditor editor={editor} member={selectedMember} disabled={pending} onClose={() => setEditor(null)} onSave={async name => {
      const result = await mutate(state => editor?.kind === 'edit' && selectedMember ? renameMember(state, selectedMember.id, name) : addMember(state, name, newId('member')), 'The crew member could not be saved.');
      if (result.ok) setEditor(null); return result.message;
    }} onRemove={selectedMember ? async () => { const result = await mutate(state => removeMember(state, selectedMember.id), 'The crew member could not be removed.'); if (result.ok) setEditor(null); return result.message; } : undefined} />
    <TimerModal value={timerDialog} member={timerMember} now={now} onClose={() => setTimerDialog(null)} onReset={timerDialog ? async () => {
      const preset = PRESETS.find(item => item.id === timerDialog.timerId)!;
      const wasComplete = !!timerMember && !!activeShift(timerMember) && remainingMs(activeShift(timerMember)!, timerDialog.timerId, Date.now()) === 0;
      const result = await mutate(state => resetTimer(state, timerDialog.memberId, timerDialog.timerId), 'The timer could not be reset.');
      if (result.ok) { setTimerDialog(null); setCompletion(wasComplete ? `${timerMember?.name}'s ${preset.label} timer is ready to start again.` : null); }
      return result.ok;
    } : undefined} />
  </Screen>;
}

function MemberCard({ member, now, disabled, onEdit, onClock, onTimer }: { member: CrewMember; now: number; disabled: boolean; onEdit: () => void; onClock: () => void; onTimer: (id: TimerId) => void }) {
  const shift = activeShift(member);
  const { width, fontScale } = useWindowDimensions();
  return <Card style={styles.memberCard}>
    <View style={styles.memberTop}><View style={styles.avatar}><Text style={styles.avatarText}>{initials(member.name)}</Text></View>
      <View style={styles.memberIdentity}><Text style={styles.memberName} numberOfLines={2}>{member.name}</Text><View style={styles.statusRow}><View style={[styles.dot, shift && styles.dotActive]} /><Text style={styles.status}>{shift ? 'On shift' : 'Off shift'}</Text></View></View>
      <Pressable accessibilityRole="button" accessibilityLabel={`Edit ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onEdit} style={({ pressed }) => [styles.overflow, disabled && styles.disabled, pressed && styles.pressed]}><Ionicons name="ellipsis-horizontal" size={24} color={colors.primary} /></Pressable>
    </View>
    <View style={styles.shiftRow}><View style={styles.flex}><Text style={styles.metaLabel}>{shift ? 'CURRENT SHIFT' : 'WORKED TODAY'}</Text><Text style={styles.shiftTime}>{formatDuration(shift ? elapsedMs(shift, now) : workedTodayMs(member, now))}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={`${shift ? 'Clock out' : 'Clock in'} ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onClock} style={({ pressed }) => [styles.clockButton, shift ? styles.clockSecondary : styles.clockPrimary, disabled && styles.disabled, pressed && styles.pressed]}><Text style={[styles.clockButtonText, !shift && styles.clockPrimaryText]}>{shift ? 'Clock out' : 'Clock in'}</Text></Pressable></View>
    <View style={[styles.timerGrid, (width < 390 || fontScale >= 1.45) && styles.timerGridStack]}>{PRESETS.map(preset => {
      const remaining = shift ? remainingMs(shift, preset.id, now) : preset.durationMs;
      const running = !!shift && shift.timers[preset.id].startedAt !== null;
      const complete = running && remaining === 0;
      const progress = running ? Math.min(1, 1 - remaining / preset.durationMs) : 0;
      const spokenDuration = preset.id === 'short' ? '3 hours 30 minutes' : '5 hours 30 minutes';
      return <Pressable key={preset.id} accessibilityRole="button" accessibilityLiveRegion={complete ? 'polite' : 'none'} accessibilityLabel={`${member.name}, ${spokenDuration} timer, ${!shift ? 'disabled' : complete ? 'complete' : running ? `${formatDuration(remaining)} remaining` : 'ready'}`}
        accessibilityState={{ disabled: disabled || !shift }} disabled={disabled || !shift} onPress={() => onTimer(preset.id)} style={({ pressed }) => [styles.timer, (disabled || !shift) && styles.disabled, running && styles.timerRunning, complete && styles.timerComplete, pressed && styles.pressed]}>
        <View style={styles.timerLabelRow}><Text style={styles.timerLabel}>{preset.label}</Text><Text style={[styles.timerState, complete && styles.completeText]}>{complete ? 'Complete' : running ? 'Running' : 'Ready'}</Text></View>
        <Text style={[styles.timerTime, complete && styles.completeText]}>{formatDuration(remaining)}</Text>
        <View style={styles.track}><View style={[styles.progress, complete && styles.progressComplete, { width: `${progress * 100}%` }]} /></View>
      </Pressable>;
    })}</View>
  </Card>;
}

function MemberEditor({ editor, member, disabled, onClose, onSave, onRemove }: { editor: Editor; member?: CrewMember; disabled: boolean; onClose: () => void; onSave: (name: string) => Promise<string | null>; onRemove?: () => Promise<string | null> }) {
  const [name, setName] = React.useState(''); const [saving, setSaving] = React.useState(false); const [error, setError] = React.useState<string | null>(null); const [confirming, setConfirming] = React.useState(false);
  React.useEffect(() => { if (editor) { setName(member?.name || ''); setError(null); setConfirming(false); } }, [editor, member?.id]);
  if (!editor) return null;
  const save = async () => { setSaving(true); setError(null); try { setError(await onSave(name)); } finally { setSaving(false); } };
  const remove = async () => { if (!onRemove) return; setSaving(true); setError(null); try { setError(await onRemove()); } finally { setSaving(false); } };
  const locked = saving || disabled;
  return <ResponsiveModal visible title={editor.kind === 'add' ? 'Add crew member' : confirming ? 'Remove crew member?' : 'Crew member'} onClose={onClose} locked={locked}>
    <Notice message={error} kind="error" />
    {confirming && member ? <><Body>Remove {member.name} and all saved shift history from this device?</Body>{activeShift(member) ? <Notice message={`${member.name} has an active shift. Removing them will discard it.`} kind="error" /> : null}</>
      : <><Field label="Name" value={name} onChangeText={setName} maxLength={60} editable={!locked} autoFocus selectTextOnFocus={editor.kind === 'edit'} placeholder="Crew member name" />
        {member ? <History member={member} /> : null}</>}
    <View style={styles.modalActions}>
      {confirming ? <><Button title="Keep member" variant="quiet" disabled={locked} onPress={() => setConfirming(false)} /><Button title={`Remove ${member?.name || 'member'}`} variant="danger" loading={saving} disabled={disabled} onPress={() => { void remove(); }} /></>
        : <><Button title="Cancel" variant="quiet" disabled={locked} onPress={onClose} />{member ? <Button title="Remove member" variant="danger" disabled={locked} onPress={() => setConfirming(true)} /> : null}<Button title="Save" loading={saving} disabled={locked || !name.trim() || name.trim() === member?.name} onPress={() => { void save(); }} /></>}
    </View>
  </ResponsiveModal>;
}

function History({ member }: { member: CrewMember }) {
  const recent = member.shifts.filter(shift => shift.clockOut !== null).slice(0, 10);
  const stamp = (value: number) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  return <View style={styles.history}><Text style={styles.metaLabel}>RECENT SHIFTS · UP TO 10 SAVED</Text>{recent.length ? recent.map(shift => <View key={shift.id} style={styles.historyRow}><View style={styles.flex}><Text style={styles.historyDate}>{stamp(shift.clockIn)}</Text><Text style={styles.historyRange}>to {stamp(shift.clockOut!)}</Text></View><Text style={styles.historyDuration}>{formatDuration(elapsedMs(shift, shift.clockOut!))}</Text></View>) : <Body muted>No completed shifts yet.</Body>}</View>;
}

function TimerModal({ value, member, now, onClose, onReset }: { value: TimerDialog; member?: CrewMember; now: number; onClose: () => void; onReset?: () => Promise<boolean> }) {
  const [saving, setSaving] = React.useState(false); if (!value || !member) return null;
  const shift = activeShift(member); if (!shift) return null;
  const preset = PRESETS.find(item => item.id === value.timerId)!; const remaining = remainingMs(shift, value.timerId, now); const complete = remaining === 0;
  return <ResponsiveModal visible title={`${preset.label} timer`} onClose={onClose} locked={saving}>
    <View style={styles.timerDialog}><Text style={styles.metaLabel}>{member.name}</Text><Text style={[styles.dialogTime, complete && styles.completeText]}>{formatDuration(remaining)}</Text><Body muted>{complete ? 'Timer complete. Reset it when you are ready to use it again.' : 'Reset clears this timer. You can start it again from the crew card.'}</Body></View>
    <View style={styles.modalActions}><Button title="Cancel" variant="quiet" disabled={saving} onPress={onClose} /><Button title={complete ? 'Reset timer' : 'Reset'} variant="danger" loading={saving} onPress={() => { setSaving(true); void onReset?.().finally(() => setSaving(false)); }} /></View>
  </ResponsiveModal>;
}

function ResponsiveModal({ visible, title, locked, onClose, children }: React.PropsWithChildren<{ visible: boolean; title: string; locked: boolean; onClose: () => void }>) {
  const { width, height } = useWindowDimensions(); const insets = useSafeAreaInsets(); const phone = width < 700;
  return <Modal visible={visible} transparent animationType={phone ? 'slide' : 'fade'} statusBarTranslucent onRequestClose={() => { if (!locked) onClose(); }} accessibilityViewIsModal>
    <View style={[styles.layer, phone ? styles.phoneLayer : styles.wideLayer]}><View style={styles.backdrop} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[styles.dialog, phone ? [styles.sheet, { maxHeight: height - insets.top - 12, paddingBottom: insets.bottom }] : [styles.centered, { maxHeight: height - insets.top - insets.bottom - 48 }]]}>
        <View style={styles.modalHeader}><Text accessibilityRole="header" style={styles.modalTitle}>{title}</Text><Pressable accessibilityRole="button" accessibilityLabel="Close" accessibilityState={{ disabled: locked }} disabled={locked} onPress={onClose} style={styles.close}><Ionicons name="close" size={24} color={locked ? colors.muted : colors.primary} /></Pressable></View>
        <ScrollView contentContainerStyle={styles.modalContent} keyboardShouldPersistTaps="handled">{children}</ScrollView>
      </KeyboardAvoidingView>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  flex: { flex: 1, minWidth: 0 }, back: { maxWidth: 190, flexShrink: 1 }, headerBackIcon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }, pressed: { opacity: 0.7 }, disabled: { opacity: 0.48 }, list: { gap: 14 },
  demoCard: { flexDirection: 'row', alignItems: 'flex-start', gap: 14, padding: 18 }, demoIcon: { width: 46, height: 46, borderRadius: 15, backgroundColor: colors.blush, alignItems: 'center', justifyContent: 'center' }, demoLabel: { fontSize: 11, lineHeight: 16, letterSpacing: 1.4, fontWeight: '700', color: colors.primary, marginBottom: 4 },
  rosterHeader: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 14 }, count: { fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: 2 }, disclaimer: { color: colors.muted, fontSize: 13, lineHeight: 20, textAlign: 'center', paddingVertical: 8 },
  memberCard: { padding: 18, gap: 16 }, memberTop: { flexDirection: 'row', alignItems: 'center', gap: 12 }, avatar: { width: 48, height: 48, borderRadius: 16, backgroundColor: colors.blush, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }, avatarText: { fontFamily: fonts.strong, fontSize: 16, color: colors.primary }, memberIdentity: { flex: 1, minWidth: 0 }, memberName: { fontFamily: fonts.display, fontSize: 23, lineHeight: 27, color: colors.ink }, statusRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 4 }, dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.controlLine }, dotActive: { backgroundColor: colors.success }, status: { color: colors.muted, fontSize: 13, lineHeight: 18 }, overflow: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  shiftRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12 }, metaLabel: { color: colors.muted, fontSize: 11, lineHeight: 16, letterSpacing: 1.25, fontWeight: '700' }, shiftTime: { color: colors.ink, fontSize: 20, lineHeight: 26, fontWeight: '600', fontVariant: ['tabular-nums'] }, clockButton: { minWidth: 132, minHeight: 52, borderRadius: 27, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center' }, clockPrimary: { backgroundColor: colors.primary }, clockSecondary: { backgroundColor: colors.soft, borderWidth: 1, borderColor: colors.controlLine }, clockButtonText: { color: colors.primary, fontWeight: '700', fontSize: 16 }, clockPrimaryText: { color: colors.onPrimary },
  timerGrid: { flexDirection: 'row', gap: 10 }, timerGridStack: { flexDirection: 'column' }, timer: { flex: 1, minWidth: 0, minHeight: 112, borderRadius: 15, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.paper, padding: 13, justifyContent: 'space-between', gap: 7 }, timerRunning: { borderColor: colors.accentStrong, backgroundColor: colors.blush }, timerComplete: { borderColor: colors.success, backgroundColor: colors.successPaper }, timerLabelRow: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }, timerLabel: { color: colors.primary, fontSize: 14, fontWeight: '700' }, timerState: { color: colors.muted, fontSize: 11, lineHeight: 16 }, timerTime: { color: colors.ink, fontSize: 18, lineHeight: 24, fontWeight: '700', fontVariant: ['tabular-nums'] }, completeText: { color: colors.success }, track: { height: 4, borderRadius: 2, backgroundColor: colors.line, overflow: 'hidden' }, progress: { height: 4, backgroundColor: colors.accentStrong }, progressComplete: { backgroundColor: colors.success },
  layer: { flex: 1 }, phoneLayer: { justifyContent: 'flex-end' }, wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 28 }, backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' }, dialog: { width: '100%', backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }, sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24 }, centered: { maxWidth: 520, borderRadius: 24 }, modalHeader: { minHeight: 68, paddingHorizontal: 18, paddingVertical: 10, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', alignItems: 'center', gap: 8 }, modalTitle: { flex: 1, minWidth: 0, fontFamily: fonts.display, fontSize: 25, lineHeight: 30, color: colors.ink }, close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' }, modalContent: { padding: 18, gap: 16 }, modalActions: { flexDirection: 'row', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 8 },
  history: { gap: 10, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 16 }, historyRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: 10 }, historyDate: { color: colors.ink, fontWeight: '600', fontSize: 14 }, historyRange: { color: colors.muted, fontSize: 13, lineHeight: 20 }, historyDuration: { color: colors.primary, fontWeight: '700', fontVariant: ['tabular-nums'] }, timerDialog: { alignItems: 'center', gap: 8, paddingVertical: 8 }, dialogTime: { fontFamily: fonts.display, color: colors.ink, fontSize: 45, lineHeight: 52, fontVariant: ['tabular-nums'] },
});
