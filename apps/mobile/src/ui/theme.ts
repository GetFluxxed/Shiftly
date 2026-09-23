// Cocoa and rose sampled from baciodilatte.us; supporting tones tuned for app readability.
export const colors = {
  paper: '#FBF6EE', card: '#FFFCF7', white: '#FFFFFF',
  ink: '#4B2E20', muted: '#796252', primary: '#6B4124',
  soft: '#F2E7D8', line: '#E6D8C8', controlLine: '#A58B78',
  accent: '#F08183', accentStrong: '#995055', blush: '#F8DFDC',
  onPrimary: '#FFF9F0', onPrimaryMuted: '#F0DDCB',
  success: '#46583E', successPaper: '#EDF1E8',
  danger: '#963D43', dangerPaper: '#FCEBED',
};

export const fonts = {
  body: 'WorkSans_400Regular', strong: 'WorkSans_600SemiBold', display: 'Newsreader_500Medium',
};

export const permissionLabels: Record<string, string> = {
  'reports.submit': 'Send shift reports', 'reports.view': 'Read shift reports',
  'reports.manage': 'Update store notices', 'memberships.manage': 'Manage team access',
  'inventory.view': 'View inventory', 'stock.adjust': 'Adjust stock',
  'counts.submit': 'Submit stock counts', 'counts.approve': 'Approve stock counts',
  'receipts.draft': 'Prepare deliveries', 'receipts.post': 'Post deliveries',
  'configuration.manage': 'Manage store setup', 'catalog.propose': 'Suggest product changes',
  'catalog.manage': 'Manage shared products',
};

export const roleLabels: Record<string, string> = {
  owner: 'Business owner', admin: 'Administrator', manager: 'Store manager', crew: 'Crew member',
};

export function friendlyDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}
