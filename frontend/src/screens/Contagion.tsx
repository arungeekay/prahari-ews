import { useEffect, useMemo, useRef, useState } from 'react'
import {
  forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide, forceX, forceY,
  type SimulationNodeDatum, type SimulationLinkDatum, type Simulation,
} from 'd3-force'
import { api } from '../api'
import type { ContagionGraph, GraphNode, SupplierNode, AnchorNode } from '../types'
import { useNav } from '../nav'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, stressColor } from '../components/ui'
import { pct } from '../format'

const W = 900
const H = 600
const ANCHOR1 = 'ANCH1'

type SimNode = GraphNode & SimulationNodeDatum
interface SimLink extends SimulationLinkDatum<SimNode> {
  amount: number
  inflow_share: number
}

const nodeRadius = (n: GraphNode) =>
  n.kind === 'anchor' ? 16 + Math.min(12, n.n_suppliers * 0.6) : 6 + (n.stress ?? 0) * 9

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
                  strokeOpacity={hot ? 0.55 : 0.35}
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
            ? <AnchorPanel anchor={selNode} suppliers={nodes.filter((n): n is SimNode & SupplierNode => n.kind === 'supplier' && n.anchor_id === selNode.id)} onOpen={openAccount} />
            : selNode && selNode.kind === 'supplier'
              ? <SupplierPanel supplier={selNode} anchor={nodes.find((n) => n.id === selNode.anchor_id) as (SimNode & AnchorNode) | undefined} onOpen={openAccount} onAnchor={setSelected} />
              : null}
        </div>
      </div>
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

function AnchorPanel({
  anchor, suppliers, onOpen,
}: { anchor: AnchorNode; suppliers: (SupplierNode & SimulationNodeDatum)[]; onOpen: (id: string) => void }) {
  const sorted = [...suppliers].sort((a, b) => a.runway_delta - b.runway_delta)
  return (
    <Card className="p-5">
      <SectionTitle sub={`Anchor buyer · ${anchor.n_suppliers} suppliers in the book`}>{anchor.label}</SectionTitle>
      <div className="rounded-xl bg-rag-red/5 border border-rag-red/20 p-3 mb-4 text-sm text-slate-700">
        Payment slowdown at this anchor is shortening its suppliers' runway clocks even while their own
        repayment records are still clean. Anchor stress: <b style={{ color: RAG.red }}>{pct(anchor.stress, 0)}</b>.
      </div>
      <div className="text-[11px] uppercase tracking-wide text-muted mb-2">Suppliers by runway impact</div>
      <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
        {sorted.map((s) => (
          <button key={s.id} onClick={() => onOpen(s.id)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-line hover:border-teal/50 hover:bg-teal/5 transition-colors text-left">
            <div className="min-w-0">
              <div className="text-sm font-medium text-ink truncate">{s.label}</div>
              <div className="text-[11px] text-muted capitalize">{s.sector.replace('_', ' ')} · adj. PD {pct(s.contagion_adjusted_pd, 0)}</div>
            </div>
            <div className="text-sm font-bold shrink-0" style={{ color: RAG.red }}>
              {s.runway_delta.toFixed(1)} mo
            </div>
          </button>
        ))}
      </div>
    </Card>
  )
}

function SupplierPanel({
  supplier, anchor, onOpen, onAnchor,
}: {
  supplier: SupplierNode; anchor?: AnchorNode; onOpen: (id: string) => void; onAnchor: (id: string) => void
}) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Supplier node">{supplier.label}</SectionTitle>
      <Row label="Own PD" value={pct(supplier.own_pd)} />
      <Row label="Contagion-adjusted PD" value={pct(supplier.contagion_adjusted_pd)} accent={RAG.red} />
      <Row label="Runway impact" value={`${supplier.runway_delta.toFixed(1)} months`} accent={RAG.red} />
      <Row label="Stress" value={pct(supplier.stress, 0)} />
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

function Row({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-line last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className="text-sm font-semibold" style={{ color: accent ?? '#0A1F44' }}>{value}</span>
    </div>
  )
}
