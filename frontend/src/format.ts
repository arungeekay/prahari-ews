// Rupee + number formatting. Everything on screen is money-first (brief §"Rupees, not scores").

/** Format rupees into lakh/crore, e.g. ₹4.12 Cr, ₹85.0 L. */
export function inr(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  const abs = Math.abs(v)
  if (abs >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`
  if (abs >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`
  if (abs >= 1000) return `₹${Math.round(v).toLocaleString('en-IN')}`
  return `₹${Math.round(v)}`
}

/** Rupees -> crore (numeric). */
export const toCr = (v: number): number => v / 1e7

/** Format a crore value already in ₹ Cr. */
export const inrCr = (v: number): string => `₹${toCr(v).toFixed(v >= 1e9 ? 0 : 2)} Cr`

/** Percentage from a 0..1 fraction. */
export function pct(x: number | null | undefined, digits = 1): string {
  if (x == null || Number.isNaN(x)) return '-'
  return `${(x * 100).toFixed(digits)}%`
}

/** Indian-grouped integer. */
export const num = (v: number): string => Math.round(v).toLocaleString('en-IN')

/** Short month label from an ISO date string like 2026-06-01 -> Jun '26. */
export function monthLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const m = d.toLocaleString('en-US', { month: 'short' })
  return `${m} '${String(d.getFullYear()).slice(2)}`
}
