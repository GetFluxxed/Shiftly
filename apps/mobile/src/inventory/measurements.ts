/** Exact display conversion; quantities travel over the API as decimal text. */
export function equivalentMass(amount: string, unit: string): string | null {
  if (!['g', 'kg'].includes(unit) || !/^\d{1,9}(?:\.\d{1,6})?$/.test(amount)) return null;
  const [whole, fraction = ''] = amount.split('.');
  const scaled = BigInt(whole!) * 1_000_000n + BigInt(fraction.padEnd(6, '0'));
  if (scaled <= 0n) return null;
  const divisor = unit === 'kg' ? 1_000n : 1_000_000_000n;
  const digits = unit === 'kg' ? 3 : 9;
  const tail = (scaled % divisor).toString().padStart(digits, '0').replace(/0+$/, '');
  return `${scaled / divisor}${tail ? `.${tail}` : ''} ${unit === 'kg' ? 'g' : 'kg'}`;
}
