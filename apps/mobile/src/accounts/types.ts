export interface RoleChoice { role: string; included: string[]; optional: string[] }
export interface Person {
  userId: number; username: string; displayName: string; accountState: string;
  businessRole: string | null; businessState: string | null; businessCapabilities: string[];
}
export interface TeamMember extends Person {
  role: string; membershipState: string; capabilities: string[]; canEdit: boolean; canReissue: boolean;
}
export interface BusinessMember extends Person {
  canDelegate: boolean; canRevokeBusiness: boolean; canTransfer: boolean; canSuspend: boolean;
}
export interface Management {
  storeId: number; members: TeamMember[]; directory: BusinessMember[]; roles: RoleChoice[];
  isOwner: boolean; businessCapabilities: string[]; sharedCrewEnabled: boolean | null;
}
export interface Invitation { userId: number; token: string; expiresIn: number }
export function accountState(person: Person, membershipState?: string) {
  return person.accountState === 'pending' ? 'Awaiting activation' : person.accountState === 'suspended' ? 'Account suspended'
    : membershipState === 'revoked' ? 'Store access removed' : 'Active';
}
export function accountId(value: string): number | null {
  const id = Number(value);
  return /^[1-9]\d*$/.test(value) && Number.isSafeInteger(id) ? id : null;
}
/** Preserve stored grants that are already included by a role, including future capabilities. */
export function roleGrants(role: RoleChoice | undefined, current: string[]) {
  return role ? current.filter(value => role.included.includes(value) || role.optional.includes(value)) : [];
}
