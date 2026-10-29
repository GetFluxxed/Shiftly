/** The URL carries an opaque secret only. Store and role are server-side facts. */
export function invitationToken(fragment: unknown): string {
  if (typeof fragment !== 'string' || fragment.length > 600) return '';
  const fields = new URLSearchParams(fragment.replace(/^#/, ''));
  const tokens = fields.getAll('invitation');
  const token = tokens[0] || '';
  return tokens.length === 1 && /^[A-Za-z0-9_-]{32,512}$/.test(token) ? token : '';
}

export function invitationLink(activationUrl: string, token: string): string {
  if (!/^[A-Za-z0-9_-]{32,512}$/.test(token)) throw new Error('Invalid invitation.');
  return `${activationUrl.split('#')[0]}#invitation=${encodeURIComponent(token)}`;
}

export type InvitationDetails = { username: string; displayName: string; storeName: string; role: 'crew' };
