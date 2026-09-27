/** Store navigation is separate from the server's action permissions. */
export function canViewStore(role: string | undefined): boolean {
  return role === 'manager' || role === 'owner';
}
