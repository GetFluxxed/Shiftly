/// <reference types="node" />
import assert from 'node:assert/strict';
import test from 'node:test';
import { WorkspaceController } from '../src/restoration/controller';
import { savedRoute } from '../src/restoration/policy';
import type { CheckpointStorage } from '../src/restoration/storage';
import type { Snapshot } from '../src/session/controller';
import {
  MAX_MEMBERS, MAX_SHIFTS, PRESETS, activeShift, addMember, clockIn, clockOut, elapsedMs,
  emptyState, formatDuration, isTrackingState, remainingMs, removeMember, renameMember,
  resetTimer, startTimer, workedTodayMs, type CrewMember, type TrackingState,
} from '../src/timeTracking/model';

const HOUR = 60 * 60 * 1_000;
const NOW = 2_000_000_000_000;

class MemoryStorage implements CheckpointStorage {
  value: string | null = null;
  async read() { return this.value; }
  async write(value: string) { this.value = value; }
  async remove() { this.value = null; }
}

function session(userId = 1, storeId = 10): Snapshot {
  const actor = { userId, username: `crew.${userId}`, displayName: `Crew ${userId}`, storeId, businessId: 5, role: 'crew' as const, capabilities: ['inventory.view'], provenance: 'named' as const };
  return { status: 'ready', actor, stores: [{ ...actor, storeName: `Store ${storeId}` }], message: null, busy: false, revision: 1 };
}

async function open(controller: WorkspaceController, snapshot = session()) {
  controller.accept(snapshot);
  await new Promise<void>(resolve => setImmediate(resolve));
  assert.equal(controller.getSnapshot().ready, true);
}

function memberState(name = 'Avery') {
  return addMember(emptyState(), name, 'member-1');
}

test('independent presets use wall-clock timestamps and resume after background time', () => {
  let state = clockIn(memberState(), 'member-1', 'shift-1', 1_000);
  state = startTimer(state, 'member-1', 'short', 2_000);
  state = startTimer(state, 'member-1', 'long', 3_000);
  const shift = activeShift(state.members[0]!)!;
  assert.deepEqual(PRESETS.map(preset => [preset.label, preset.durationMs]), [['3:30', 3.5 * HOUR], ['5:30', 5.5 * HOUR]]);
  assert.equal(remainingMs(shift, 'short', 7_000), 3.5 * HOUR - 5_000);
  assert.equal(remainingMs(shift, 'long', 7_000), 5.5 * HOUR - 4_000);
  assert.equal(elapsedMs(shift, 7_000), 6_000);
  assert.strictEqual(startTimer(state, 'member-1', 'short', 8_000), state);
  state = resetTimer(state, 'member-1', 'short');
  assert.equal(remainingMs(activeShift(state.members[0]!)!, 'short', 99_000), 3.5 * HOUR);
});

test('clock-out freezes elapsed time and both timer countdowns', () => {
  let state = clockIn(memberState(), 'member-1', 'shift-1', 10_000);
  state = startTimer(state, 'member-1', 'short', 11_000);
  state = startTimer(state, 'member-1', 'long', 12_000);
  state = clockOut(state, 'member-1', 20_000);
  const shift = state.members[0]!.shifts[0]!;
  assert.equal(elapsedMs(shift, 200_000), 10_000);
  assert.equal(remainingMs(shift, 'short', 200_000), 3.5 * HOUR - 9_000);
  assert.equal(remainingMs(shift, 'long', 200_000), 5.5 * HOUR - 8_000);
  assert.throws(() => startTimer(state, 'member-1', 'short', 21_000), /clocked in/);
  assert.throws(() => resetTimer(state, 'member-1', 'short'), /clocked in/);
});

