import { useEffect, useMemo, useState } from 'react'
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api'
import type { Account, Bucket, Confidence, Mover, Portfolio as PortfolioT } from '../types'
import { GRADES, SMA_ORDER } from '../types'
import { useNav } from '../nav'
import {
  Card, SectionTitle, Kpi, Spinner, RAG, CountUpCr, RagChip, GradeBadge, PdDelta, Chip, ThinFileChip, gradeColor, smaColor,
} from '../components/ui'
import { inr, inrCr, toCr, pct, months } from '../format'

type Filter = 'risk' | 'red' | 'amber' | 'green'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'risk', label: 'Red + Amber' },
  { key: 'red', label: 'Red' },
  { key: 'amber', label: 'Amber' },
  { key: 'green', label: 'Green' },
]

interface CellDatum {
  name: string
  size: number
  bucket: Bucket
  borrower_id: string
  exposure: number
  runway_label: string
  demo: string
  months_on_file: number
  confidence: Confidence
}

function TreemapCell(props: any) {
  const { x, y, width, height, depth, bucket, name, borrower_id, exposure, demo, onSelect } = props
  if (depth === 0 || width == null || width <= 0 || height <= 0) return null
  const color = RAG[bucket as Bucket] ?? '#94a3b8'
  const showText = width > 62 && height > 30
  const truncate = (s: string) => {
    const max = Math.floor(width / 6.4)
    return s.length > max ? s.slice(0, Math.max(3, max - 1)) + '…' : s
  }
  return (
    <g onClick={() => borrower_id && onSelect(borrower_id)} style={{ cursor: borrower_id ? 'pointer' : 'default' }}>
      <rect
        x={x} y={y} width={width} height={height} rx={3}
        fill={color} stroke="#fff" strokeWidth={1.25}
        style={{ transition: 'opacity .15s' }}
      />
      {demo === 'sharma' && (
        <rect x={x + 1.5} y={y + 1.5} width={width - 3} height={height - 3} rx={2}
          fill="none" stroke="#fff" strokeWidth={2} strokeDasharray="4 3" />
      )}
      {showText && (
        <>
          <text x={x + 7} y={y + 17} fontSize={11} fill="#fff" fontWeight={600}>{truncate(name)}</text>
          <text x={x + 7} y={y + 31} fontSize={10} fill="rgba(255,255,255,0.88)">{inr(exposure)}</text>
        </>
      )}
    </g>
  )
}

/** Hover card for a treemap tile; marks thin files (under 12 months of conduct) so a short-window score is read as such. */
function TreemapTip({ active, payload }: { active?: boolean; payload?: any[] }) {
  const p = active ? (payload?.[0]?.payload as Partial<CellDatum> | undefined) : undefined
  if (!p || !p.borrower_id) return null
  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-soft">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-ink">{p.name}</span>
        {p.bucket && <RagChip bucket={p.bucket} />}
        {p.confidence === 'low' && <ThinFileChip months={p.months_on_file} />}
      </div>
      <div className="text-muted mt-1">
        {p.borrower_id} · {inr(p.exposure ?? 0)} · runway {p.runway_label ?? '-'} mo
        {p.months_on_file != null ? ` · ${p.months_on_file} months on file` : ''}
      </div>
    </div>
  )
}

