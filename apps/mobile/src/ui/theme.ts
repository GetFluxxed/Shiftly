export const colors = {
  paper: '#F5F4EE', card: '#FFFEF8', ink: '#23382E', muted: '#657267',
  forest: '#234F3C', sage: '#E3EADD', line: '#DCE1D5', coral: '#BC4A33',
  peach: '#F8E2D5', white: '#FFFFFF', danger: '#A73328', dangerPaper: '#FFF0E9',
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
