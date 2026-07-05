import type { ReactNode } from 'react'
import type { Bucket } from '../types'
import { useTween } from './anim'
import { inr, toCr } from '../format'

export const RAG: Record<Bucket, string> = {
  red: '#E5484D',
  amber: '#E8A317',
  green: '#2E9E5B',
}

export const RAG_TINT: Record<Bucket, string> = {
  red: 'rgba(229,72,77,0.12)',
  amber: 'rgba(232,163,23,0.14)',
  green: 'rgba(46,158,91,0.12)',
}

/** Color a runway (months) on the RAG scale for the dial. */
export function runwayColor(months: number): string {
  if (months >= 18) return RAG.green
  if (months >= 9) return RAG.amber
  return RAG.red
}

/** Color a PD (0..1). */
export function pdColor(pd: number): string {
  if (pd >= 0.5) return RAG.red
  if (pd >= 0.15) return RAG.amber
  return RAG.green
}

/** Color a stress score (0..1) for the contagion graph. */
export function stressColor(s: number): string {
  if (s >= 0.66) return RAG.red
  if (s >= 0.33) return RAG.amber
  return RAG.green
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-card border border-line rounded-2xl shadow-soft ${className}`}>{children}</div>
  )
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-ink font-semibold text-[15px] tracking-tight">{children}</h3>
      {sub && <p className="text-muted text-xs mt-0.5">{sub}</p>}
    </div>
  )
}

export function RagChip({ bucket, children }: { bucket: Bucket; children?: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold capitalize"
      style={{ background: RAG_TINT[bucket], color: RAG[bucket] }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: RAG[bucket] }} />
      {children ?? bucket}
    </span>
  )
}

export function Kpi({
  label, value, hint, accent,
}: { label: string; value: ReactNode; hint?: string; accent?: string }) {
  return (
    <div className="px-4 py-2.5 rounded-xl bg-white/70 border border-line min-w-[128px]">
      <div className="text-[11px] uppercase tracking-wide text-muted font-medium">{label}</div>
      <div className="text-lg font-bold" style={{ color: accent ?? '#0A1F44' }}>{value}</div>
      {hint && <div className="text-[11px] text-muted mt-0.5">{hint}</div>}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-muted text-sm py-10 justify-center">
      <span className="w-4 h-4 rounded-full border-2 border-line border-t-brand animate-spin" />
      {label ?? 'Loading…'}
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="m-6 p-4 rounded-xl border border-rag-red/30 bg-rag-red/5 text-rag-red text-sm">
      {message}
    </div>
  )
}

/** Animated rupee counter (crore). */
export function CountUpCr({ value, className }: { value: number; className?: string }) {
  const v = useTween(toCr(value), 1100)
  return <span className={className}>₹{v.toFixed(2)} Cr</span>
}

/** Animated rupee counter that picks lakh/crore automatically. */
export function CountUpInr({ value, className }: { value: number; className?: string }) {
  const v = useTween(value, 900)
  return <span className={className}>{inr(v)}</span>
}
