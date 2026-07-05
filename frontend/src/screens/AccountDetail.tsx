import { useEffect, useState } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { motion } from 'framer-motion'
import { api } from '../api'
import type { AccountDetail as Detail, WhatIf, ReasonCode, Beat, ComplianceClock, DocResp } from '../types'
import { useNav } from '../nav'
import { Card, SectionTitle, RagChip, Spinner, ErrorBox, RAG, pdColor } from '../components/ui'
import { Gauge } from '../components/Gauge'
import { RunwayDial } from '../components/RunwayDial'
import { DocumentModal } from '../components/DocumentModal'
import { inr, pct, monthLabel } from '../format'
import { useTween } from '../components/anim'

const ACTION_LABEL: Record<string, string> = {
  enhanced_monitoring: 'Enhanced monitoring',
  restructure: 'Restructure',
  limit_reduction: 'Limit reduction',
  collateral_topup: 'Collateral top-up',
}

export function AccountDetail({ id }: { id: string }) {
  const { go } = useNav()
  const [d, setD] = useState<Detail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sim, setSim] = useState<WhatIf | null>(null)
  const [simLoading, setSimLoading] = useState<string | null>(null)

  const [doc, setDoc] = useState<{ open: boolean; title: string; subtitle?: string; text: string | null; loading: boolean }>(
    { open: false, title: '', text: null, loading: false },
  )

  useEffect(() => {
    setD(null); setErr(null); setSim(null)
    api.account(id).then(setD).catch((e) => setErr(String(e)))
  }, [id])

  if (err) return <ErrorBox message={err} />
  if (!d) return <Spinner label="Loading account…" />

  const runwayShown = sim ? sim.runway_after : d.runway_months

  const runWhatIf = async (action: string) => {
    if (sim?.action === action) { setSim(null); return } // toggle off
    setSimLoading(action)
    try {
      const r = await api.whatif(id, action)
      setSim(r)
    } catch (e) {
      setErr(String(e))
    } finally {
      setSimLoading(null)
    }
  }

  const draft = async (kind: 'memo' | 'crilc') => {
    setDoc({
      open: true, loading: true, text: null,
      title: kind === 'memo' ? 'SMA early-warning memo' : 'CRILC reporting note',
      subtitle: `${d.name} · ${d.borrower_id}`,
    })
    try {
      const r: DocResp = kind === 'memo' ? await api.memo(id) : await api.crilc(id)
      setDoc((p) => ({ ...p, loading: false, text: r.text, title: r.document_type }))
    } catch (e) {
      setDoc((p) => ({ ...p, loading: false, text: `Failed to generate document: ${e}` }))
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <button onClick={() => go('portfolio')} className="text-muted hover:text-ink text-sm mb-2 inline-flex items-center gap-1">
            ← Portfolio
          </button>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-ink tracking-tight">{d.name}</h2>
            <RagChip bucket={d.bucket} />
            {d.borrower_id === 'MSME00001' && (
              <span className="text-[11px] font-semibold text-teal border border-teal/30 bg-teal/5 rounded-full px-2.5 py-1">
                Demo character
              </span>
            )}
          </div>
          <p className="text-muted text-sm mt-1">
            {d.borrower_id} · <span className="capitalize">{d.sector.replace('_', ' ')}</span> · {d.city}, {d.state} · {d.loan_type} facility
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => draft('memo')}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors shadow-soft">
            Draft SMA memo
          </button>
          <button onClick={() => draft('crilc')}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold text-brand border border-brand/30 bg-white hover:bg-brand/5 transition-colors">
            Draft CRILC report
          </button>
        </div>
      </div>

      {/* Top row: runway dial + PD gauge + stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-5 flex flex-col items-center justify-center">
          <SectionTitle sub="Projected months to 90+ DPD on current trajectory.">Runway clock</SectionTitle>
          <RunwayDial runway={runwayShown} />
          {sim && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              className="mt-2 text-sm font-semibold" style={{ color: sim.runway_delta >= 0 ? RAG.green : RAG.red }}>
              {sim.runway_delta >= 0 ? '+' : ''}{sim.runway_delta.toFixed(1)} months from “{ACTION_LABEL[sim.action] ?? sim.action}”
            </motion.div>
          )}
        </Card>

        <Card className="p-5 flex flex-col items-center justify-center">
          <SectionTitle sub="Probability of default within 12 months.">Probability of default</SectionTitle>
          <Gauge fraction={d.pd} color={pdColor(d.pd)} size={200} thickness={18}>
            <div className="text-4xl font-bold" style={{ color: pdColor(d.pd) }}>{pct(d.pd, 0)}</div>
            <div className="text-xs text-muted mt-1 font-medium tracking-wide">12-MONTH PD</div>
          </Gauge>
        </Card>

        <Card className="p-5">
          <SectionTitle>Exposure snapshot</SectionTitle>
          <Stat label="Exposure at risk" value={inr(d.exposure)} big />
          <Stat label="Sanctioned limit" value={inr(d.sanctioned_limit)} />
          <Stat label="Limit utilisation" value={pct(d.utilisation)} />
          <Stat label="Runway (model)" value={`${d.runway_label} months`} />
        </Card>
      </div>

      {/* What-if simulator */}
      <Card className="p-5">
        <SectionTitle sub="Simulate a supervisory action; the runway clock and provisioning update live.">
          What-if simulator
        </SectionTitle>
        <div className="flex flex-wrap gap-2 mb-4">
          {d.whatif_actions.map((a) => {
            const active = sim?.action === a
            return (
              <button
                key={a}
                onClick={() => runWhatIf(a)}
                disabled={simLoading != null}
                className={`px-4 py-2 rounded-xl text-sm font-medium border transition-colors ${
                  active ? 'bg-teal text-white border-teal' : 'bg-white text-slate-700 border-line hover:border-teal/50'
                } ${simLoading === a ? 'opacity-60' : ''}`}
              >
                {simLoading === a ? 'Simulating…' : (ACTION_LABEL[a] ?? a)}
              </button>
            )
          })}
          {sim && (
            <button onClick={() => setSim(null)}
              className="px-4 py-2 rounded-xl text-sm font-medium text-muted hover:text-ink">
              Reset
            </button>
          )}
        </div>
        {sim ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Delta label="Runway" before={`${sim.runway_before.toFixed(1)} mo`} after={`${sim.runway_after.toFixed(1)} mo`} good={sim.runway_after >= sim.runway_before} />
            <Delta label="Provisioning" before={inr(sim.provision_before)} after={inr(sim.provision_after)} good={sim.provision_after <= sim.provision_before} />
            <div className="rounded-xl bg-rag-green/5 border border-rag-green/20 p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">Saved vs. acting at NPA</div>
              <div className="text-xl font-bold text-rag-green mt-0.5">{inr(sim.provision_saved_vs_npa)}</div>
            </div>
            <p className="md:col-span-3 text-sm text-slate-600 bg-paper rounded-xl p-3 border border-line">{sim.note}</p>
          </motion.div>
        ) : (
          <p className="text-sm text-muted">Select an action to preview its effect on runway and provisioning.</p>
        )}
      </Card>

      {/* Storyline + reason codes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Storyline storyline={d.storyline} beats={d.beats} />
        <ReasonCodes reasons={d.reason_codes} />
      </div>

      {/* Series chart + compliance clocks */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SeriesChart d={d} />
        </div>
        <ComplianceClocks clocks={d.compliance_clocks} />
      </div>

      <DocumentModal
        open={doc.open} title={doc.title} subtitle={doc.subtitle} text={doc.text} loading={doc.loading}
        onClose={() => setDoc((p) => ({ ...p, open: false }))}
      />
    </div>
  )
}

