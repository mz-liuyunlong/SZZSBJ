/** PR337 purchase approval: deterministic local demo only, never use for real API rows. */
export function buildDemoDailySales90(last30: number, seed: number): number[] {
  if (!Number.isFinite(last30) || last30 < 0) return [];
  const target = Math.max(0, Math.round(last30));
  const daily = Array.from({length: 90}, (_, i) => {
    const trend = i < 30 ? 0.76 : i < 60 ? 0.88 : 1;
    const base = target / 30 * trend;
    const oscillation = Math.sin((i + seed) * 0.49) * (base * .34)
      + Math.cos((i + seed * 3) * .83) * (base * .21);
    return Math.max(0, Math.round(base + oscillation));
  });
  // Keep the last 30 days consistent with the very same profile's sales30Qty.
  let delta = target - daily.slice(60).reduce((sum, value) => sum + value, 0);
  let pass = 0;
  while (delta !== 0 && pass < 6000) {
    const position = 60 + ((pass * 17 + seed * 7) % 30);
    if (delta > 0) { daily[position]++; delta--; }
    else if (daily[position] > 0) { daily[position]--; delta++; }
    pass++;
  }
  if (delta !== 0) throw new Error('Demo daily sales reconciliation failed');
  return daily;
}

export function finiteNumber(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined;
  return value;
}
