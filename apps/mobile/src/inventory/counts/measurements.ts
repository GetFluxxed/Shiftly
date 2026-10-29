import type { Entry, SnapshotProduct } from './api';

function scaled(value: string): bigint | null {
  if (!/^\d{1,9}(?:\.\d{1,6})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole!) * 1_000_000_000n + BigInt(fraction.padEnd(9, '0'));
}
function scaledPackage(value: string): bigint | null {
  if (!/^\d{1,15}(?:\.\d{1,9})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.'); return BigInt(whole!) * 1_000_000_000n + BigInt(fraction.padEnd(9, '0'));
}
function convert(value: bigint, from: string, to: string): bigint | null {
  if (from === to) return to === 'each' && value % 1_000_000_000n ? null : value;
  if (from === 'g' && to === 'kg') return value % 1_000n === 0n ? value / 1_000n : null;
  if (from === 'kg' && to === 'g') return value * 1_000n;
  return null;
}
export function entryTotal(entry: Entry, product: SnapshotProduct): string | null {
  let total: bigint | null;
  if (entry.mode === 'total') {
    const amount = scaled(entry.amount); if (amount === null) return null;
    total = convert(amount, entry.unit, product.baseUnit);
  } else if (entry.mode === 'containers') {
    if (!Number.isInteger(entry.fullContainers) || entry.fullContainers < 0 || entry.fullContainers > 1_000_000 || product.containerAmount === null) return null;
    const container = scaledPackage(product.containerAmount), partial = scaled(entry.partialAmount);
    if (container === null || partial === null) return null;
    const converted = convert(partial, entry.partialUnit, product.baseUnit); if (converted === null) return null;
    total = container * BigInt(entry.fullContainers) + converted;
  } else {
    const known = new Map((product.packages || []).map(item => [item.id, item]));
    total = 0n;
    const seen = new Set<string>();
    for (const row of entry.packages) {
      const item = known.get(row.packageId);
      if (!item || !item.active || seen.has(row.packageId) || !Number.isInteger(row.count) || row.count < 0 || row.count > 1_000_000) return null;
      const amount = scaledPackage(item.amount); if (amount === null) return null;
      seen.add(row.packageId); total += amount * BigInt(row.count);
    }
    const partial = scaled(entry.partialAmount); if (partial === null) return null;
    const converted = convert(partial, entry.partialUnit, product.baseUnit); if (converted === null) return null;
    total += converted;
  }
  if (total === null || total > 999_999_999_999_999_999_999_999n) return null;
  const fraction = (total % 1_000_000_000n).toString().padStart(9, '0').replace(/0+$/, '');
  return `${total / 1_000_000_000n}${fraction ? '.' + fraction : ''}`;
}
export function quantityLabel(amount: string | null, unit: string) { return amount === null ? 'Not counted' : `${amount} ${unit === 'each' ? 'items' : unit}`; }
export function entryLabel(entry: Entry | null, product: SnapshotProduct) {
  if (!entry) return 'Not counted';
  if (entry.mode === 'total') return `Measured total: ${quantityLabel(entry.amount, entry.unit)}`;
  if (entry.mode === 'containers') return `${entry.fullContainers} full × ${quantityLabel(product.containerAmount, product.baseUnit)} + ${quantityLabel(entry.partialAmount, entry.partialUnit)} net partial`;
  const known = new Map((product.packages || []).map(item => [item.id, item]));
  const packages = entry.packages.filter(item => item.count > 0).map(item => { const saved = known.get(item.packageId); const source = saved?.labelAmount && saved.labelUnit ? `${saved.labelAmount} ${saved.labelUnit === 'lb' ? 'lbs' : saved.labelUnit}${saved.labelUnit === product.baseUnit ? '' : ` = ${quantityLabel(saved.amount, product.baseUnit)}`}` : saved ? quantityLabel(saved.amount, product.baseUnit) : ''; return `${item.count} × ${saved?.name || 'saved package'}${source ? ` [${source}]` : ''}`; }).join(' + ');
  const partial = `${quantityLabel(entry.partialAmount, entry.partialUnit)} loose`;
  return packages ? `${packages} + ${partial}` : partial;
}
