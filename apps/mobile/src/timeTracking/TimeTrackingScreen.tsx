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
  BREAK_PRESETS, MAX_MEMBERS, PRESETS, activeShift, addMember, breakRemainingMs, clockIn, clockOut, elapsedMs, emptyState, formatDuration,
  isTrackingState, remainingMs, removeMember, renameMember, resetBreakTimer, resetTimer, startBreakTimer, startTimer, workedTodayMs,
  type BreakTimerId, type CrewMember, type TimerId, type TrackingState,
} from './model';

type Editor = { kind: 'add' } | { kind: 'edit' | 'detail'; memberId: string; timerId?: TimerId } | null;

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

  const selectedMember = editor && editor.kind !== 'add' ? tracking.members.find(member => member.id === editor.memberId) : undefined;
  const compactRoster = tracking.members.length >= 4;
  const editorKey = editor?.kind === 'add' ? 'add' : editor ? `${editor.kind}:${editor.memberId}:${editor.timerId || ''}` : '';
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
    {tracking.members.length ? <Text style={styles.rosterHint}>Tap a name for timers and shift details.</Text> : null}
    {tracking.members.length === 0 ? <Card><EmptyState icon="people-outline" title="No crew members yet" description="Add someone to start tracking a shift on this device." /></Card>
      : <View style={styles.list}>{tracking.members.map(member => compactRoster ? <CompactMemberRow key={member.id} member={member} now={now} disabled={pending}
        onDetail={() => { setError(null); setEditor({ kind: 'detail', memberId: member.id }); }}
        onClock={async () => { const shift = activeShift(member); await mutate(state => shift ? clockOut(state, member.id, Date.now()) : clockIn(state, member.id, newId('shift'), Date.now()), `Could not ${shift ? 'clock out' : 'clock in'} ${member.name}.`); }} /> : <MemberCard key={member.id} member={member} now={now}
        disabled={pending} onDetail={() => { setError(null); setEditor({ kind: 'detail', memberId: member.id }); }} onEdit={() => { setError(null); setEditor({ kind: 'edit', memberId: member.id }); }}
        onClock={async () => { const shift = activeShift(member); await mutate(state => shift ? clockOut(state, member.id, Date.now()) : clockIn(state, member.id, newId('shift'), Date.now()), `Could not ${shift ? 'clock out' : 'clock in'} ${member.name}.`); }}
        onTimer={async timerId => {
          const shift = activeShift(member); if (!shift) return;
          if (shift.timers[timerId].startedAt !== null) { setEditor({ kind: 'detail', memberId: member.id, timerId }); return; }
          setCompletion(null); await mutate(state => startTimer(state, member.id, timerId, Date.now()), 'The timer could not be started.');
        }} />)}</View>}
    <Text style={styles.disclaimer}>Demo data clears on sign-out or store change.</Text>
    {editor ? <MemberEditor key={editorKey} editor={editor} member={selectedMember} now={now} disabled={pending} onClose={() => setEditor(null)} onSave={async name => {
      const result = await mutate(state => selectedMember ? renameMember(state, selectedMember.id, name) : addMember(state, name, newId('member')), 'The crew member could not be saved.');
      if (result.ok && editor?.kind === 'add') setEditor(null); return result.message;
    }} onRemove={selectedMember ? async () => { const result = await mutate(state => removeMember(state, selectedMember.id), 'The crew member could not be removed.'); if (result.ok) setEditor(null); return result.message; } : undefined}
      onClock={selectedMember ? async () => { const shift = activeShift(selectedMember); return (await mutate(state => shift ? clockOut(state, selectedMember.id, Date.now()) : clockIn(state, selectedMember.id, newId('shift'), Date.now()), `Could not ${shift ? 'clock out' : 'clock in'} ${selectedMember.name}.`)).message; } : undefined}
      onTimer={selectedMember ? async timerId => { const shift = activeShift(selectedMember); if (!shift) return null; setCompletion(null); return (await mutate(state => startTimer(state, selectedMember.id, timerId, Date.now()), 'The timer could not be started.')).message; } : undefined}
      onReset={selectedMember ? async timerId => { const shift = activeShift(selectedMember); const preset = PRESETS.find(item => item.id === timerId)!; const wasComplete = !!shift && remainingMs(shift, timerId, Date.now()) === 0; const result = await mutate(state => resetTimer(state, selectedMember.id, timerId), 'The timer could not be reset.'); if (result.ok) setCompletion(wasComplete ? `${selectedMember.name}'s ${preset.label} timer is ready to start again.` : null); return result.message; } : undefined}
      onBreakTimer={selectedMember ? async timerId => {
        const shift = activeShift(selectedMember);
        if (!shift) return null;
        const result = await mutate(state => startBreakTimer(state, selectedMember.id, timerId, Date.now()), 'The break timer could not be started.');
        return result.message;
      } : undefined}
      onResetBreak={selectedMember ? async timerId => {
        const result = await mutate(state => resetBreakTimer(state, selectedMember.id, timerId), 'The break timer could not be reset.');
        return result.message;
      } : undefined} /> : null}
  </Screen>;
}

