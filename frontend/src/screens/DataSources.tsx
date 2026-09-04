import { useEffect, useState } from 'react'
import { api } from '../api'
import type { DataSources as DS, Feed, AdapterDemo } from '../types'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, Chip } from '../components/ui'
import { num } from '../format'

/** Catalogue names for the sample calls the adapter demo returns, keyed as the backend keys them. */
const API_NAMES: Record<string, string> = {
  api_394: 'getCustomerAccountsByCustId',
  api_391: 'getLoanAccountDetails',
  api_441: 'fetchLoanAccountLimits',
  api_402: 'getLoanOverdueDetails',
  api_404: 'getLoanOverduePositionEnquiry',
  api_393: 'getFullAccountStatementWithPagination',
  api_362: 'accountLienEnquiry',
}
const SAMPLE_ORDER = ['api_394', 'api_391', 'api_441', 'api_402', 'api_404', 'api_393', 'api_362']
/** Parity rows carry these identity fields; every other key is a mapped column. */
const PARITY_META = new Set(['borrower_id', 'name', 'months'])

/** Feed status colours: mapped and consent-flow green, external feed requested amber, external grey. */
function statusColor(status: string): string {
  const s = status.toLowerCase()
  if (s.startsWith('mapped') || s === 'consent flow mapped') return RAG.green
  if (s === 'external feed requested') return RAG.amber
  return '#5B6B85'
}

