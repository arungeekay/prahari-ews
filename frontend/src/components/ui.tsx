import type { ReactNode } from 'react'
import type { Bucket } from '../types'
import { useTween } from './anim'
import { inr, toCr, pp } from '../format'

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

/**
 * Thresholds that drive PD and runway colours. They are served by /api/framework
 * (rag.amber_pd, rag.red_pd, runway_colours.green_min_months, runway_colours.amber_min_months)
 * and reach components through src/framework.tsx. FALLBACK_THRESHOLDS mirrors the shipped
 * data/interpretation_framework.json and is used only until the framework has loaded.
 */
export interface Thresholds {
  amber_pd: number
  red_pd: number
  green_min_months: number
  amber_min_months: number
}

export const FALLBACK_THRESHOLDS: Thresholds = {
  amber_pd: 0.05,
  red_pd: 0.2,
  green_min_months: 18,
  amber_min_months: 9,
}

/** RAG bucket for a runway (months). */
export function runwayBucket(months: number, t: Thresholds = FALLBACK_THRESHOLDS): Bucket {
  if (months >= t.green_min_months) return 'green'
  if (months >= t.amber_min_months) return 'amber'
  return 'red'
}

/** Color a runway (months) on the RAG scale for the dial. */
export function runwayColor(months: number, t: Thresholds = FALLBACK_THRESHOLDS): string {
  return RAG[runwayBucket(months, t)]
}

/** RAG bucket for a calibrated PD (0..1), same bands as the backend. */
export function pdBucket(pd: number, t: Thresholds = FALLBACK_THRESHOLDS): Bucket {
  if (pd >= t.red_pd) return 'red'
  if (pd >= t.amber_pd) return 'amber'
  return 'green'
}

/** Color a PD (0..1). */
export function pdColor(pd: number, t: Thresholds = FALLBACK_THRESHOLDS): string {
  return RAG[pdBucket(pd, t)]
}

/** Color a stress score (0..1) for the contagion graph. */
export function stressColor(s: number): string {
  if (s >= 0.66) return RAG.red
  if (s >= 0.33) return RAG.amber
  return RAG.green
}

/** Unified risk grade colours, PR1 (best) to PR7 (worst). */
export const GRADE_COLOR: Record<string, string> = {
  PR1: '#1F8A4C',
  PR2: '#2E9E5B',
  PR3: '#7FB241',
  PR4: '#E8A317',
  PR5: '#E07B24',
  PR6: '#E5484D',
  PR7: '#A8262B',
}

export const gradeColor = (grade: string): string => GRADE_COLOR[grade] ?? '#5B6B85'

/** Statutory SMA (days past due) colours. */
export function smaColor(label: string): string {
  if (label === 'Standard') return RAG.green
  if (label === 'SMA-0') return RAG.amber
  if (label === 'NPA') return '#A8262B'
  return RAG.red
}

/** Officer-note sentiment in [-1, 1]: adverse below -0.15 (the backend's own cut), favourable above 0.15. */
export function sentimentTone(s: number): 'negative' | 'positive' | 'neutral' {
  if (s < -0.15) return 'negative'
  if (s > 0.15) return 'positive'
  return 'neutral'
}

export function sentimentColor(s: number): string {
  const tone = sentimentTone(s)
  return tone === 'negative' ? RAG.red : tone === 'positive' ? RAG.green : '#5B6B85'
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

/** Neutral pill. Pass a colour to tint it (dot + text), e.g. for statutory SMA or feed status. */
export function Chip({
  children, color = '#5B6B85', bg, dot = true, title, className = '',
}: { children: ReactNode; color?: string; bg?: string; dot?: boolean; title?: string; className?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line ${className}`}
      style={{ background: bg ?? `${color}14`, color }}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />}
      {children}
    </span>
  )
}

/** Thin-file marker: fewer than 12 months of conduct on file, so the score rests on a short window. */
export function ThinFileChip({ months, className = '' }: { months?: number; className?: string }) {
  const hint = `Thin file${months != null ? `: ${months} months of conduct on file` : ''}. ` +
    "The score rests on a short window and should be read with the officer's own knowledge of the account."
  return (
    <Chip color={RAG.amber} dot={false} className={className} title={hint}>
      thin file{months != null ? ` · ${months} mo` : ''}
    </Chip>
  )
}

/** Unified risk grade badge: PR1..PR7 with label and 0-1000 score. */
export function GradeBadge({
  grade, label, score, compact = false,
}: { grade: string; label?: string; score?: number; compact?: boolean }) {
  const c = gradeColor(grade)
  if (compact) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold"
        style={{ color: c, background: `${c}1F` }} title={label ? `${grade} · ${label}` : grade}>
        {grade}
      </span>
    )
  }
  return (
    <div className="inline-flex items-center gap-3 rounded-xl border px-3 py-2"
      style={{ borderColor: `${c}66`, background: `${c}14` }}>
      <span className="text-xl font-bold tracking-tight leading-none" style={{ color: c }}>{grade}</span>
      <div className="leading-tight">
        <div className="text-sm font-semibold text-ink">{label ?? 'Risk grade'}</div>
        {score != null && <div className="text-[11px] text-muted">Score {score.toLocaleString('en-IN')} / 1000</div>}
      </div>
    </div>
  )
}

/** Sentiment chip for officer notes: negative red, positive green, neutral grey. */
export function SentimentChip({ sentiment }: { sentiment: number }) {
  const tone = sentimentTone(sentiment)
  const c = sentimentColor(sentiment)
  return (
    <Chip color={c} title={`Sentiment ${sentiment.toFixed(2)} on a -1 to 1 scale`}>
      {tone} {sentiment >= 0 ? '+' : ''}{sentiment.toFixed(2)}
    </Chip>
  )
}

/** PD change in percentage points. Rising PD is red, falling is green, flat is grey. */
export function PdDelta({ delta, className = '' }: { delta: number; className?: string }) {
  const c = delta > 0.0005 ? RAG.red : delta < -0.0005 ? RAG.green : '#5B6B85'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-md text-[11px] font-semibold ${className}`}
      style={{ color: c, background: `${c}14` }}>
      {delta > 0.0005 ? '▲ ' : delta < -0.0005 ? '▼ ' : ''}{pp(delta)}
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

/** Small labelled figure on a paper background (model card, contagion panels). */
export function MiniStat({
  label, value, sub, accent, size = 'md',
}: { label: string; value: ReactNode; sub?: string; accent?: string; size?: 'sm' | 'md' }) {
  return (
    <div className="rounded-xl bg-paper border border-line p-3 text-center min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`${size === 'sm' ? 'text-sm' : 'text-lg'} font-bold mt-0.5 break-words`} style={{ color: accent ?? '#0A1F44' }}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
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