function MemberCard({ member, now, disabled, onDetail, onEdit, onClock, onTimer }: { member: CrewMember; now: number; disabled: boolean; onDetail: () => void; onEdit: () => void; onClock: () => void; onTimer: (id: TimerId) => void }) {
  const shift = activeShift(member);
  return <Card style={styles.memberCard}>
    <View style={styles.memberTop}><Pressable accessibilityRole="button" accessibilityLabel={`View ${member.name} timers and shift details`} accessibilityState={{ disabled }} disabled={disabled} onPress={onDetail} style={({ pressed }) => [styles.memberDetailButton, disabled && styles.disabled, pressed && styles.pressed]}><View style={styles.avatar}><Text style={styles.avatarText}>{initials(member.name)}</Text></View>
      <View style={styles.memberIdentity}><Text style={styles.memberName} numberOfLines={2}>{member.name}</Text><View style={styles.statusRow}><View style={[styles.dot, shift && styles.dotActive]} /><Text style={styles.status}>{shift ? 'On shift' : 'Off shift'}</Text></View></View></Pressable>
      <Pressable accessibilityRole="button" accessibilityLabel={`Edit ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onEdit} style={({ pressed }) => [styles.overflow, disabled && styles.disabled, pressed && styles.pressed]}><Ionicons name="ellipsis-horizontal" size={24} color={colors.primary} /></Pressable>
    </View>
    <View style={styles.shiftRow}><View style={styles.flex}><Text style={styles.metaLabel}>{shift ? 'CURRENT SHIFT' : 'WORKED TODAY'}</Text><Text style={styles.shiftTime}>{formatDuration(shift ? elapsedMs(shift, now) : workedTodayMs(member, now))}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={`${shift ? 'Clock out' : 'Clock in'} ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onClock} style={({ pressed }) => [styles.clockButton, shift ? styles.clockSecondary : styles.clockPrimary, disabled && styles.disabled, pressed && styles.pressed]}><Text style={[styles.clockButtonText, !shift && styles.clockPrimaryText]}>{shift ? 'Clock out' : 'Clock in'}</Text></Pressable></View>
    <TimerControls member={member} now={now} disabled={disabled} onTimer={onTimer} />
  </Card>;
}

function timerSummary(member: CrewMember, timerId: TimerId, now: number) {
  const shift = activeShift(member); const preset = PRESETS.find(item => item.id === timerId)!;
  if (!shift || shift.timers[timerId].startedAt === null) return `${preset.label} · Ready`;
  const remaining = remainingMs(shift, timerId, now);
  const minutes = Math.ceil(remaining / 60_000); const concise = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
  return remaining === 0 ? `${preset.label} · Complete` : `${preset.label} · ${concise} left`;
}