export function Portfolio({ portfolio }: { portfolio: PortfolioT | null }) {
  const { openAccount } = useNav()
  const [accounts, setAccounts] = useState<Account[] | null>(null)
  const [filter, setFilter] = useState<Filter>('risk')
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.accounts({ sort: 'exposure', limit: 3000 })
      .then((r) => setAccounts(r.accounts))
      .catch((e) => setErr(String(e)))
  }, [])

  const data = useMemo<CellDatum[]>(() => {
    if (!accounts) return []
    const pass = (a: Account) =>
      filter === 'risk' ? a.bucket !== 'green' : a.bucket === filter
    const rows = accounts.filter(pass).sort((a, b) => b.exposure - a.exposure)
    const capped = filter === 'green' ? rows.slice(0, 220) : rows.slice(0, 300)
    return capped.map((a) => ({
      name: a.name,
      size: a.exposure,
      bucket: a.bucket,
      borrower_id: a.borrower_id,
      exposure: a.exposure,
      runway_label: a.runway_label,
      demo: a.demo,
      months_on_file: a.months_on_file,
      confidence: a.confidence,
    }))
  }, [accounts, filter])

  /** Thin files (under 12 months of conduct) in the prediction book, by borrower id, for the movers chip. */
  const thinFiles = useMemo(() => {
    const m = new Map<string, number>()
    for (const a of accounts ?? []) if (a.confidence === 'low') m.set(a.borrower_id, a.months_on_file)
    return m
  }, [accounts])

  if (err) return <div className="text-rag-red text-sm">{err}</div>

  return (
    <div className="space-y-6">
      {/* KPI header */}
      {portfolio && (
        <div className="flex flex-wrap items-stretch gap-3">
          <Kpi label="As of" value={portfolio.as_of_label} hint={`framework ${portfolio.framework_version}`} />
          <Kpi label="MSME accounts" value={portfolio.n_accounts.toLocaleString('en-IN')}
            hint={`${inrCr(portfolio.total_exposure)} monitored in the prediction book`} />
          <Kpi label="Red-bucket exposure" value={inrCr(portfolio.red_exposure)} accent={RAG.red}
            hint={`${portfolio.buckets.red.count} red accounts`} />
          <Kpi label="Amber-bucket exposure" value={inrCr(portfolio.buckets.amber.exposure)} accent={RAG.amber}
            hint={`${portfolio.buckets.amber.count} amber accounts`} />
          <Kpi label="Avg runway (red)" value={months(portfolio.avg_runway_red)} accent={RAG.red}
            hint={`${months(portfolio.avg_runway_flagged)} flagged · ${months(portfolio.avg_runway)} whole book`} />
          <Kpi label="Movers up this month" value={portfolio.n_movers_up.toLocaleString('en-IN')} accent={RAG.amber}
            hint="PD rose by more than 2 pp since last month" />
          <Kpi label="Already NPA" value={portfolio.n_npa.toLocaleString('en-IN')} accent="#A8262B"
            hint={`${inrCr(portfolio.npa_exposure)} · 90+ DPD, outside the prediction book of ${portfolio.n_book.toLocaleString('en-IN')}`} />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Heat map */}
        <Card className="xl:col-span-2 p-5">
          <div className="flex items-center justify-between mb-3">
            <SectionTitle sub="Each tile is an account, sized by exposure and coloured by RAG bucket. Click to open.">
              Portfolio Heat Map
            </SectionTitle>
            <div className="flex gap-1 bg-paper rounded-xl p-1 border border-line">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    filter === f.key ? 'bg-white text-ink shadow-sm' : 'text-muted hover:text-ink'
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          {!accounts ? (
            <Spinner label="Loading portfolio…" />
          ) : data.length === 0 ? (
            <div className="text-muted text-sm py-20 text-center">No accounts in this bucket.</div>
          ) : (
            <div style={{ width: '100%', height: 460 }}>
              <ResponsiveContainer>
                <Treemap
                  data={data}
                  dataKey="size"
                  animationDuration={500}
                  content={<TreemapCell onSelect={openAccount} />}
                >
                  <Tooltip content={<TreemapTip />} />
                </Treemap>
              </ResponsiveContainer>
            </div>
          )}
          <div className="flex items-center gap-4 mt-3 text-xs text-muted">
            {(['red', 'amber', 'green'] as Bucket[]).map((b) => (
              <span key={b} className="inline-flex items-center gap-1.5 capitalize">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: RAG[b] }} />{b}
              </span>
            ))}
            <span className="inline-flex items-center gap-1.5 ml-2">
              <span className="w-3 h-2.5 rounded-sm border border-dashed border-ink" /> Demo character
            </span>
          </div>
        </Card>

        {/* Right column: provision impact + grade strip + statutory SMA mix */}
        <div className="space-y-6">
          {portfolio && <ProvisionImpact portfolio={portfolio} />}
          {portfolio && <GradeStrip portfolio={portfolio} />}
          {portfolio && <SmaMix portfolio={portfolio} />}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2">
          <MoversPanel nSuppressed={portfolio?.n_suppressed ?? 0} thinFiles={thinFiles} />
        </div>
        {portfolio && <SectorExposure portfolio={portfolio} />}
      </div>
    </div>
  )
}