function Stat({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-line last:border-0">
      <span className="text-sm text-muted">{label}</span>
      <span className={`font-semibold text-ink ${big ? 'text-xl' : 'text-sm'}`}>{value}</span>
    </div>
  )
}

function Delta({ label, before, after, good }: { label: string; before: string; after: string; good: boolean }) {
  return (
    <div className="rounded-xl bg-paper border border-line p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm text-muted line-through">{before}</span>
        <span className="text-muted">→</span>
        <span className="text-lg font-bold" style={{ color: good ? RAG.green : RAG.red }}>{after}</span>
      </div>
    </div>
  )
}

function Storyline({ storyline, beats }: { storyline: string; beats: Beat[] }) {
  // Drop the trailing disclaimer + "Key beats" block from the prose (beats are shown as a timeline).
  const prose = storyline.split('Key beats:')[0].split('- Draft prepared')[0].trim()
  const tail = storyline.includes('- Draft prepared') ? '- Draft prepared' + storyline.split('- Draft prepared')[1] : ''
  return (
    <Card className="p-5">
      <SectionTitle sub="How the account drifted from green to its current bucket.">Deterioration storyline</SectionTitle>
      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{prose}</p>
      <ol className="mt-4 relative border-l-2 border-line ml-1.5 space-y-4 pt-1">
        {beats.map((b, i) => (
          <motion.li key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }}
            className="ml-4 relative">
            <span className="absolute -left-[22px] top-1 w-3 h-3 rounded-full bg-rag-amber ring-4 ring-rag-amber/15" />
            <div className="text-[11px] font-semibold text-teal uppercase tracking-wide">
              Month {b.month} · {monthLabel(b.month_label)}
            </div>
            <div className="text-sm text-slate-700">{b.text}</div>
          </motion.li>
        ))}
      </ol>
      {tail && <p className="text-[11px] text-muted italic mt-4">{tail}</p>}
    </Card>
  )
}

