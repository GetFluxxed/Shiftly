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

export function canonicalMassPreview(amount: string, source: string, base: string): { value: string; rounded: boolean } | null {
  const precision = source === 'lb' ? 6 : 9;
  if (!['g', 'kg', 'lb'].includes(source) || !['g', 'kg'].includes(base) || !new RegExp(`^\\d{1,9}(?:\\.\\d{1,${precision}})?$`).test(amount)) return null;
  const [whole, fraction = ''] = amount.split('.'); const input = BigInt(whole!) * 1_000_000_000n + BigInt(fraction.padEnd(9, '0'));
  if (input <= 0n) return null;
  let numerator: bigint, divisor: bigint;
  if (source === 'lb') { numerator = input * 45_359_237n; divisor = base === 'kg' ? 100_000_000n : 100_000n; }
  else if (source === base) { numerator = input; divisor = 1n; }
  else if (source === 'kg') { numerator = input * 1_000n; divisor = 1n; }
  else { numerator = input; divisor = 1_000n; }
  const quotient = numerator / divisor, remainder = numerator % divisor;
  const canonical = quotient + (remainder * 2n >= divisor ? 1n : 0n);
  const tail = (canonical % 1_000_000_000n).toString().padStart(9, '0').replace(/0+$/, '');
  return { value: `${canonical / 1_000_000_000n}${tail ? `.${tail}` : ''}`, rounded: remainder !== 0n };
}