function ProvisionImpact({ portfolio }: { portfolio: PortfolioT }) {
  const { provision_now, provision_at_npa, provision_saved_acting_now } = portfolio
  const maxV = Math.max(provision_now, provision_at_npa) || 1
  return (
    <Card className="p-5">
      <SectionTitle sub="Provisioning on the red bucket if we intervene now vs. let it slide to NPA.">
        Provision impact - act now vs. at NPA
      </SectionTitle>
      <div className="rounded-xl bg-rag-green/5 border border-rag-green/20 p-4 text-center mb-4">
        <div className="text-[11px] uppercase tracking-wide text-muted">Preserved by acting now</div>
        <div className="text-3xl font-bold text-rag-green mt-1">
          <CountUpCr value={provision_saved_acting_now} />
        </div>
      </div>
      <Bar label="Provision if we act now" value={provision_now} max={maxV} color={RAG.green} />
      <Bar label="Provision at NPA" value={provision_at_npa} max={maxV} color={RAG.red} />
    </Card>
  )
}

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-600">{label}</span>
        <span className="font-semibold text-ink">{inrCr(value)}</span>
      </div>
      <div className="h-2.5 rounded-full bg-paper overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.max(2, (value / max) * 100)}%`, background: color }} />
      </div>
    </div>
  )
}