export function DataSources() {
  const [ds, setDs] = useState<DS | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.dataSources().then(setDs).catch((e) => setErr(String(e)))
  }, [])

  if (err) return <ErrorBox message={err} />
  if (!ds) return <Spinner label="Reading data provenance…" />

  const p = ds.provenance
  const rows: [string, string][] = [
    ['Source', String(p.source ?? '-')],
    ['Mode', p.mode != null ? String(p.mode) : '-'],
    ['Seed', p.seed != null ? String(p.seed) : '-'],
    ['As-of month', p.as_of_month != null ? String(p.as_of_month) : ds.as_of_label],
    ['Point-in-time enforced at', p.point_in_time_enforced_at != null ? String(p.point_in_time_enforced_at) : '-'],
    ['Rows (MSME monthly)', num(ds.rows)],
    ['Borrowers', num(ds.borrowers)],
    ['Months on file', `Month ${ds.months[0]} to ${ds.months[1]} · latest ${ds.as_of_label}`],
  ]
  if (p.base_url) rows.push(['Sandbox base URL', String(p.base_url)])
  if (p.history_months != null) rows.push(['History pulled', `${p.history_months} months`])
  if (p.catalogue && p.catalogue.length) rows.push(['API catalogue used', p.catalogue.join(', ')])

  const counts = ds.feeds.reduce<Record<string, number>>((acc, f) => {
    acc[f.status] = (acc[f.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink tracking-tight">Data Sources</h2>
          <p className="text-muted text-sm mt-1">
            Where every input comes from, in the bank's own API vocabulary. Point-in-time is enforced, so no feature uses data after the as-of month.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip color={RAG.green} title="Active data source">source: {p.source}</Chip>
          {p.mode != null && <Chip dot={false}>mode: {String(p.mode)}</Chip>}
          <Chip dot={false} title="How officer notes are scored">note scorer: {ds.note_scorer}</Chip>
          <Chip dot={false} title="Provider drafting memos and commentary">llm: {ds.llm_provider}</Chip>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="p-5">
          <SectionTitle sub="Recorded by the ingest layer when the book was loaded.">Provenance</SectionTitle>
          <dl>
            {rows.map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4 py-2 border-b border-line last:border-0">
                <dt className="text-sm text-muted shrink-0">{k}</dt>
                <dd className="text-sm font-semibold text-ink text-right break-words">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>

        <Card className="p-5 xl:col-span-2">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <SectionTitle sub="Each behavioural feed, the IDBI API numbers it maps to, and the columns it fills.">Feeds</SectionTitle>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(counts).map(([status, n]) => (
                <Chip key={status} color={statusColor(status)}>{status} · {n}</Chip>
              ))}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                  <th className="py-2 pr-3 font-medium">Feed</th>
                  <th className="py-2 px-3 font-medium">IDBI APIs</th>
                  <th className="py-2 px-3 font-medium">Columns</th>
                  <th className="py-2 pl-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {ds.feeds.map((f: Feed) => (
                  <tr key={f.feed} className="border-b border-line last:border-0 align-top">
                    <td className="py-2.5 pr-3">
                      <div className="font-medium text-ink">{f.feed}</div>
                      {f.mode && <div className="text-[11px] text-muted">mode: {f.mode}</div>}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">
                      {f.idbi_apis.length ? f.idbi_apis.join(', ') : <span className="text-muted">none (external)</span>}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex flex-wrap gap-1">
                        {f.columns.map((c) => (
                          <span key={c} className="text-[11px] font-mono px-1.5 py-0.5 rounded-md bg-paper border border-line text-slate-600">{c}</span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2.5 pl-3 whitespace-nowrap">
                      <Chip color={statusColor(f.status)}>{f.status}</Chip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <AdapterDemoCard />

      <Card className="p-5 border-teal/30 bg-teal/[0.03]">
        <SectionTitle>Coverage</SectionTitle>
        <p className="text-sm text-slate-700 leading-relaxed">{ds.coverage_note}</p>
      </Card>
    </div>
  )
}

/** POST /api/data-sources/adapter-demo: the IDBI-catalogue adapter run live against the Finacle-shaped mock. */
function AdapterDemoCard() {
  const [r, setR] = useState<AdapterDemo | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const run = async () => {
    setBusy(true); setErr(null)
    try {
      setR(await api.adapterDemo())
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const cols = r && r.parity.length ? Object.keys(r.parity[0]).filter((k) => !PARITY_META.has(k)) : []
  const sampleKeys = r
    ? [...SAMPLE_ORDER.filter((k) => k in r.samples), ...Object.keys(r.samples).filter((k) => !SAMPLE_ORDER.includes(k))]
    : []
  const p = r?.provenance

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub="Pull the demo cast through the IDBI-catalogue adapter against the Finacle-shaped mock, live: the wire payloads, and the parity of what came back against the book.">
          Run the adapter live
        </SectionTitle>
        <button
          onClick={run} disabled={busy}
          className="px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors shadow-soft disabled:opacity-50"
        >
          {busy ? 'Calling the catalogue…' : r ? 'Run again' : 'Run the adapter live'}
        </button>
      </div>

      {err && <div className="text-sm text-rag-red">{err}</div>}
      {busy && <Spinner label="Calling the IDBI catalogue through the adapter…" />}
      {!busy && !r && !err && (
        <p className="text-sm text-muted">Nothing has run yet. The call takes a few seconds and touches every API in the catalogue for three accounts.</p>
      )}

      {r && !busy && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-bold text-ink">
              {num(r.api_calls)} catalogue calls in {r.seconds}s for {r.cif_ids.length} accounts
            </span>
            {p && <Chip color={RAG.green} title="Active data source">source: {String(p.source ?? '-')}</Chip>}
            {p?.mode != null && <Chip dot={false}>mode: {String(p.mode)}</Chip>}
            {p?.base_url && <Chip dot={false} title="Sandbox base URL">{String(p.base_url)}</Chip>}
            {p?.history_months != null && <Chip dot={false}>{p.history_months} months pulled</Chip>}
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted font-medium mb-1.5">Parity against the book</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                    <th className="py-2 pr-3 font-medium">Account</th>
                    <th className="py-2 px-2 font-medium text-right">Months</th>
                    {cols.map((c) => (
                      <th key={c} className="py-2 px-2 font-mono font-medium normal-case tracking-normal">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.parity.map((row) => (
                    <tr key={row.borrower_id} className="border-b border-line last:border-0 align-top">
                      <td className="py-2 pr-3">
                        <div className="font-medium text-ink">{row.name}</div>
                        <div className="text-[11px] text-muted">{row.borrower_id}</div>
                      </td>
                      <td className="py-2 px-2 text-right text-slate-600">{row.months}</td>
                      {cols.map((c) => {
                        const val = Number(row[c])
                        const ok = val === 0
                        return (
                          <td key={c} className="py-2 px-2">
                            <Chip color={ok ? RAG.green : RAG.amber} dot={false} title={ok ? 'identical to the book' : 'differs from the book'}>
                              {Number.isFinite(val) ? val : String(row[c])}
                            </Chip>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-muted mt-1.5">Max scaled difference, 0 means identical.</p>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted font-medium mb-1.5">Filled as gaps: not in the catalogue</div>
            {r.external_columns_filled.length === 0 ? (
              <p className="text-sm text-muted">Every column came from the catalogue.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {r.external_columns_filled.map((c) => (
                  <Chip key={c} color={RAG.amber} dot={false} className="font-mono">{c}</Chip>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wide text-muted font-medium mb-1.5">Sample calls, exactly as they travel on the wire</div>
            <div className="rounded-xl border border-line divide-y divide-line overflow-hidden">
              {sampleKeys.map((k) => {
                const s = r.samples[k]
                const n = k.replace('api_', '')
                const isOpen = !!open[k]
                return (
                  <div key={k}>
                    <button
                      onClick={() => setOpen((o) => ({ ...o, [k]: !o[k] }))}
                      className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-paper transition-colors"
                    >
                      <span className="text-sm">
                        <span className="font-semibold text-ink">API {n}</span>
                        <span className="font-mono text-xs text-slate-600 ml-2">{API_NAMES[k] ?? ''}</span>
                      </span>
                      <span className="text-xs text-muted">{isOpen ? 'hide' : 'show'}</span>
                    </button>
                    {isOpen && (
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 px-4 pb-4">
                        <JsonBlock title="Request" value={s.request} />
                        <JsonBlock title="Response" value={s.response} />
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          <p className="text-[11px] text-muted italic leading-snug">{r.note}</p>
        </div>
      )}
    </Card>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-muted mb-1">{title}</div>
      <pre className="text-[11px] font-mono bg-paper border border-line rounded-xl p-3 overflow-auto max-h-72 text-slate-700 whitespace-pre">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}