function ReasonCodes({ reasons }: { reasons: ReasonCode[] }) {
  const maxAbs = Math.max(...reasons.map((r) => Math.abs(r.contribution)), 0.001)
  return (
    <Card className="p-5">
      <SectionTitle sub="Top model drivers (SHAP). Red pushes toward default; green is protective.">
        Why PRAHARI flagged this account
      </SectionTitle>
      <div className="space-y-3">
        {reasons.map((r) => {
          const positive = r.contribution >= 0
          const w = (Math.abs(r.contribution) / maxAbs) * 100
          return (
            <div key={r.factor}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-slate-700">{r.plain}</span>
                <span className="font-mono text-xs text-muted">{positive ? '+' : ''}{r.contribution.toFixed(2)}</span>
              </div>
              <div className="h-2 rounded-full bg-paper overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.max(3, w)}%`, background: positive ? RAG.red : RAG.green }} />
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function SeriesChart({ d }: { d: Detail }) {
  const data = d.series.map((s) => ({
    m: monthLabel(s.month_date),
    creditsL: +(s.credits / 1e5).toFixed(1),
    util: +(s.limit_utilisation * 100).toFixed(1),
  }))
  return (
    <Card className="p-5">
      <SectionTitle sub="Sales inflows falling while limit utilisation creeps up - the classic stress signature.">
        Monthly credits vs. limit utilisation
      </SectionTitle>
      <div style={{ width: '100%', height: 280 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <defs>
              <linearGradient id="credGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={RAG.green} stopOpacity={0.28} />
                <stop offset="100%" stopColor={RAG.green} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F8" vertical={false} />
            <XAxis dataKey="m" tick={{ fontSize: 10, fill: '#5B6B85' }} interval={2} tickLine={false} axisLine={{ stroke: '#E3E8F0' }} />
            <YAxis yAxisId="l" tick={{ fontSize: 10, fill: '#5B6B85' }} tickLine={false} axisLine={false}
              label={{ value: 'Credits (₹ L)', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#5B6B85', dy: 40 }} />
            <YAxis yAxisId="r" orientation="right" domain={[0, 100]} tick={{ fontSize: 10, fill: '#5B6B85' }} tickLine={false} axisLine={false}
              label={{ value: 'Utilisation %', angle: 90, position: 'insideRight', fontSize: 10, fill: '#5B6B85', dy: -34 }} />
            <Tooltip
              contentStyle={{ borderRadius: 12, border: '1px solid #E3E8F0', fontSize: 12 }}
              formatter={(v: any, name: any) => name === 'Credits (₹ L)' ? [`₹${v} L`, name] : [`${v}%`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="l" type="monotone" dataKey="creditsL" name="Credits (₹ L)" stroke={RAG.green} strokeWidth={2} fill="url(#credGrad)" />
            <Line yAxisId="r" type="monotone" dataKey="util" name="Utilisation %" stroke={RAG.red} strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function ComplianceClocks({ clocks }: { clocks: ComplianceClock[] }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Regulatory timelines triggered for red-flagged accounts.">Compliance clocks</SectionTitle>
      {clocks.length === 0 ? (
        <p className="text-sm text-muted">No compliance clocks active for this account.</p>
      ) : (
        <div className="space-y-4">
          {clocks.map((c) => <ClockCard key={c.name} clock={c} />)}
        </div>
      )}
    </Card>
  )
}

function ClockCard({ clock }: { clock: ComplianceClock }) {
  const days = useTween(clock.days_remaining, 900)
  const frac = clock.window_days > 0 ? Math.max(0, Math.min(1, clock.days_remaining / clock.window_days)) : 0
  const color = frac > 0.5 ? RAG.amber : RAG.red
  return (
    <div className="rounded-xl border border-line p-3.5 bg-paper/60">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-ink">{clock.name}</span>
        <span className="text-lg font-bold" style={{ color }}>{Math.round(days)}<span className="text-xs font-medium text-muted ml-1">days</span></span>
      </div>
      <div className="h-2 rounded-full bg-white mt-2 overflow-hidden border border-line">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${frac * 100}%`, background: color }} />
      </div>
      <p className="text-[11px] text-muted mt-1.5">{clock.detail}</p>
    </div>
  )
}
