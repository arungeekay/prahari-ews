import { useEffect, useMemo, useRef, useState } from 'react'
import {
  forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide, forceX, forceY,
  type SimulationNodeDatum, type SimulationLinkDatum, type Simulation,
} from 'd3-force'
import { api } from '../api'
import type {
  ContagionGraph, ContagionMethod, ContagionNodeResult, GraphNode, SupplierNode, AnchorNode, Scenario,
} from '../types'
import { useNav } from '../nav'
import { useFramework } from '../framework'
import { isStatic } from '../components/anim'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, MiniStat, stressColor, PdDelta, Chip, RagChip } from '../components/ui'
import { pct, inr } from '../format'

const W = 900
const H = 600
const ANCHOR1 = 'ANCH1'

type SimNode = GraphNode & SimulationNodeDatum
interface SimLink extends SimulationLinkDatum<SimNode> {
  amount: number
  inflow_share: number
  regularity: number
}

const nodeRadius = (n: GraphNode) =>
  n.kind === 'anchor' ? 16 + Math.min(12, n.n_suppliers * 0.6) : 6 + (n.stress ?? 0) * 9

/** node_result() per supplier, fetched lazily from /api/accounts/{id} and kept for the session. */
const nodeResultCache = new Map<string, ContagionNodeResult | null>()