/** Compact unified-grade distribution: PR1 (best) to PR7 (worst), count and exposure. */
function GradeStrip({ portfolio }: { portfolio: PortfolioT }) {
  const rows = GRADES.map((g) => ({
    grade: g,
    count: portfolio.grades[g]?.count ?? 0,
    exposure: portfolio.grades[g]?.exposure ?? 0,
  }))
  const total = rows.reduce((s, r) => s + r.count, 0) || 1
  return (
    <Card className="p-5">
      <SectionTitle sub={`One risk grade for every loan, whatever its type or sector · framework ${portfolio.framework_version}`}>
        Grade distribution
      </SectionTitle>
      <div className="flex h-3 rounded-full overflow-hidden bg-paper border border-line">
        {rows.map((r) => r.count > 0 && (
          <div key={r.grade} title={`${r.grade}: ${r.count.toLocaleString('en-IN')} accounts · ${inr(r.exposure)}`}
            style={{ width: `${(r.count / total) * 100}%`, background: gradeColor(r.grade) }} />
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1 mt-3">
        {rows.map((r) => (
          <div key={r.grade} className="rounded-lg border border-line bg-paper/60 px-1 py-2 text-center min-w-0">
            <div className="text-[11px] font-bold" style={{ color: gradeColor(r.grade) }}>{r.grade}</div>
            <div className="text-sm font-semibold text-ink">{r.count.toLocaleString('en-IN')}</div>
            <div className="text-[10px] text-muted truncate">{toCr(r.exposure).toFixed(0)} Cr</div>
          </div>
        ))}
      </div>
    </Card>
  )
}

/** Statutory SMA (actual days past due) and facility mix, as chips. */
function SmaMix({ portfolio }: { portfolio: PortfolioT }) {
  const mix = portfolio.statutory_sma_mix
  const known = SMA_ORDER as readonly string[]
  const keys = [
    ...known.filter((k) => k in mix),
    ...Object.keys(mix).filter((k) => !known.includes(k)),
  ]
  return (
    <Card className="p-5">
      <SectionTitle sub={`RBI statutory status from actual days past due across the full book of ${portfolio.n_book.toLocaleString('en-IN')} accounts, NPA included. The model flag never replaces it.`}>
        Statutory SMA mix
      </SectionTitle>
      <div className="flex flex-wrap gap-2">
        {keys.map((k) => (
          <span key={k} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border border-line bg-paper/60">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: smaColor(k) }} />
            <span className="text-ink">{k}</span>
            <span className="text-muted font-medium">{mix[k].toLocaleString('en-IN')}</span>
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 mt-3 text-[11px] text-muted">
        <span className="uppercase tracking-wide">Facility mix</span>
        {Object.entries(portfolio.loan_type_mix).map(([k, v]) => (
          <span key={k} className="px-2 py-0.5 rounded-md bg-paper border border-line text-slate-600">
            {k} · {v.toLocaleString('en-IN')}
          </span>
        ))}
      </div>
    </Card>
  )
}

/** Accounts whose calibrated PD rose most since last month, with what changed. */
function MoversPanel({ nSuppressed, thinFiles }: { nSuppressed: number; thinFiles: Map<string, number> }) {
  const { openAccount } = useNav()
  const [movers, setMovers] = useState<Mover[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.movers(8).then((r) => setMovers(r.movers)).catch((e) => setErr(String(e)))
  }, [])

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub="Top 8 accounts by rise in calibrated PD since last month, with the leading model driver. Click to open.">
          Movers this month
        </SectionTitle>
        {nSuppressed > 0 && (
          <Chip color="#0E7C7B" title="Cleared by an officer; suppressed from movers and the watch-list until the cooling period ends">
            {nSuppressed} cleared, in cooling period
          </Chip>
        )}
      </div>
      {err ? (
        <div className="text-rag-red text-sm">{err}</div>
      ) : !movers ? (
        <Spinner label="Ranking movers…" />
      ) : movers.length === 0 ? (
        <p className="text-sm text-muted">No account moved up this month.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                <th className="py-2 pr-3 font-medium">Account</th>
                <th className="py-2 px-3 font-medium">Facility</th>
                <th className="py-2 px-3 font-medium text-right whitespace-nowrap">PD last month → now</th>
                <th className="py-2 px-3 font-medium">Bucket</th>
                <th className="py-2 px-3 font-medium text-right">Exposure</th>
                <th className="py-2 pl-3 font-medium">What changed</th>
              </tr>
            </thead>
            <tbody>
              {movers.map((m) => (
                <tr key={m.borrower_id}
                  onClick={() => openAccount(m.borrower_id)}
                  className="border-b border-line last:border-0 hover:bg-paper cursor-pointer align-top">
                  <td className="py-2.5 pr-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-ink">{m.name}</span>
                      <GradeBadge grade={m.grade} compact />
                      {thinFiles.has(m.borrower_id) && <ThinFileChip months={thinFiles.get(m.borrower_id)} />}
                    </div>
                    <div className="text-[11px] text-muted capitalize">
                      {m.borrower_id} · {m.sector.replace('_', ' ')} · {m.statutory_sma}
                    </div>
                  </td>
                  <td className="py-2.5 px-3 text-slate-600">{m.loan_type}</td>
                  <td className="py-2.5 px-3 text-right whitespace-nowrap">
                    <span className="text-muted">{pct(m.pd_prev)}</span>
                    <span className="text-muted mx-1.5">→</span>
                    <span className="font-semibold text-ink">{pct(m.pd)}</span>
                    <PdDelta delta={m.pd_delta} className="ml-2" />
                  </td>
                  <td className="py-2.5 px-3"><RagChip bucket={m.bucket} /></td>
                  <td className="py-2.5 px-3 text-right font-semibold text-ink whitespace-nowrap">{inr(m.exposure)}</td>
                  <td className="py-2.5 pl-3 text-slate-600 text-[12px] max-w-[280px]">{m.top_reasons[0] ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

function SectorExposure({ portfolio }: { portfolio: PortfolioT }) {
  const entries = Object.entries(portfolio.sector_exposure)
  const max = Math.max(...entries.map(([, v]) => v)) || 1
  return (
    <Card className="p-5">
      <SectionTitle sub="Where the book's exposure concentrates.">Exposure by sector</SectionTitle>
      <div className="space-y-2.5">
        {entries.map(([sector, v]) => (
          <div key={sector}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-600 capitalize">{sector.replace('_', ' ')}</span>
              <span className="font-semibold text-ink">{toCr(v).toFixed(0)} Cr</span>
            </div>
            <div className="h-2 rounded-full bg-paper overflow-hidden">
              <div className="h-full rounded-full bg-brand transition-all duration-700"
                style={{ width: `${(v / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