test('repeated shift actions and stale mutations fail clearly', () => {
  const state = clockIn(memberState(), 'member-1', 'shift-1', 1_000);
  assert.throws(() => clockIn(state, 'member-1', 'shift-2', 2_000), /already clocked in/);
  assert.throws(() => clockOut(memberState(), 'member-1', 2_000), /not clocked in/);
  assert.throws(() => clockOut(state, 'member-1', 999), /before clock-in/);
  assert.throws(() => clockOut(state, 'missing', 2_000), /no longer exists/);
  assert.throws(() => renameMember(state, 'missing', 'Name'), /no longer exists/);
  assert.throws(() => removeMember(state, 'missing'), /no longer exists/);

  const closed = clockOut(state, 'member-1', 3_000);
  assert.throws(() => clockIn(closed, 'member-1', 'shift-2', 2_999), /previous clock-out/);
  assert.equal(activeShift(clockIn(closed, 'member-1', 'shift-2', 3_000).members[0]!)?.id, 'shift-2');
});

test('newest-first history retains the latest nine closed shifts plus the active shift', () => {
  let state = memberState();
  for (let index = 0; index < MAX_SHIFTS + 2; index += 1) {
    state = clockIn(state, 'member-1', `shift-${index}`, index * 10 + 1);
    state = clockOut(state, 'member-1', index * 10 + 2);
  }
  state = clockIn(state, 'member-1', 'current', 1_000);
  assert.equal(state.members[0]!.shifts.length, MAX_SHIFTS);
  assert.deepEqual(state.members[0]!.shifts.map(shift => shift.id), ['current', 'shift-11', 'shift-10', 'shift-9', 'shift-8', 'shift-7', 'shift-6', 'shift-5', 'shift-4', 'shift-3']);
});

test('worked today sums multiple shifts and clips an overnight shift to the local day', () => {
  const now = new Date(2026, 9, 29, 12).getTime();
  const today = new Date(2026, 9, 29, 0).getTime();
  const member: CrewMember = {
    id: 'member-1', name: 'Avery', shifts: [
      { id: 'open', clockIn: today + 10 * HOUR, clockOut: null, timers: { short: { startedAt: null }, long: { startedAt: null } } },
      { id: 'morning', clockIn: today + 5 * HOUR, clockOut: today + 7 * HOUR, timers: { short: { startedAt: null }, long: { startedAt: null } } },
      { id: 'overnight', clockIn: today - 2 * HOUR, clockOut: today + HOUR, timers: { short: { startedAt: null }, long: { startedAt: null } } },
    ],
  };
  assert.equal(workedTodayMs(member, now), 5 * HOUR);
});

test('names are normalized, duplicates rejected, and removal preserves other members', () => {
  let state = addMember(emptyState(), '  Avery   Stone ', 'one');
  state = addMember(state, 'Jordan', 'two');
  assert.equal(state.members[0]!.name, 'Avery Stone');
  assert.throws(() => renameMember(state, 'two', ' aVeRy stone '), /already exists/);
  assert.throws(() => addMember(state, 'AVERY STONE', 'three'), /already exists/);
  state = renameMember(state, 'two', ' Jordan Lee ');
  assert.deepEqual(removeMember(state, 'one').members.map(member => member.name), ['Jordan Lee']);
});