export function Contagion() {
  const { openAccount } = useNav()
  const [graph, setGraph] = useState<ContagionGraph | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [nodes, setNodes] = useState<SimNode[]>([])
  const [links, setLinks] = useState<SimLink[]>([])
  const [selected, setSelected] = useState<string>(ANCHOR1)
  const simRef = useRef<Simulation<SimNode, undefined> | null>(null)

  useEffect(() => {
    api.contagion().then(setGraph).catch((e) => setErr(String(e)))
  }, [])

  useEffect(() => {
    if (!graph) return
    const simNodes: SimNode[] = graph.nodes.map((n, i) => ({
      ...n,
      x: W / 2 + Math.cos((i / graph.nodes.length) * 2 * Math.PI) * 200,
      y: H / 2 + Math.sin((i / graph.nodes.length) * 2 * Math.PI) * 200,
    }))
    const simLinks: SimLink[] = graph.edges.map((e) => ({ ...e }))

    const sim = forceSimulation<SimNode>(simNodes)
      .force('charge', forceManyBody<SimNode>().strength((d) => (d.kind === 'anchor' ? -520 : -120)))
      .force('link', forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(70).strength(0.6))
      .force('center', forceCenter(W / 2, H / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => nodeRadius(d) + 6))
      .force('x', forceX(W / 2).strength(0.04))
      .force('y', forceY(H / 2).strength(0.06))
      .alpha(1)

    if (isStatic()) {
      // settle the layout synchronously so the graph renders in its final state at once
      sim.stop()
      sim.tick(300)
      setNodes([...simNodes])
      setLinks([...simLinks])
      simRef.current = sim
      return () => { sim.stop() }
    }
    sim.on('tick', () => {
      setNodes([...simNodes])
      setLinks([...simLinks])
    })
    simRef.current = sim
    return () => { sim.stop() }
  }, [graph])

  const related = useMemo(() => {
    const set = new Set<string>([selected])
    const sel = nodes.find((n) => n.id === selected)
    if (!sel) return set
    if (sel.kind === 'anchor') {
      nodes.forEach((n) => { if (n.kind === 'supplier' && n.anchor_id === selected) set.add(n.id) })
    } else {
      set.add(sel.anchor_id)
    }
    return set
  }, [selected, nodes])

  if (err) return <ErrorBox message={err} />
  if (!graph || nodes.length === 0) return <Spinner label="Building the anchor payment graph…" />

  const selNode = nodes.find((n) => n.id === selected)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-ink tracking-tight">Contagion Map</h2>
        <p className="text-teal text-sm mt-1 font-medium">PRAHARI watches the economy between the accounts.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-2 p-3">
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} className="select-none">
            {/* edges */}
            {links.map((l, i) => {
              const s = l.source as SimNode
              const t = l.target as SimNode
              if (s?.x == null || t?.x == null || s.y == null || t.y == null) return null
              const hot = related.has(s.id) && related.has(t.id)
              return (
                <line
                  key={i}
                  x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                  stroke={hot ? RAG.red : '#D7DEEA'}
                  strokeWidth={hot ? 1 + l.inflow_share * 4 : 0.8}
                  strokeOpacity={hot ? 0.35 + 0.4 * (l.regularity ?? 0.5) : 0.35}
                />
              )
            })}
            {/* nodes */}
            {nodes.map((n) => {
              const r = nodeRadius(n)
              const focused = related.has(n.id)
              const isAnchor = n.kind === 'anchor'
              const fill = isAnchor ? RAG[stressBucket(n.stress)] : stressColor(n.stress ?? 0)
              return (
                <g key={n.id}
                  transform={`translate(${n.x},${n.y})`}
                  onClick={() => setSelected(n.id)}
                  style={{ cursor: 'pointer', opacity: focused ? 1 : 0.22, transition: 'opacity .3s' }}
                >
                  {n.id === selected && (
                    <circle r={r + 5} fill="none" stroke={RAG.red} strokeWidth={2} strokeOpacity={0.6} />
                  )}
                  <circle r={r} fill={fill} stroke="#fff" strokeWidth={isAnchor ? 2.5 : 1.25} />
                  {(isAnchor || focused) && (
                    <text
                      x={0} y={isAnchor ? -r - 6 : -r - 4}
                      textAnchor="middle"
                      fontSize={isAnchor ? 12 : 9.5}
                      fontWeight={isAnchor ? 700 : 500}
                      fill="#0A1F44"
                    >
                      {isAnchor ? n.label : truncate(n.label, 18)}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
          <div className="flex items-center gap-4 px-2 pb-1 text-xs text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="w-3.5 h-3.5 rounded-full bg-ink/70" /> Anchor buyer</span>
            {(['red', 'amber', 'green'] as const).map((b) => (
              <span key={b} className="inline-flex items-center gap-1.5 capitalize">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: RAG[b] }} /> {b === 'red' ? 'high' : b === 'amber' ? 'medium' : 'low'} stress
              </span>
            ))}
            <span className="ml-auto italic">Tip: click Bharat Auto Components Ltd (Anchor #1) to trace its suppliers.</span>
          </div>
        </Card>

        {/* Side panel */}
        <div>
          {selNode && selNode.kind === 'anchor'
            ? <AnchorPanel anchor={selNode} method={graph.method}
                suppliers={nodes.filter((n): n is SimNode & SupplierNode => n.kind === 'supplier' && n.anchor_id === selNode.id)}
                onOpen={openAccount} />
            : selNode && selNode.kind === 'supplier'
              ? <SupplierPanel supplier={selNode} method={graph.method}
                  anchor={nodes.find((n) => n.id === selNode.anchor_id) as (SimNode & AnchorNode) | undefined}
                  onOpen={openAccount} onAnchor={setSelected} />
              : null}
        </div>
      </div>

      {/* Portfolio stress test for the selected anchor; keyed so the slider resets per anchor */}
      {selNode && selNode.kind === 'anchor' && <ScenarioPanel key={selNode.id} anchor={selNode} />}
    </div>
  )
}

function stressBucket(s: number): 'red' | 'amber' | 'green' {
  if (s >= 0.66) return 'red'
  if (s >= 0.33) return 'amber'
  return 'green'
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

function MethodLine({ method }: { method: ContagionMethod }) {
  return (
    <div className="text-[11px] text-muted leading-snug rounded-xl bg-paper border border-line p-2.5">
      <b className="font-semibold text-slate-600">How it is computed:</b> anchor stress is {method.anchor_stress} with elasticity {method.elasticity};
      then <code className="font-mono text-[10.5px] text-ink">{method.equation}</code>, {method.iterations} passes, recomputed from own stress each pass so nothing is counted twice.
    </div>
  )
}

function AnchorPanel({
  anchor, suppliers, method, onOpen,
}: { anchor: AnchorNode; suppliers: (SupplierNode & SimulationNodeDatum)[]; method: ContagionMethod; onOpen: (id: string) => void }) {
  const sorted = [...suppliers].sort((a, b) => a.runway_delta - b.runway_delta)
  const measured = anchor.inflow_decline != null
  return (
    <Card className="p-5">
      <SectionTitle sub={`Anchor buyer · ${anchor.n_suppliers} suppliers in the book · ${anchor.sector.replace('_', ' ')}`}>{anchor.label}</SectionTitle>
      <div className="grid grid-cols-3 gap-2 mb-3">
        <MiniStat label="Inflow decline" value={measured ? pct(anchor.inflow_decline as number, 0) : 'n/a'}
          accent={measured && (anchor.inflow_decline as number) > 0 ? RAG.red : undefined} sub="measured" />
        <MiniStat label="Suppliers measured" value={String(anchor.n_suppliers_measured)} sub={`of ${anchor.n_suppliers}`} />
        <MiniStat label="Anchor stress" value={pct(anchor.stress, 0)} accent={stressColor(anchor.stress)} sub="0 to 100" />
      </div>
      <div className="rounded-xl bg-rag-red/5 border border-rag-red/20 p-3 mb-3 text-sm text-slate-700 leading-relaxed">
        {measured ? (
          <>Payments from this anchor to its suppliers fell <b style={{ color: RAG.red }}>{pct(anchor.inflow_decline as number, 0)}</b> (median across {anchor.n_suppliers_measured} suppliers, recent months versus baseline).
            That slowdown shortens the suppliers' runway clocks even while their own repayment records are still clean.</>
        ) : (
          <>No anchor-attributable inflow series is available for this anchor, so a documented fallback stress of {pct(anchor.stress, 0)} is applied.</>
        )}
      </div>
      <div className="mb-4"><MethodLine method={method} /></div>
      <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Suppliers by runway impact</div>
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto pr-1">
        {sorted.map((s) => (
          <button key={s.id} onClick={() => onOpen(s.id)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-line hover:border-teal/50 hover:bg-teal/5 transition-colors text-left">
            <div className="min-w-0">
              <div className="text-sm font-medium text-ink truncate">{s.label}</div>
              <div className="text-[11px] text-muted capitalize">
                {s.sector.replace('_', ' ')} · PD {pct(s.own_pd, 0)} → adj. {pct(s.contagion_adjusted_pd, 0)}
              </div>
            </div>
            <div className="text-sm font-bold shrink-0" style={{ color: s.runway_delta < 0 ? RAG.red : '#0A1F44' }}>
              {s.runway_delta > 0 ? '+' : ''}{s.runway_delta.toFixed(1)} mo
            </div>
          </button>
        ))}
      </div>
    </Card>
  )
}

function SupplierPanel({
  supplier, anchor, method, onOpen, onAnchor,
}: {
  supplier: SupplierNode; anchor?: AnchorNode; method: ContagionMethod
  onOpen: (id: string) => void; onAnchor: (id: string) => void
}) {
  const fw = useFramework()
  // undefined = loading, null = unavailable
  const [detail, setDetail] = useState<ContagionNodeResult | null | undefined>(
    () => nodeResultCache.has(supplier.id) ? nodeResultCache.get(supplier.id) : undefined,
  )

  useEffect(() => {
    let alive = true
    if (nodeResultCache.has(supplier.id)) {
      setDetail(nodeResultCache.get(supplier.id))
      return
    }
    setDetail(undefined)
    api.account(supplier.id)
      .then((d) => { nodeResultCache.set(supplier.id, d.contagion); if (alive) setDetail(d.contagion) })
      .catch(() => { if (alive) setDetail(null) })
    return () => { alive = false }
  }, [supplier.id])

  const added = supplier.contagion_adjusted_pd - supplier.own_pd
  const ownC = fw.pdColor(supplier.own_pd)
  const adjC = fw.pdColor(supplier.contagion_adjusted_pd)
  const ownBucket = fw.pdBucket(supplier.own_pd)
  const adjBucket = fw.pdBucket(supplier.contagion_adjusted_pd)
  const rebucketed = ownBucket !== adjBucket

  return (
    <Card className="p-5">
      <SectionTitle sub={`Supplier node · ${supplier.sector.replace('_', ' ')}`}>{supplier.label}</SectionTitle>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="rounded-xl bg-paper border border-line p-3 text-center">
          <div className="text-[11px] uppercase tracking-wide text-muted">Own PD</div>
          <div className="text-xl font-bold mt-0.5" style={{ color: ownC }}>{pct(supplier.own_pd)}</div>
          <div className="text-[11px] text-muted capitalize">{ownBucket} on own conduct</div>
        </div>
        <div className="rounded-xl bg-paper border border-line p-3 text-center">
          <div className="text-[11px] uppercase tracking-wide text-muted">Contagion-adjusted</div>
          <div className="text-xl font-bold mt-0.5" style={{ color: adjC }}>{pct(supplier.contagion_adjusted_pd)}</div>
          <div className="text-[11px] text-muted capitalize">{adjBucket}{rebucketed ? ' · re-bucketed' : ''}</div>
        </div>
      </div>
      <div className="flex items-center gap-2 mb-2">
        <PdDelta delta={added} />
        <span className="text-xs text-muted">added by upstream stress</span>
      </div>
      <Row label="Runway impact" value={`${supplier.runway_delta > 0 ? '+' : ''}${supplier.runway_delta.toFixed(1)} months`}
        accent={supplier.runway_delta < 0 ? RAG.red : undefined} />
      <Row label="Node stress" value={pct(supplier.stress, 0)} />

      <div className="mt-3">
        {detail === undefined ? (
          <div className="text-xs text-muted flex items-center gap-2">
            <span className="w-3 h-3 rounded-full border-2 border-line border-t-brand animate-spin" /> Tracing the upstream cause…
          </div>
        ) : detail?.why ? (
          <p className="text-sm text-slate-700 bg-rag-red/5 border border-rag-red/20 rounded-xl p-3 leading-relaxed">{detail.why}</p>
        ) : (
          <p className="text-xs text-muted">No upstream anchor stress is adding to this account's PD at present.</p>
        )}
      </div>

      <div className="mt-3"><MethodLine method={method} /></div>

      {anchor && (
        <button onClick={() => onAnchor(anchor.id)} className="text-sm text-brand hover:underline mt-3">
          ← Upstream anchor: {anchor.label}
        </button>
      )}
      <button onClick={() => onOpen(supplier.id)}
        className="w-full mt-4 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors">
        Open account detail
      </button>
    </Card>
  )
}

function ScenarioPanel({ anchor }: { anchor: AnchorNode }) {
  const { openAccount } = useNav()
  const fw = useFramework()
  const measured = Math.round(Math.max(0, Math.min(1, anchor.stress ?? 0)) * 100)
  const [stressPct, setStressPct] = useState<number>(measured)
  const [res, setRes] = useState<Scenario | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const run = async (value: number) => {
    setBusy(true); setErr(null)
    try {
      setRes(await api.scenario(anchor.id, value / 100))
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }
  const preset = (value: number) => { setStressPct(value); void run(value) }

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub={`Override the measured payment stress of ${anchor.label} and re-run the diffusion over its ${anchor.n_suppliers} suppliers. Same auditable equation, one input changed.`}>
          Stress scenario
        </SectionTitle>
        <Chip dot={false} title="Stress measured from the decline in anchor-attributable inflows">measured stress {measured}%</Chip>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-end">
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted">Anchor payment stress</span>
            <span className="text-base font-bold text-ink">{stressPct}%</span>
          </div>
          <input
            type="range" min={0} max={100} step={1} value={stressPct}
            onChange={(e) => setStressPct(Number(e.target.value))}
            className="w-full accent-[#0B3D91]"
            aria-label="Anchor payment stress"
          />
          <div className="flex justify-between text-[10px] text-muted">
            <span>0% · pays as before</span>
            <span>100% · stops paying</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <button onClick={() => preset(100)} disabled={busy}
            className="px-3 py-2 rounded-xl text-xs font-semibold border border-rag-red/40 text-rag-red bg-rag-red/5 hover:bg-rag-red/10 transition-colors disabled:opacity-50">
            Anchor fails (100%)
          </button>
          <button onClick={() => preset(0)} disabled={busy}
            className="px-3 py-2 rounded-xl text-xs font-semibold border border-rag-green/40 text-rag-green bg-rag-green/5 hover:bg-rag-green/10 transition-colors disabled:opacity-50">
            Anchor recovers (0%)
          </button>
          <button onClick={() => run(stressPct)} disabled={busy}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors disabled:opacity-60">
            {busy ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      {err && <div className="mt-3 text-sm text-rag-red">{err}</div>}

      {res && (
        <div className="mt-5">
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            <BeforeAfter label="Exposure-weighted PD" before={pct(res.exposure_weighted_pd_before)} after={pct(res.exposure_weighted_pd_after)}
              worse={res.exposure_weighted_pd_after > res.exposure_weighted_pd_before} sub={`across ${inr(res.supplier_exposure)} of supplier exposure`} />
            <BeforeAfter label="Red exposure" before={inr(res.red_exposure_before)} after={inr(res.red_exposure_after)}
              worse={res.red_exposure_after > res.red_exposure_before} />
            <BeforeAfter label="Average runway" before={`${res.avg_runway_before.toFixed(1)} mo`} after={`${res.avg_runway_after.toFixed(1)} mo`}
              worse={res.avg_runway_after < res.avg_runway_before} />
            <BeforeAfter label="Expected-loss proxy" before={inr(res.expected_loss_proxy_before)} after={inr(res.expected_loss_proxy_after)}
              worse={res.expected_loss_proxy_after > res.expected_loss_proxy_before} sub="exposure x contagion-adjusted PD" />
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3 text-xs text-muted">
            <Chip color={res.n_rebucketed > 0 ? RAG.amber : RAG.green}>
              {res.n_rebucketed} of {res.n_suppliers} suppliers re-bucketed
            </Chip>
            <span>{inr(res.exposure_rebucketed)} of exposure changes bucket</span>
            <span>· provisioning at risk if newly red: {inr(res.provisioning_at_risk_delta)}</span>
            <span>· anchor stress {pct(res.stress_before, 0)} → {pct(res.stress_after, 0)}</span>
          </div>

          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                  <th className="py-2 pr-3 font-medium">Supplier</th>
                  <th className="py-2 px-3 font-medium text-right">Exposure</th>
                  <th className="py-2 px-3 font-medium text-right whitespace-nowrap">PD before → after</th>
                  <th className="py-2 px-3 font-medium">Bucket</th>
                  <th className="py-2 pl-3 font-medium text-right whitespace-nowrap">Runway before → after</th>
                </tr>
              </thead>
              <tbody>
                {res.suppliers.map((s) => {
                  const moved = s.bucket_before !== s.bucket_after
                  return (
                    <tr key={s.borrower_id} onClick={() => openAccount(s.borrower_id)}
                      className={`border-b border-line last:border-0 hover:bg-paper cursor-pointer ${moved ? 'bg-rag-amber/[0.04]' : ''}`}>
                      <td className="py-2 pr-3">
                        <div className="font-medium text-ink">{s.name}</div>
                        <div className="text-[11px] text-muted">{s.borrower_id} · own PD {pct(s.own_pd)}</div>
                      </td>
                      <td className="py-2 px-3 text-right font-semibold text-ink whitespace-nowrap">{inr(s.exposure)}</td>
                      <td className="py-2 px-3 text-right whitespace-nowrap">
                        <span className="text-muted">{pct(s.pd_before)}</span>
                        <span className="text-muted mx-1.5">→</span>
                        <span className="font-semibold" style={{ color: fw.pdColor(s.pd_after) }}>{pct(s.pd_after)}</span>
                        <PdDelta delta={s.pd_after - s.pd_before} className="ml-2" />
                      </td>
                      <td className="py-2 px-3 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5">
                          <RagChip bucket={s.bucket_before} />
                          <span className="text-muted">→</span>
                          <RagChip bucket={s.bucket_after} />
                        </span>
                      </td>
                      <td className="py-2 pl-3 text-right whitespace-nowrap">
                        <span className="text-muted">{s.runway_before.toFixed(1)}</span>
                        <span className="text-muted mx-1.5">→</span>
                        <span className="font-semibold" style={{ color: fw.runwayColor(s.runway_after) }}>{s.runway_after.toFixed(1)} mo</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-muted mt-3">Same auditable equation, one input changed.</p>
        </div>
      )}
    </Card>
  )
}

function BeforeAfter({ label, before, after, worse, sub }: { label: string; before: string; after: string; worse: boolean; sub?: string }) {
  const same = before === after
  const c = same ? '#5B6B85' : worse ? RAG.red : RAG.green
  return (
    <div className="rounded-xl bg-paper border border-line p-3 min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="flex items-center gap-2 mt-1 flex-wrap">
        <span className="text-sm text-muted">{before}</span>
        <span className="text-muted">→</span>
        <span className="text-lg font-bold" style={{ color: c }}>{after}</span>
      </div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
    </div>
  )
}

function Row({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-line last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-sm font-semibold" style={{ color: accent ?? '#0A1F44' }}>{value}</span>
    </div>
  )
}
