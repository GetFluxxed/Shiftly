export type TimerId = 'short' | 'long';

export type TimerState = { startedAt: number | null };
export type Shift = {
  id: string;
  clockIn: number;
  clockOut: number | null;
  timers: Record<TimerId, TimerState>;
};
export type CrewMember = { id: string; name: string; shifts: Shift[] };
export type TrackingState = { version: 1; members: CrewMember[] };

export const MAX_MEMBERS = 20;
export const MAX_SHIFTS = 10;
const MAX_NAME_LENGTH = 60;
const MAX_ID_LENGTH = 120;
const MAX_STORED_JSON_LENGTH = 40_000;

export const PRESETS: ReadonlyArray<{ id: TimerId; label: string; durationMs: number }> = [
  { id: 'short', label: '3:30', durationMs: 3.5 * 60 * 60 * 1_000 },
  { id: 'long', label: '5:30', durationMs: 5.5 * 60 * 60 * 1_000 },
];

export function emptyState(): TrackingState {
  return { version: 1, members: [] };
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: string[]) {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
}

function validId(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= MAX_ID_LENGTH && value.trim() === value;
}

function validTimestamp(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && Number.isSafeInteger(value) && value >= 0 && value <= 8.64e15;
}

function validTimer(value: unknown): value is TimerState {
  return isObject(value) && hasExactKeys(value, ['startedAt']) && (value.startedAt === null || validTimestamp(value.startedAt));
}

function validShift(value: unknown): value is Shift {
  if (!isObject(value) || !hasExactKeys(value, ['id', 'clockIn', 'clockOut', 'timers'])) return false;
  if (!validId(value.id) || !validTimestamp(value.clockIn)) return false;
  if (value.clockOut !== null && (!validTimestamp(value.clockOut) || value.clockOut < value.clockIn)) return false;
  if (!isObject(value.timers) || !hasExactKeys(value.timers, ['short', 'long'])) return false;
  if (!validTimer(value.timers.short) || !validTimer(value.timers.long)) return false;
  for (const timer of [value.timers.short, value.timers.long]) {
    if (timer.startedAt !== null && timer.startedAt < value.clockIn) return false;
    if (timer.startedAt !== null && value.clockOut !== null && timer.startedAt > value.clockOut) return false;
  }
  return true;
}