function compactDuration(ms: number) {
  const minutes = Math.floor(Math.max(0, ms) / 60_000);
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

function CompactMemberRow({ member, now, disabled, onDetail, onClock }: { member: CrewMember; now: number; disabled: boolean; onDetail: () => void; onClock: () => void }) {
  const shift = activeShift(member);
  const summary = PRESETS.map(preset => timerSummary(member, preset.id, now)).join(', ');
  return <Card style={styles.compactCard}>
    <Pressable accessibilityRole="button" accessibilityLabel={`View ${member.name} timers and shift details`} accessibilityHint={summary} accessibilityState={{ disabled }} disabled={disabled} onPress={onDetail} style={({ pressed }) => [styles.compactDetail, disabled && styles.disabled, pressed && styles.pressed]}>
      <Text style={styles.compactName} numberOfLines={2}>{member.name}</Text>
      <View style={styles.compactStatus}><View style={[styles.dot, shift && styles.dotActive]} /><Text style={styles.compactElapsed}>{shift ? `On shift · ${compactDuration(elapsedMs(shift, now))}` : `Off shift · ${compactDuration(workedTodayMs(member, now))} today`}</Text></View>
      {PRESETS.map(preset => <Text key={preset.id} style={[styles.compactTimer, !!shift && shift.timers[preset.id].startedAt !== null && remainingMs(shift, preset.id, now) === 0 && styles.completeText]}>{timerSummary(member, preset.id, now)}</Text>)}
    </Pressable>
    <Pressable accessibilityRole="button" accessibilityLabel={`${shift ? 'Clock out' : 'Clock in'} ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onClock} style={({ pressed }) => [styles.compactClock, shift ? styles.clockSecondary : styles.clockPrimary, disabled && styles.disabled, pressed && styles.pressed]}><Text style={[styles.compactClockText, !shift && styles.clockPrimaryText]}>{shift ? 'Clock out' : 'Clock in'}</Text></Pressable>
  </Card>;
}

type EditorView = 'detail' | 'edit' | 'remove' | 'reset' | 'resetBreak';
type ActiveEditor = Exclude<Editor, null>;

function MemberEditor({ editor, member, now, disabled, onClose, onSave, onRemove, onClock, onTimer, onReset, onBreakTimer, onResetBreak }: { editor: ActiveEditor; member?: CrewMember; now: number; disabled: boolean; onClose: () => void; onSave: (name: string) => Promise<string | null>; onRemove?: () => Promise<string | null>; onClock?: () => Promise<string | null>; onTimer?: (timerId: TimerId) => Promise<string | null>; onReset?: (timerId: TimerId) => Promise<string | null>; onBreakTimer?: (timerId: BreakTimerId) => Promise<string | null>; onResetBreak?: (timerId: BreakTimerId) => Promise<string | null> }) {
  const [name, setName] = React.useState(member?.name || '');
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [view, setView] = React.useState<EditorView>(editor.kind === 'detail' ? (editor.timerId ? 'reset' : 'detail') : 'edit');
  const [resettingTimer, setResettingTimer] = React.useState<TimerId>(editor.kind !== 'add' && editor.timerId ? editor.timerId : 'short');
  const [resettingBreak, setResettingBreak] = React.useState<BreakTimerId>('ten');
  const run = async (action: () => Promise<string | null>, next?: EditorView) => {
    setSaving(true);
    setError(null);
    try {
      const message = await action();
      setError(message);
      if (!message && next) setView(next);
    } finally { setSaving(false); }
  };
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const message = await onSave(name);
      setError(message);
      if (!message && member) {
        if (editor.kind === 'detail') setView('detail');
        else onClose();
      }
    } finally { setSaving(false); }
  };
  const remove = async () => {
    if (!onRemove) return;
    setSaving(true);
    setError(null);
    try { setError(await onRemove()); } finally { setSaving(false); }
  };
  const handleTimer = (timerId: TimerId) => {
    if (!member) return;
    const shift = activeShift(member);
    if (!shift) return;
    if (shift.timers[timerId].startedAt !== null) {
      setResettingTimer(timerId);
      setView('reset');
      return;
    }
    if (onTimer) void run(() => onTimer(timerId));
  };
  const handleClock = () => { if (onClock) void run(onClock); };
  const handleReset = () => { if (onReset) void run(() => onReset(resettingTimer), 'detail'); };
  const handleBreakTimer = (timerId: BreakTimerId) => {
    if (!member) return;
    const shift = activeShift(member);
    if (!shift) return;
    if ((shift.breakTimers?.[timerId]?.startedAt ?? null) !== null) {
      setResettingBreak(timerId);
      setView('resetBreak');
      return;
    }
    if (onBreakTimer) void run(() => onBreakTimer(timerId));
  };
  const handleResetBreak = () => { if (onResetBreak) void run(() => onResetBreak(resettingBreak), 'detail'); };
  const beginEdit = () => { setName(member?.name || ''); setError(null); setView('edit'); };
  const cancelEdit = () => { setName(member?.name || ''); setError(null); setView('detail'); };
  const locked = saving || disabled;
  const breakLabel = BREAK_PRESETS.find(item => item.id === resettingBreak)!.label.replace('min', 'minute');
  const title = editor.kind === 'add' ? 'Add crew member' : view === 'remove' ? 'Remove crew member?' : view === 'reset' ? `${PRESETS.find(item => item.id === resettingTimer)!.label} timer` : view === 'resetBreak' ? `${breakLabel} break` : editor.kind === 'edit' ? 'Crew member' : member?.name || 'Crew member';
  return <ResponsiveModal visible title={title} onClose={onClose} locked={locked}>
    <Notice message={error} kind="error" />
    {view === 'detail' && member ? <MemberDetails member={member} now={now} disabled={locked} onClock={handleClock} onTimer={handleTimer} onBreakTimer={handleBreakTimer} /> : null}
    {view === 'edit' ? <><Field label="Name" value={name} onChangeText={setName} maxLength={60} editable={!locked} autoFocus selectTextOnFocus={!!member} placeholder="Crew member name" />{member ? <History member={member} /> : null}</> : null}
    {view === 'remove' && member ? <><Body>Remove {member.name} and all saved shift history from this device?</Body>{activeShift(member) ? <Notice message={`${member.name} has an active shift. Removing them will discard it.`} kind="error" /> : null}</> : null}
    {view === 'reset' && member ? <ResetTimerDetails member={member} timerId={resettingTimer} now={now} /> : null}
    {view === 'resetBreak' && member ? <ResetBreakDetails member={member} timerId={resettingBreak} now={now} /> : null}
    <View style={styles.modalActions}>{view === 'detail' ? <Button title="Edit member" variant="secondary" disabled={locked} onPress={beginEdit} />
      : view === 'remove' ? <><Button title="Keep member" variant="quiet" disabled={locked} onPress={() => setView('edit')} /><Button title={`Remove ${member?.name || 'member'}`} variant="danger" loading={saving} disabled={disabled} onPress={() => { void remove(); }} /></>
      : view === 'reset' ? <><Button title="Cancel" variant="quiet" disabled={locked} onPress={() => setView('detail')} /><Button title={member && activeShift(member) && remainingMs(activeShift(member)!, resettingTimer, now) === 0 ? 'Reset timer' : 'Reset'} variant="danger" loading={saving} disabled={disabled} onPress={handleReset} /></>
      : view === 'resetBreak' ? <><Button title="Cancel" variant="quiet" disabled={locked} onPress={() => setView('detail')} /><Button title="Reset break" variant="danger" loading={saving} disabled={disabled} onPress={handleResetBreak} /></>
      : <><Button title="Cancel" variant="quiet" disabled={locked} onPress={member && editor.kind === 'detail' ? cancelEdit : onClose} />{member ? <Button title="Remove member" variant="danger" disabled={locked} onPress={() => setView('remove')} /> : null}<Button title="Save" loading={saving} disabled={locked || !name.trim() || name.trim() === member?.name} onPress={() => { void save(); }} /></>}</View>
  </ResponsiveModal>;
}

function MemberDetails({ member, now, disabled, onClock, onTimer, onBreakTimer }: { member: CrewMember; now: number; disabled: boolean; onClock: () => void; onTimer: (timerId: TimerId) => void; onBreakTimer: (timerId: BreakTimerId) => void }) {
  const shift = activeShift(member);
  return <>
    <View style={styles.detailShift}>
      <View style={styles.flex}>
        <Text style={styles.metaLabel}>{shift ? 'CURRENT SHIFT' : 'WORKED TODAY'}</Text>
        <Text style={styles.shiftTime}>{formatDuration(shift ? elapsedMs(shift, now) : workedTodayMs(member, now))}</Text>
      </View>
      <Pressable accessibilityRole="button" accessibilityLabel={`${shift ? 'Clock out' : 'Clock in'} ${member.name}`} accessibilityState={{ disabled }} disabled={disabled} onPress={onClock}
        style={({ pressed }) => [styles.clockButton, shift ? styles.clockSecondary : styles.clockPrimary, disabled && styles.disabled, pressed && styles.pressed]}>
        <Text style={[styles.clockButtonText, !shift && styles.clockPrimaryText]}>{shift ? 'Clock out' : 'Clock in'}</Text>
      </Pressable>
    </View>
    <TimerControls member={member} now={now} disabled={disabled} onTimer={onTimer} />
    <BreakControls member={member} now={now} disabled={disabled} onTimer={onBreakTimer} />
    <History member={member} />
  </>;
}

function formatBreakDuration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1_000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

function BreakControls({ member, now, disabled, onTimer }: { member: CrewMember; now: number; disabled: boolean; onTimer: (timerId: BreakTimerId) => void }) {
  const shift = activeShift(member);
  const { width, fontScale } = useWindowDimensions();
  return <View style={styles.breakSection}>
    <View><Text style={styles.metaLabel}>BREAKS</Text><Body muted>Track a 10 or 30 minute break separately.</Body></View>
    <View style={[styles.breakGrid, (width < 390 || fontScale >= 1.45) && styles.timerGridStack]}>{BREAK_PRESETS.map(preset => {
      const startedAt = shift?.breakTimers?.[preset.id]?.startedAt ?? null;
      const remaining = shift ? breakRemainingMs(shift, preset.id, now) : preset.durationMs;
      const running = !!shift && startedAt !== null;
      const complete = running && remaining === 0;
      const spokenDuration = preset.id === 'ten' ? '10 minute' : '30 minute';
      const timerState = !shift ? 'disabled' : complete ? 'complete' : running ? `${formatBreakDuration(remaining)} remaining` : 'ready';
      return <Pressable key={preset.id} accessibilityRole="button" accessibilityLiveRegion={complete ? 'polite' : 'none'} accessibilityLabel={`${member.name}, ${spokenDuration} break, ${timerState}`}
        accessibilityState={{ disabled: disabled || !shift }} disabled={disabled || !shift} onPress={() => onTimer(preset.id)}
        style={({ pressed }) => [styles.breakTimer, (disabled || !shift) && styles.disabled, running && styles.timerRunning, complete && styles.timerComplete, pressed && styles.pressed]}>
        <View style={styles.timerLabelRow}><Text style={styles.timerLabel}>{preset.label}</Text><Text style={[styles.timerState, complete && styles.completeText]}>{complete ? 'Complete' : running ? 'Running' : 'Ready'}</Text></View>
        <Text style={[styles.breakTime, complete && styles.completeText]}>{formatBreakDuration(remaining)}</Text>
      </Pressable>;
    })}</View>
  </View>;
}

function TimerControls({ member, now, disabled, onTimer }: { member: CrewMember; now: number; disabled: boolean; onTimer: (timerId: TimerId) => void }) {
  const shift = activeShift(member);
  const { width, fontScale } = useWindowDimensions();
  return <View style={[styles.timerGrid, (width < 390 || fontScale >= 1.45) && styles.timerGridStack]}>
    {PRESETS.map(preset => {
      const remaining = shift ? remainingMs(shift, preset.id, now) : preset.durationMs;
      const running = !!shift && shift.timers[preset.id].startedAt !== null;
      const complete = running && remaining === 0;
      const progress = running ? Math.min(1, 1 - remaining / preset.durationMs) : 0;
      const spokenDuration = preset.id === 'short' ? '3 hours 30 minutes' : '5 hours 30 minutes';
      const timerState = !shift ? 'disabled' : complete ? 'complete' : running ? `${formatDuration(remaining)} remaining` : 'ready';
      return <Pressable key={preset.id} accessibilityRole="button" accessibilityLiveRegion={complete ? 'polite' : 'none'} accessibilityLabel={`${member.name}, ${spokenDuration} timer, ${timerState}`}
        accessibilityState={{ disabled: disabled || !shift }} disabled={disabled || !shift} onPress={() => onTimer(preset.id)}
        style={({ pressed }) => [styles.timer, (disabled || !shift) && styles.disabled, running && styles.timerRunning, complete && styles.timerComplete, pressed && styles.pressed]}>
        <View style={styles.timerLabelRow}><Text style={styles.timerLabel}>{preset.label}</Text><Text style={[styles.timerState, complete && styles.completeText]}>{complete ? 'Complete' : running ? 'Running' : 'Ready'}</Text></View>
        <Text style={[styles.timerTime, complete && styles.completeText]}>{formatDuration(remaining)}</Text>
        <View style={styles.track}><View style={[styles.progress, complete && styles.progressComplete, { width: `${progress * 100}%` }]} /></View>
      </Pressable>;
    })}
  </View>;
}

function ResetTimerDetails({ member, timerId, now }: { member: CrewMember; timerId: TimerId; now: number }) {
  const shift = activeShift(member); if (!shift) return null; const remaining = remainingMs(shift, timerId, now); const complete = remaining === 0;
  return <View style={styles.timerDialog}><Text style={styles.metaLabel}>{member.name}</Text><Text style={[styles.dialogTime, complete && styles.completeText]}>{formatDuration(remaining)}</Text><Body muted>{complete ? 'Timer complete. Reset it when you are ready to use it again.' : 'Reset clears this timer. You can start it again from the person details.'}</Body></View>;
}

function ResetBreakDetails({ member, timerId, now }: { member: CrewMember; timerId: BreakTimerId; now: number }) {
  const shift = activeShift(member);
  if (!shift) return null;
  const remaining = breakRemainingMs(shift, timerId, now);
  const complete = remaining === 0;
  return <View style={styles.timerDialog}>
    <Text style={styles.metaLabel}>{member.name}</Text>
    <Text style={[styles.dialogTime, complete && styles.completeText]}>{formatBreakDuration(remaining)}</Text>
    <Body muted>{complete ? 'Break complete. Reset it when you are ready to use it again.' : 'Reset clears this break timer without changing shift hours or other timers.'}</Body>
  </View>;
}

function History({ member }: { member: CrewMember }) {
  const recent = member.shifts.filter(shift => shift.clockOut !== null).slice(0, 10);
  const stamp = (value: number) => new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  return <View style={styles.history}><Text style={styles.metaLabel}>RECENT SHIFTS · UP TO 10 SAVED</Text>{recent.length ? recent.map(shift => <View key={shift.id} style={styles.historyRow}><View style={styles.flex}><Text style={styles.historyDate}>{stamp(shift.clockIn)}</Text><Text style={styles.historyRange}>to {stamp(shift.clockOut!)}</Text></View><Text style={styles.historyDuration}>{formatDuration(elapsedMs(shift, shift.clockOut!))}</Text></View>) : <Body muted>No completed shifts yet.</Body>}</View>;
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
  rosterHeader: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 14 }, count: { fontSize: 14, lineHeight: 21, color: colors.muted, marginTop: 2 }, rosterHint: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 3 }, disclaimer: { color: colors.muted, fontSize: 13, lineHeight: 20, textAlign: 'center', paddingVertical: 8 },
  compactCard: { padding: 0, flexDirection: 'row', alignItems: 'stretch', overflow: 'hidden' }, compactDetail: { flex: 1, minWidth: 0, minHeight: 100, paddingHorizontal: 12, paddingVertical: 12, justifyContent: 'center' }, compactName: { fontFamily: fonts.display, fontSize: 19, lineHeight: 23, color: colors.ink }, compactStatus: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2, minWidth: 0 }, compactElapsed: { flex: 1, minWidth: 0, color: colors.ink, fontSize: 13, lineHeight: 18, fontWeight: '600', fontVariant: ['tabular-nums'] }, compactTimer: { color: colors.muted, fontSize: 13, lineHeight: 18, fontVariant: ['tabular-nums'] }, compactClock: { minWidth: 88, minHeight: 48, marginHorizontal: 12, paddingHorizontal: 12, alignSelf: 'center', alignItems: 'center', justifyContent: 'center', borderRadius: 24 }, compactClockText: { color: colors.primary, fontWeight: '700', fontSize: 14, textAlign: 'center' },
  memberCard: { padding: 18, gap: 16 }, memberTop: { flexDirection: 'row', alignItems: 'center', gap: 4 }, memberDetailButton: { flex: 1, minWidth: 0, minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 16 }, avatar: { width: 48, height: 48, borderRadius: 16, backgroundColor: colors.blush, alignItems: 'center', justifyContent: 'center', flexShrink: 0 }, avatarText: { fontFamily: fonts.strong, fontSize: 16, color: colors.primary }, memberIdentity: { flex: 1, minWidth: 0 }, memberName: { fontFamily: fonts.display, fontSize: 23, lineHeight: 27, color: colors.ink }, statusRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: 4 }, dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.controlLine }, dotActive: { backgroundColor: colors.success }, status: { color: colors.muted, fontSize: 13, lineHeight: 18 }, overflow: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  shiftRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12 }, metaLabel: { color: colors.muted, fontSize: 11, lineHeight: 16, letterSpacing: 1.25, fontWeight: '700' }, shiftTime: { color: colors.ink, fontSize: 20, lineHeight: 26, fontWeight: '600', fontVariant: ['tabular-nums'] }, clockButton: { minWidth: 132, minHeight: 52, borderRadius: 27, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center' }, clockPrimary: { backgroundColor: colors.primary }, clockSecondary: { backgroundColor: colors.soft, borderWidth: 1, borderColor: colors.controlLine }, clockButtonText: { color: colors.primary, fontWeight: '700', fontSize: 16 }, clockPrimaryText: { color: colors.onPrimary },
  timerGrid: { flexDirection: 'row', gap: 10 }, timerGridStack: { flexDirection: 'column' }, timer: { flex: 1, minWidth: 0, minHeight: 112, borderRadius: 15, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.paper, padding: 13, justifyContent: 'space-between', gap: 7 }, timerRunning: { borderColor: colors.accentStrong, backgroundColor: colors.blush }, timerComplete: { borderColor: colors.success, backgroundColor: colors.successPaper }, timerLabelRow: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 }, timerLabel: { color: colors.primary, fontSize: 14, fontWeight: '700' }, timerState: { color: colors.muted, fontSize: 11, lineHeight: 16 }, timerTime: { color: colors.ink, fontSize: 18, lineHeight: 24, fontWeight: '700', fontVariant: ['tabular-nums'] }, completeText: { color: colors.success }, track: { height: 4, borderRadius: 2, backgroundColor: colors.line, overflow: 'hidden' }, progress: { height: 4, backgroundColor: colors.accentStrong }, progressComplete: { backgroundColor: colors.success },
  breakSection: { gap: 10, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 16 }, breakGrid: { flexDirection: 'row', gap: 10 }, breakTimer: { flex: 1, minWidth: 0, minHeight: 76, borderRadius: 15, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.paper, padding: 13, justifyContent: 'space-between', gap: 6 }, breakTime: { color: colors.ink, fontSize: 17, lineHeight: 22, fontWeight: '700', fontVariant: ['tabular-nums'] },
  layer: { flex: 1 }, phoneLayer: { justifyContent: 'flex-end' }, wideLayer: { justifyContent: 'center', alignItems: 'center', padding: 28 }, backdrop: { position: 'absolute', inset: 0, backgroundColor: 'rgba(45,28,18,0.42)' }, dialog: { width: '100%', backgroundColor: colors.paper, borderWidth: 1, borderColor: colors.line, overflow: 'hidden' }, sheet: { borderTopLeftRadius: 24, borderTopRightRadius: 24 }, centered: { maxWidth: 520, borderRadius: 24 }, modalHeader: { minHeight: 68, paddingHorizontal: 18, paddingVertical: 10, backgroundColor: colors.card, borderBottomWidth: 1, borderBottomColor: colors.line, flexDirection: 'row', alignItems: 'center', gap: 8 }, modalTitle: { flex: 1, minWidth: 0, fontFamily: fonts.display, fontSize: 25, lineHeight: 30, color: colors.ink }, close: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' }, modalContent: { padding: 18, gap: 16 }, modalActions: { flexDirection: 'row', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 8 },
  detailShift: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12 }, history: { gap: 10, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 16 }, historyRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: 10 }, historyDate: { color: colors.ink, fontWeight: '600', fontSize: 14 }, historyRange: { color: colors.muted, fontSize: 13, lineHeight: 20 }, historyDuration: { color: colors.primary, fontWeight: '700', fontVariant: ['tabular-nums'] }, timerDialog: { alignItems: 'center', gap: 8, paddingVertical: 8 }, dialogTime: { fontFamily: fonts.display, color: colors.ink, fontSize: 45, lineHeight: 52, fontVariant: ['tabular-nums'] },
});
