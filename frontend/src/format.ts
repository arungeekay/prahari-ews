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

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Short month label from a YYYY-MM label like 2025-11 -> Nov '25. No Date parsing, so no timezone drift. */
export function ymLabel(ym: string | null | undefined): string {
  if (!ym) return '-'
  const m = /^(\d{4})-(\d{2})/.exec(ym)
  if (!m) return ym
  const name = MONTH_ABBR[parseInt(m[2], 10) - 1]
  return name ? `${name} '${m[1].slice(2)}` : ym
}

/** Shift a YYYY-MM label by a number of months (month-index arithmetic, e.g. to date a projected default month). */
export function shiftYm(ym: string, months: number): string {
  const m = /^(\d{4})-(\d{2})/.exec(ym)
  if (!m) return ym
  const total = parseInt(m[1], 10) * 12 + (parseInt(m[2], 10) - 1) + months
  const y = Math.floor(total / 12)
  const mo = total - y * 12 + 1
  return `${y}-${String(mo).padStart(2, '0')}`
}

/** Signed change in percentage points from a 0..1 delta, e.g. +2.3 pp. */
export function pp(delta: number | null | undefined, digits = 1): string {
  if (delta == null || Number.isNaN(delta)) return '-'
  const v = delta * 100
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)} pp`
}

/** Months with one decimal, or a dash when the backend returns null (e.g. no red accounts). */
export function months(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  return `${v.toFixed(1)} mo`
}

/** Audit timestamp (ISO, UTC) as a compact local date-time, e.g. 03 Sep 2026, 14:05. */
export function timestamp(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