function normalizedName(name: string) {
  return name.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

function cleanName(name: string) {
  const cleaned = name.trim().replace(/\s+/g, ' ');
  if (!cleaned) throw new Error('Crew member name is required.');
  if (cleaned.length > MAX_NAME_LENGTH) throw new Error(`Crew member name must be ${MAX_NAME_LENGTH} characters or fewer.`);
  return cleaned;
}

export function isTrackingState(value: unknown): value is TrackingState {
  let serialized: string | undefined;
  try { serialized = JSON.stringify(value); } catch { return false; }
  if (serialized === undefined || serialized.length > MAX_STORED_JSON_LENGTH) return false;
  if (!isObject(value) || !hasExactKeys(value, ['version', 'members']) || value.version !== 1 || !Array.isArray(value.members) || value.members.length > MAX_MEMBERS) return false;
  const memberIds = new Set<string>();
  const names = new Set<string>();
  const shiftIds = new Set<string>();
  for (const member of value.members) {
    if (!isObject(member) || !hasExactKeys(member, ['id', 'name', 'shifts']) || !validId(member.id)) return false;
    if (typeof member.name !== 'string' || member.name !== member.name.trim().replace(/\s+/g, ' ') || !member.name || member.name.length > MAX_NAME_LENGTH) return false;
    if (!Array.isArray(member.shifts) || member.shifts.length > MAX_SHIFTS) return false;
    const nameKey = normalizedName(member.name);
    if (memberIds.has(member.id) || names.has(nameKey)) return false;
    memberIds.add(member.id); names.add(nameKey);
    for (let index = 0; index < member.shifts.length; index += 1) {
      const shift = member.shifts[index]!;
      if (!validShift(shift) || shiftIds.has(shift.id)) return false;
      shiftIds.add(shift.id);
      if (shift.clockOut === null && index !== 0) return false;
      const newer = member.shifts[index - 1];
      if (newer && (shift.clockIn > newer.clockIn || shift.clockOut === null || shift.clockOut > newer.clockIn)) return false;
    }
  }
  return true;
}

function ensureStateFits(state: TrackingState) {
  if (!isTrackingState(state)) throw new Error('Time tracking data exceeds the device storage capacity. Remove old crew history and try again.');
  return state;
}

function findMember(state: TrackingState, id: string) {
  const member = state.members.find(candidate => candidate.id === id);
  if (!member) throw new Error('Crew member no longer exists.');
  return member;
}

function assertTimestamp(now: number) {
  if (!validTimestamp(now)) throw new Error('Time must be a nonnegative finite millisecond timestamp.');
}

export function activeShift(member: CrewMember): Shift | undefined {
  return member.shifts.find(shift => shift.clockOut === null);
}

export function addMember(state: TrackingState, name: string, id: string): TrackingState {
  const cleaned = cleanName(name);
  if (!validId(id)) throw new Error('Crew member ID is invalid.');
  if (state.members.length >= MAX_MEMBERS) throw new Error(`Time tracking is limited to ${MAX_MEMBERS} crew members.`);
  if (state.members.some(member => member.id === id)) throw new Error('Crew member ID is already in use.');
  if (state.members.some(member => normalizedName(member.name) === normalizedName(cleaned))) throw new Error(`A crew member named “${cleaned}” already exists.`);
  return ensureStateFits({ ...state, members: [...state.members, { id, name: cleaned, shifts: [] }] });
}

export function renameMember(state: TrackingState, id: string, name: string): TrackingState {
  const member = findMember(state, id);
  const cleaned = cleanName(name);
  if (state.members.some(candidate => candidate.id !== id && normalizedName(candidate.name) === normalizedName(cleaned))) throw new Error(`A crew member named “${cleaned}” already exists.`);
  if (member.name === cleaned) return state;
  return ensureStateFits({ ...state, members: state.members.map(candidate => candidate.id === id ? { ...candidate, name: cleaned } : candidate) });
}

export function removeMember(state: TrackingState, id: string): TrackingState {
  findMember(state, id);
  return { ...state, members: state.members.filter(member => member.id !== id) };
}

export function clockIn(state: TrackingState, memberId: string, shiftId: string, now: number): TrackingState {
  assertTimestamp(now);
  if (!validId(shiftId)) throw new Error('Shift ID is invalid.');
  const member = findMember(state, memberId);
  if (activeShift(member)) throw new Error(`${member.name} is already clocked in.`);
  const latestClockOut = member.shifts.reduce((latest, shift) => Math.max(latest, shift.clockOut ?? 0), 0);
  if (now < latestClockOut) throw new Error('Clock-in time cannot be before the previous clock-out time.');
  if (state.members.some(candidate => candidate.shifts.some(shift => shift.id === shiftId))) throw new Error('Shift ID is already in use.');
  const shift: Shift = { id: shiftId, clockIn: now, clockOut: null, timers: { short: { startedAt: null }, long: { startedAt: null } } };
  // Shifts are newest-first for direct history rendering. Keep nine closed shifts plus the new active shift.
  const shifts = [shift, ...member.shifts.filter(candidate => candidate.clockOut !== null).slice(0, MAX_SHIFTS - 1)];
  return ensureStateFits({ ...state, members: state.members.map(candidate => candidate.id === memberId ? { ...candidate, shifts } : candidate) });
}

export function clockOut(state: TrackingState, memberId: string, now: number): TrackingState {
  assertTimestamp(now);
  const member = findMember(state, memberId);
  const shift = activeShift(member);
  if (!shift) throw new Error(`${member.name} is not clocked in.`);
  if (now < shift.clockIn) throw new Error('Clock-out time cannot be before clock-in time.');
  return ensureStateFits({ ...state, members: state.members.map(candidate => candidate.id === memberId ? { ...candidate, shifts: candidate.shifts.map(item => item.id === shift.id ? { ...item, clockOut: now } : item) } : candidate) });
}

export function startTimer(state: TrackingState, memberId: string, timerId: TimerId, now: number): TrackingState {
  assertTimestamp(now);
  const member = findMember(state, memberId);
  const shift = activeShift(member);
  if (!shift) throw new Error(`${member.name} must be clocked in to start a timer.`);
  if (now < shift.clockIn) throw new Error('Timer start cannot be before clock-in time.');
  if (shift.timers[timerId].startedAt !== null) return state;
  return ensureStateFits({ ...state, members: state.members.map(candidate => candidate.id === memberId ? { ...candidate, shifts: candidate.shifts.map(item => item.id === shift.id ? { ...item, timers: { ...item.timers, [timerId]: { startedAt: now } } } : item) } : candidate) });
}

export function resetTimer(state: TrackingState, memberId: string, timerId: TimerId): TrackingState {
  const member = findMember(state, memberId);
  const shift = activeShift(member);
  if (!shift) throw new Error(`${member.name} must be clocked in to reset a timer.`);
  if (shift.timers[timerId].startedAt === null) return state;
  return ensureStateFits({ ...state, members: state.members.map(candidate => candidate.id === memberId ? { ...candidate, shifts: candidate.shifts.map(item => item.id === shift.id ? { ...item, timers: { ...item.timers, [timerId]: { startedAt: null } } } : item) } : candidate) });
}

export function remainingMs(shift: Shift, timerId: TimerId, now: number): number {
  const startedAt = shift.timers[timerId].startedAt;
  const duration = PRESETS.find(preset => preset.id === timerId)!.durationMs;
  if (startedAt === null) return duration;
  const end = shift.clockOut === null ? now : shift.clockOut;
  return Math.max(0, duration - Math.max(0, end - startedAt));
}

export function elapsedMs(shift: Shift, now: number): number {
  return Math.max(0, (shift.clockOut === null ? now : shift.clockOut) - shift.clockIn);
}

export function workedTodayMs(member: CrewMember, now: number): number {
  const dayStart = new Date(now); dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart); dayEnd.setDate(dayEnd.getDate() + 1);
  return member.shifts.reduce((total, shift) => {
    const end = shift.clockOut === null ? now : shift.clockOut;
    return total + Math.max(0, Math.min(end, dayEnd.getTime()) - Math.max(shift.clockIn, dayStart.getTime()));
  }, 0);
}

export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(Number.isFinite(ms) ? ms / 1_000 : 0));
  const hours = Math.floor(seconds / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
