import { useEffect, useMemo, useState } from 'react'
import { Treemap, ResponsiveContainer } from 'recharts'
import { api } from '../api'
import type { Account, Bucket, Portfolio as PortfolioT } from '../types'
import { useNav } from '../nav'
import { Card, SectionTitle, Kpi, Spinner, RAG, CountUpCr } from '../components/ui'
import { inr, inrCr, toCr } from '../format'

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
    }))
  }, [accounts, filter])

  if (err) return <div className="text-rag-red text-sm">{err}</div>

  return (
    <div className="space-y-6">
      {/* KPI header */}
      {portfolio && (
        <div className="flex flex-wrap items-stretch gap-3">
          <Kpi label="MSME accounts" value={portfolio.n_accounts.toLocaleString('en-IN')}
            hint={`${inrCr(portfolio.total_exposure)} monitored`} />
          <Kpi label="Red-bucket exposure" value={inrCr(portfolio.red_exposure)} accent={RAG.red}
            hint={`${portfolio.buckets.red.count} red accounts`} />
          <Kpi label="Amber-bucket exposure" value={inrCr(portfolio.buckets.amber.exposure)} accent={RAG.amber}
            hint={`${portfolio.buckets.amber.count} amber accounts`} />
          <Kpi label="Avg runway (red)" value={`${portfolio.avg_runway_red.toFixed(1)} mo`} accent={RAG.red}
            hint={`${portfolio.avg_runway_flagged.toFixed(1)} mo flagged · ${portfolio.avg_runway.toFixed(1)} mo whole book`} />
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
                />
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

        {/* Right column: provision impact + sector */}
        <div className="space-y-6">
          {portfolio && <ProvisionImpact portfolio={portfolio} />}
          {portfolio && <SectorExposure portfolio={portfolio} />}
        </div>
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