test('restore validation accepts exact bounded data and rejects corrupt or unsafe shapes', () => {
  const valid = clockOut(clockIn(memberState(), 'member-1', 'shift-1', 1_000), 'member-1', 2_000);
  assert.equal(isTrackingState(JSON.parse(JSON.stringify(valid))), true);
  const invalid: unknown[] = [
    { ...valid, version: 2 },
    { ...valid, surprise: true },
    { version: 1, members: [{ ...valid.members[0], name: ' Avery' }] },
    { version: 1, members: [valid.members[0], { ...valid.members[0] }] },
    { version: 1, members: [{ ...valid.members[0], shifts: [{ ...valid.members[0]!.shifts[0], clockOut: 0 }] }] },
    { version: 1, members: [{ ...valid.members[0], shifts: [{ ...valid.members[0]!.shifts[0], timers: { short: { startedAt: Number.NaN }, long: { startedAt: null } } }] }] },
    { version: 1, members: [{ ...valid.members[0], shifts: [
      { ...valid.members[0]!.shifts[0], id: 'newer', clockIn: 1_500, clockOut: 2_500 },
      { ...valid.members[0]!.shifts[0], id: 'older', clockIn: 1_000, clockOut: 2_000 },
    ] }] },
    { version: 1, members: [{ ...valid.members[0], shifts: [
      valid.members[0]!.shifts[0],
      { ...valid.members[0]!.shifts[0], id: 'old-active', clockIn: 0, clockOut: null },
    ] }] },
    { version: 1, members: Array.from({ length: MAX_MEMBERS + 1 }, (_, index) => ({ id: `m${index}`, name: `M ${index}`, shifts: [] })) },
    { version: 1, members: [{ id: 'one', name: 'Huge', shifts: [], padding: 'x'.repeat(12_000) }] },
  ];
  for (const value of invalid) assert.equal(isTrackingState(value), false);
  const cyclic: Record<string, unknown> = {}; cyclic.self = cyclic;
  assert.equal(isTrackingState(cyclic), false);
});

test('IDs, capacity, formatting, and timestamps are bounded', () => {
  let state: TrackingState = emptyState();
  for (let index = 0; index < MAX_MEMBERS; index += 1) state = addMember(state, `Member ${index}`, `member-${index}`);
  assert.throws(() => addMember(state, 'Overflow', 'overflow'), /limited to 20/);
  assert.throws(() => addMember(emptyState(), 'Name', ' '), /ID is invalid/);
  assert.throws(() => clockIn(memberState(), 'member-1', 'shift', -1), /nonnegative finite/);
  assert.throws(() => clockIn(memberState(), 'member-1', 'shift', 8.64e15 + 1), /nonnegative finite/);
  assert.equal(formatDuration(3_661_999), '1:01:01');
  assert.equal(formatDuration(-1), '0:00:00');
});

test('time-tracking route restoration is owner-only', () => {
  const crew = session().actor!;
  assert.equal(savedRoute('/time-tracking', {}, crew), null);
  assert.deepEqual(savedRoute('/time-tracking', {}, { ...crew, role: 'owner' }), { pathname: '/time-tracking' });
});

test('workspace checkpoint writes, flushes, and cold-restores the validated model', async () => {
  const storage = new MemoryStorage();
  const first = new WorkspaceController(storage, () => NOW);
  await open(first);
  const tracked = startTimer(clockIn(memberState(), 'member-1', 'shift-1', NOW - HOUR), 'member-1', 'short', NOW - 30 * 60_000);
  first.write('timeTracking.demo', tracked, 'v1', first.getSnapshot().scope);
  assert.equal(await first.flush(), true);
  assert.match(storage.value ?? '', /timeTracking\.demo/);

  const cold = new WorkspaceController(storage, () => NOW);
  await open(cold);
  assert.deepEqual(cold.read('timeTracking.demo', emptyState(), 'v1', isTrackingState), tracked);
});

test('workspace scope isolation never restores another account or store tracking state', async () => {
  const storage = new MemoryStorage();
  const first = new WorkspaceController(storage, () => NOW);
  await open(first, session(1, 10));
  first.write('timeTracking.demo', memberState('Private Crew'), 'v1', first.getSnapshot().scope);
  await first.flush();

  const otherUser = new WorkspaceController(storage, () => NOW);
  await open(otherUser, session(2, 10));
  assert.deepEqual(otherUser.read('timeTracking.demo', emptyState(), 'v1', isTrackingState), emptyState());

  const otherStore = new WorkspaceController(storage, () => NOW);
  await open(otherStore, session(1, 11));
  assert.deepEqual(otherStore.read('timeTracking.demo', emptyState(), 'v1', isTrackingState), emptyState());
});
