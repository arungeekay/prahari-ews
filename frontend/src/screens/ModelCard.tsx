import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
  BarChart, Bar, Cell, LabelList,
} from 'recharts'
import { api } from '../api'
import type {
  ModelCard as Card_, CostOfError, ModelMetrics, ThresholdPoint, DecileRow, LeadTimeRow, BaselineRow,
  Calibration, SegmentRow, RunwayCard, Ablation, SegmentModelRow, ValueAtScale,
} from '../types'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, CountUpCr, Chip, MiniStat } from '../components/ui'
import { pct, num, inr, pp } from '../format'

const TOOLTIP_STYLE = { borderRadius: 12, border: '1px solid #E3E8F0', fontSize: 12 }
const AXIS_TICK = { fontSize: 10, fill: '#5B6B85' }

export function ModelCard() {
  const [mc, setMc] = useState<Card_ | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.modelCard().then(setMc).catch((e) => setErr(String(e)))
  }, [])

  if (err) return <ErrorBox message={err} />
  if (!mc) return <Spinner label="Loading model card…" />

  const m = mc.metrics

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink tracking-tight">{mc.name}</h2>
          <p className="text-muted text-sm mt-1">{mc.task} · {mc.algorithm}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip dot={false}>{m.horizon_months}-month horizon</Chip>
          <Chip dot={false}>{m.n_features} features</Chip>
          <Chip dot={false} title="How reason codes are computed">explainer: {mc.explainer_backend}</Chip>
          <Chip dot={false} title="How officer notes are scored">note scorer: {mc.note_scorer}</Chip>
        </div>
      </div>

      {/* 1. Headline tiles */}
      <HeadlineTiles m={m} />

      {/* Value at bank scale: the same recall and alert rate on the bank's own book */}
      <ValueCalculator m={m} />

      {/* 2. Alert budget */}
      <AlertBudget m={m} />

      {/* 3 + 4. Deciles and lead time */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <DecileTable rows={m.deciles} />
        <LeadTime rows={m.lead_time} thr={m.lead_time_threshold} />
      </div>

      {/* 5. Baselines */}
      <Baselines rows={m.baselines} />

      {/* 6 + 7. Calibration and segments */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <CalibrationPanel c={m.calibration} method={m.calibration_method} />
        <Segments rows={m.segments} />
      </div>

      {/* Ablation (bank-internal data only) and per-loan-type challengers */}
      {(m.ablation || (m.segment_models && m.segment_models.length > 0)) && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {m.ablation && <AblationPanel a={m.ablation} nFeatures={m.n_features} />}
          {m.segment_models && m.segment_models.length > 0 && <SegmentModelsPanel rows={m.segment_models} />}
        </div>
      )}

      {/* 8 + 9. Validation design and confusion matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ValidationDesign m={m} />
        <ConfusionPanel m={m} />
      </div>

      {/* Runway (time-to-90+DPD) model evidence */}
      {mc.runway && <RunwayModelPanel r={mc.runway} />}

      {/* Cost of error - the money argument for high recall */}
      {mc.cost_of_error && <CostOfErrorPanel c={mc.cost_of_error} />}

      {/* Honesty note */}
      <Card className="p-5 border-teal/30 bg-teal/[0.03]">
        <SectionTitle>Honesty note</SectionTitle>
        <p className="text-sm text-slate-700 leading-relaxed">{mc.honesty_note}</p>
      </Card>

      {/* Features by pillar */}
      <Features card={mc} />
    </div>
  )
}

// ------------------------------------------------------------------ 1. headline
function HeadlineTiles({ m }: { m: ModelMetrics }) {
  const ci = m.auc_ci95
  const ciTxt = ci.low != null && ci.high != null
    ? `95% CI ${ci.low.toFixed(3)} to ${ci.high.toFixed(3)} · ${ci.n_boot} bootstraps`
    : 'confidence interval unavailable'
  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <Headline label="AUC" value={m.auc.toFixed(3)} accent={RAG.green} sub={ciTxt} big />
        <Headline label="KS" value={m.ks.toFixed(3)} sub="max separation of defaulters" />
        <Headline label="Brier" value={m.calibration.brier.toFixed(4)} sub="calibration error, lower is better" />
        <Headline label="Accuracy" value={pct(m.accuracy, 1)} sub="raw accuracy" />
        <Headline label="Balanced accuracy" value={pct(m.balanced_accuracy, 1)} sub="mean of recall and specificity" />
        <Headline label="Recall" value={pct(m.recall, 1)} accent={RAG.green} sub="eventual defaults caught" />
        <Headline label="Precision" value={pct(m.precision, 1)} sub="alerts that went on to default" />
      </div>
      <p className="text-[11px] text-muted mt-2">
        Reported at the bank 90 percent accuracy operating point (threshold {m.operating_threshold.toFixed(3)}), on validation fold C:
        {' '}{num(m.n_valid)} account-months from {num(m.n_borrowers_valid)} borrowers the model never saw, at as-of months after the training window.
      </p>
    </div>
  )
}

function Headline({ label, value, sub, big, accent }: { label: string; value: string; sub?: string; big?: boolean; accent?: string }) {
  return (
    <Card className="p-4 min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`font-bold mt-1 ${big ? 'text-3xl' : 'text-2xl'}`} style={{ color: accent ?? '#0A1F44' }}>{value}</div>
      {sub && <div className="text-[11px] text-muted mt-0.5 leading-snug">{sub}</div>}
    </Card>
  )
}

// ------------------------------------------------------------------ value at bank scale
interface ValueForm { bookCr: string; defaultRatePct: string; ticketLakh: string; reviewCost: string }

function NumberField({
  label, unit, value, onChange, step = 1,
}: { label: string; unit: string; value: string; onChange: (v: string) => void; step?: number }) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wide text-muted">{label}</span>
      <div className="flex items-center gap-2 mt-1 rounded-xl border border-line bg-paper/60 px-3 py-2 focus-within:border-teal/60 focus-within:bg-white">
        <input
          type="number" inputMode="decimal" min={0} step={step} value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-transparent text-sm text-ink font-semibold focus:outline-none"
        />
        <span className="text-[11px] text-muted whitespace-nowrap">{unit}</span>
      </div>
    </label>
  )
}

/** GET /api/value: the validation-fold recall and alert rate applied to a book of the bank's own size. */
function ValueCalculator({ m }: { m: ModelMetrics }) {
  const [form, setForm] = useState<ValueForm>(() => ({
    bookCr: '40000',
    defaultRatePct: (m.valid_positive_rate * 100).toFixed(1),
    ticketLakh: '75',
    reviewCost: '5000',
  }))
  const [v, setV] = useState<ValueAtScale | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const bookCr = Number(form.bookCr)
  const defaultRate = Number(form.defaultRatePct) / 100
  const ticketLakh = Number(form.ticketLakh)
  const reviewCost = Number(form.reviewCost)
  const valid = [bookCr, defaultRate, ticketLakh, reviewCost].every((x) => Number.isFinite(x) && x > 0)

  useEffect(() => {
    if (!valid) return
    const handle = setTimeout(() => {
      setBusy(true)
      api.value({ book_cr: bookCr, default_rate: defaultRate, avg_ticket_lakh: ticketLakh, review_cost: reviewCost })
        .then((r) => { setV(r); setErr(null) })
        .catch((e) => setErr(String(e)))
        .finally(() => setBusy(false))
    }, 350)
    return () => clearTimeout(handle)
  }, [bookCr, defaultRate, ticketLakh, reviewCost, valid])

  const set = (k: keyof ValueForm) => (val: string) => setForm((f) => ({ ...f, [k]: val }))

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub="Put in your own book. The arithmetic applies the validation-fold recall and alert rate at the bank 90 operating point; every assumption is returned with the number.">
          Value at bank scale
        </SectionTitle>
        <Chip color={RAG.amber} dot={false} title="Illustrative arithmetic on stated assumptions, not a forecast">illustrative</Chip>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className="lg:col-span-2 grid grid-cols-2 gap-3 content-start">
          <NumberField label="Book size" unit="₹ crore" value={form.bookCr} onChange={set('bookCr')} step={1000} />
          <NumberField label="12-month default rate" unit="percent" value={form.defaultRatePct} onChange={set('defaultRatePct')} step={0.1} />
          <NumberField label="Average ticket" unit="₹ lakh" value={form.ticketLakh} onChange={set('ticketLakh')} step={5} />
          <NumberField label="Review cost" unit="₹ per alert" value={form.reviewCost} onChange={set('reviewCost')} step={500} />
          {!valid && <p className="col-span-2 text-[11px] text-rag-red">Every input must be a positive number.</p>}
          {v && (
            <p className="col-span-2 text-[11px] text-muted leading-snug">
              Operating point: threshold {v.operating_point.threshold != null ? v.operating_point.threshold.toFixed(3) : '-'} ·
              recall {pct(v.operating_point.recall)} · precision {pct(v.operating_point.precision)} · alerts {pct(v.operating_point.alert_rate)} of the book.
            </p>
          )}
        </div>
        <div className="lg:col-span-3">
          {err ? (
            <div className="text-sm text-rag-red">{err}</div>
          ) : !v ? (
            <Spinner label="Working it out…" />
          ) : (
            <div className={`transition-opacity ${busy ? 'opacity-60' : ''}`}>
              <div className="rounded-xl bg-rag-green/5 border border-rag-green/20 p-5 text-center">
                <div className="text-[11px] uppercase tracking-wide text-muted">Provisioning actionable per twelve-month cycle</div>
                <div className="text-3xl font-bold text-rag-green mt-1">
                  <CountUpCr value={v.provisioning_actionable} />
                </div>
                <div className="text-[11px] text-muted mt-1.5">
                  {inr(v.caught_default_exposure)} of {inr(v.expected_default_exposure)} expected default exposure flagged in time
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                <MiniStat label="Accounts" value={num(v.n_accounts)} sub="book divided by average ticket" />
                <MiniStat label="Alerts per cycle" value={num(v.alerts_per_cycle)} accent={RAG.amber} sub={`${pct(v.operating_point.alert_rate)} of the book`} />
                <MiniStat label="Review cost" value={inr(v.review_cost_total)} sub={`${inr(v.inputs.review_cost)} per alert`} />
                <MiniStat label="Actionable per review rupee" value={`₹${v.actionable_per_review_rupee.toFixed(1)}`} accent={RAG.green}
                  sub="provisioning actionable divided by review cost" />
              </div>
              <p className="text-[11px] text-muted italic mt-3 leading-snug">Illustrative: {v.note}</p>
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ ablation: bank-internal data only
function AblationPanel({ a, nFeatures }: { a: Ablation; nFeatures: number }) {
  const aucGap = a.full_model_auc - a.internal_only_auc
  const recGap = a.full_model_recall_at_budget - a.internal_only_recall_at_budget
  return (
    <Card className="p-5">
      <SectionTitle sub={`Same folds, same alert budget of ${num(a.alert_budget)} alerts, retrained on only the columns the core-banking catalogue provides. What if the external feeds never arrive?`}>
        Bank-internal data only (ablation)
      </SectionTitle>
      <div className="grid grid-cols-2 gap-3">
        <AblationTile title="Full model" sub={`${num(nFeatures)} features, internal and external`}
          auc={a.full_model_auc} recall={a.full_model_recall_at_budget} />
        <AblationTile title="Internal only" sub={`${num(a.n_internal_features)} features from the IDBI catalogue`}
          auc={a.internal_only_auc} recall={a.internal_only_recall_at_budget} highlight />
      </div>
      <p className="text-sm text-slate-700 mt-3">
        Gap to the full model: <b className="font-semibold text-ink">{aucGap >= 0 ? '+' : ''}{aucGap.toFixed(4)} AUC</b> and{' '}
        <b className="font-semibold text-ink">{pp(recGap)} recall</b> at the same budget. That gap is what the external feeds are worth.
      </p>
      <div className="mt-3">
        <div className="text-[11px] uppercase tracking-wide text-muted mb-1.5">External features removed · {a.external_features_removed.length}</div>
        <div className="flex flex-wrap gap-1.5">
          {a.external_features_removed.map((f) => (
            <span key={f} className="text-[11px] font-mono px-2 py-1 rounded-md border text-slate-600"
              style={{ borderColor: `${RAG.amber}66`, background: `${RAG.amber}14` }}>
              {f}
            </span>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-muted mt-3 leading-snug">{a.note}</p>
    </Card>
  )
}

function AblationTile({
  title, sub, auc, recall, highlight = false,
}: { title: string; sub: string; auc: number; recall: number; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border p-4 ${highlight ? 'border-teal/40 bg-teal/[0.04]' : 'border-line bg-paper'}`}>
      <div className="text-[11px] uppercase tracking-wide text-muted">{title}</div>
      <div className="text-[11px] text-muted">{sub}</div>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="text-xs text-muted">AUC</span>
        <span className="text-2xl font-bold text-ink">{auc.toFixed(4)}</span>
      </div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs text-muted">Recall at budget</span>
        <span className="text-lg font-bold" style={{ color: RAG.green }}>{pct(recall)}</span>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ challengers: one model per loan type
/** Green when the global model holds, amber when a dedicated model wins, grey when there were too few defaults to tell. */
function verdictColor(verdict: string): string {
  const s = verdict.toLowerCase()
  if (s.includes('not better')) return RAG.green
  if (s.includes('better')) return RAG.amber
  return '#5B6B85'
}

function SegmentModelsPanel({ rows }: { rows: SegmentModelRow[] }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="A dedicated XGBoost challenger per loan type, trained on fold A and scored on fold C, against the one global model with per-loan-type calibration.">
        One model or one per loan type?
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
              <th className="py-2 pr-3 font-medium">Loan type</th>
              <th className="py-2 px-3 font-medium text-right">Train rows</th>
              <th className="py-2 px-3 font-medium text-right">Validation rows</th>
              <th className="py-2 px-3 font-medium text-right">Defaults in fold</th>
              <th className="py-2 px-3 font-medium text-right">Global model AUC</th>
              <th className="py-2 px-3 font-medium text-right">Dedicated model AUC</th>
              <th className="py-2 pl-3 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const c = verdictColor(r.verdict)
              return (
                <tr key={r.loan_type} className="border-b border-line last:border-0">
                  <td className="py-2.5 pr-3 font-medium text-ink">{r.loan_type}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{num(r.n_train)}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{num(r.n_valid)}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{r.defaults_valid != null ? num(r.defaults_valid) : '-'}</td>
                  <td className="py-2.5 px-3 text-right font-semibold text-ink">{r.global_model_auc != null ? r.global_model_auc.toFixed(4) : '-'}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{r.dedicated_model_auc != null ? r.dedicated_model_auc.toFixed(4) : '-'}</td>
                  <td className="py-2.5 pl-3"><Chip color={c}>{r.verdict}</Chip></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted mt-3 leading-snug">
        The clause asks for suitable methods per loan type; the answer here is one model with per-loan-type calibration, and this is the evidence.
      </p>
    </Card>
  )
}

// ------------------------------------------------------------------ 2. alert budget
function AlertBudget({ m }: { m: ModelMetrics }) {
  const curve = m.threshold_curve
  const nearestIdx = (thr: number) =>
    curve.reduce((best, p, i) => (Math.abs(p.threshold - thr) < Math.abs(curve[best].threshold - thr) ? i : best), 0)

  const [idx, setIdx] = useState(() => nearestIdx(m.operating_threshold))
  const [opKey, setOpKey] = useState<string | null>(
    () => m.operating_points.find((o) => o.threshold === m.operating_threshold)?.key ?? null,
  )

  const op = opKey ? m.operating_points.find((o) => o.key === opKey) : undefined
  const pt: ThresholdPoint = op ?? curve[Math.min(idx, curve.length - 1)]

  const chartData = useMemo(() => curve.map((p) => ({
    thr: p.threshold,
    recall: +(p.recall * 100).toFixed(1),
    precision: +(p.precision * 100).toFixed(1),
    alerts: +(p.alert_rate * 100).toFixed(1),
  })), [curve])

  if (curve.length === 0) return null

  return (
    <Card className="p-5">
      <SectionTitle sub="Every threshold on the validation fold. Slide to the alert budget your officers can review; the three named operating points were chosen on the calibration fold, never on this one.">
        Choose your alert budget
      </SectionTitle>

      <div className="flex flex-wrap gap-2 mb-4">
        {m.operating_points.map((o) => {
          const active = opKey === o.key
          return (
            <button key={o.key}
              onClick={() => { setOpKey(o.key); setIdx(nearestIdx(o.threshold)) }}
              className={`px-3.5 py-2 rounded-xl text-sm font-medium border transition-colors ${
                active ? 'bg-teal text-white border-teal' : 'bg-white text-slate-700 border-line hover:border-teal/50'
              }`}>
              {o.label}
              <span className={`ml-2 text-xs ${active ? 'text-white/80' : 'text-muted'}`}>thr {o.threshold.toFixed(3)}</span>
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
        <div className="lg:col-span-3">
          <input
            type="range" min={0} max={curve.length - 1} step={1} value={idx}
            onChange={(e) => { setIdx(Number(e.target.value)); setOpKey(null) }}
            className="w-full accent-[#0B3D91]"
            aria-label="Alert threshold"
          />
          <div className="flex justify-between text-[10px] text-muted mb-2">
            <span>more alerts · threshold {curve[0].threshold.toFixed(2)}</span>
            <span>threshold {curve[curve.length - 1].threshold.toFixed(2)} · fewer alerts</span>
          </div>
          <div style={{ width: '100%', height: 230 }}>
            <ResponsiveContainer>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F8" vertical={false} />
                <XAxis dataKey="thr" type="number" domain={['dataMin', 'dataMax']} tick={AXIS_TICK} tickLine={false}
                  axisLine={{ stroke: '#E3E8F0' }} tickFormatter={(v: any) => Number(v).toFixed(2)} />
                <YAxis domain={[0, 100]} tick={AXIS_TICK} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v: any) => `threshold ${Number(v).toFixed(3)}`}
                  formatter={(v: any, name: any) => [`${v}%`, name]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="recall" name="Recall" stroke={RAG.green} strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="precision" name="Precision" stroke="#0B3D91" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="alerts" name="Alerts (% of book)" stroke={RAG.amber} strokeWidth={1.75} strokeDasharray="5 4" dot={false} />
                <ReferenceLine x={pt.threshold} stroke={RAG.red} strokeWidth={1.5} strokeDasharray="4 3"
                  label={{ value: 'selected', position: 'top', fontSize: 10, fill: RAG.red }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="lg:col-span-2 grid grid-cols-2 gap-2 content-start">
          <MiniStat label="Threshold" value={pt.threshold.toFixed(3)} sub={op ? op.label : 'custom point'} />
          <MiniStat label="Accuracy" value={pct(pt.accuracy, 1)} sub={`balanced ${pct(pt.balanced_accuracy, 1)}`} />
          <MiniStat label="Recall" value={pct(pt.recall, 1)} accent={RAG.green} sub="defaults caught" />
          <MiniStat label="Precision" value={pct(pt.precision, 1)} sub={`F1 ${pt.f1.toFixed(3)}`} />
          <MiniStat label="Alerts" value={num(pt.alerts)} sub={`${pct(pt.alert_rate, 1)} of book for officer review`} />
          <MiniStat label="Missed defaults" value={num(pt.missed)} accent={pt.missed > 0 ? RAG.red : RAG.green}
            sub={`of ${num(pt.confusion_matrix[1][0] + pt.confusion_matrix[1][1])} in the fold`} />
        </div>
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ 3. deciles
function DecileTable({ rows }: { rows: DecileRow[] }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Validation fold ranked by PD and cut into ten equal slices. Lift is each slice's default rate against the fold's base rate.">
        Decile capture
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
              <th className="py-2 pr-2 font-medium">Decile</th>
              <th className="py-2 px-2 font-medium text-right">n</th>
              <th className="py-2 px-2 font-medium text-right">Defaults</th>
              <th className="py-2 px-2 font-medium text-right">Default rate</th>
              <th className="py-2 px-2 font-medium text-right">Lift</th>
              <th className="py-2 pl-2 font-medium">Cumulative capture</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.decile} className="border-b border-line last:border-0">
                <td className="py-1.5 pr-2">
                  <div className="font-semibold text-ink">D{r.decile}</div>
                  <div className="text-[10px] text-muted whitespace-nowrap">PD {pct(r.min_pd, 1)} to {pct(r.max_pd, 1)}</div>
                </td>
                <td className="py-1.5 px-2 text-right text-slate-600">{num(r.n)}</td>
                <td className="py-1.5 px-2 text-right font-semibold text-ink">{r.defaults}</td>
                <td className="py-1.5 px-2 text-right text-slate-600">{pct(r.default_rate, 1)}</td>
                <td className="py-1.5 px-2 text-right text-slate-600">{r.lift.toFixed(1)}x</td>
                <td className="py-1.5 pl-2 min-w-[140px]">
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 rounded-full bg-paper overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${r.cum_capture * 100}%`, background: RAG.green }} />
                    </div>
                    <span className="text-xs font-semibold text-ink w-12 text-right">{pct(r.cum_capture, 1)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ 4. lead time
function LeadTime({ rows, thr }: { rows: LeadTimeRow[]; thr: number }) {
  const data = rows.map((r) => ({
    bin: `${r.months_ahead} mo`,
    flagged: r.flagged != null ? +(r.flagged * 100).toFixed(1) : 0,
    n: r.n,
    measured: r.flagged != null,
  }))
  return (
    <Card className="p-5">
      <SectionTitle sub={`Share of eventual defaulters already flagged at the maximum-capture threshold (${thr.toFixed(3)}), by how many months before they reached 90+ DPD.`}>
        Lead time
      </SectionTitle>
      <div style={{ width: '100%', height: 220 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F8" vertical={false} />
            <XAxis dataKey="bin" tick={{ fontSize: 11, fill: '#5B6B85' }} tickLine={false} axisLine={{ stroke: '#E3E8F0' }} />
            <YAxis domain={[0, 100]} tick={AXIS_TICK} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: any) => [`${v}%`, 'Already flagged']} cursor={{ fill: 'rgba(10,31,68,0.04)' }} />
            <Bar dataKey="flagged" radius={[6, 6, 0, 0]} isAnimationActive>
              {data.map((d, i) => (
                <Cell key={i} fill={!d.measured ? '#CBD5E1' : d.flagged >= 80 ? RAG.green : d.flagged >= 50 ? RAG.amber : RAG.red} />
              ))}
              <LabelList dataKey="flagged" position="top" formatter={(v: any) => `${v}%`} style={{ fontSize: 11, fill: '#0A1F44', fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="grid gap-2 mt-1" style={{ gridTemplateColumns: `repeat(${Math.max(1, rows.length)}, minmax(0, 1fr))` }}>
        {rows.map((r) => (
          <div key={r.months_ahead} className="text-center text-[11px] text-muted">
            {r.n} defaulter{r.n === 1 ? '' : 's'}{r.flagged == null ? ' · none in fold' : ''}
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted mt-3 leading-snug">
        This is the "12 months in advance" evidence: the right-most bar is the share of eventual defaulters the model had already
        flagged 10 to 12 months before the account slipped to 90+ DPD.
      </p>
    </Card>
  )
}

// ------------------------------------------------------------------ 5. baselines
function Baselines({ rows }: { rows: BaselineRow[] }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="The rules a bank runs today, scored on the same validation fold. PRAHARI is then held to exactly the same number of alerts, so the comparison is like for like.">
        Baselines on the same fold
      </SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
              <th className="py-2 pr-3 font-medium">Method</th>
              <th className="py-2 px-3 font-medium text-right">Recall</th>
              <th className="py-2 px-3 font-medium text-right">Precision</th>
              <th className="py-2 px-3 font-medium text-right">Alerts</th>
              <th className="py-2 px-3 font-medium text-right">PRAHARI recall at same alerts</th>
              <th className="py-2 pl-3 font-medium text-right">Uplift</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const up = r.uplift_x
              const upColor = up == null ? '#5B6B85' : up >= 1.05 ? RAG.green : up <= 0.95 ? RAG.red : '#5B6B85'
              return (
                <tr key={r.name} className="border-b border-line last:border-0 align-top">
                  <td className="py-2.5 pr-3">
                    <div className="font-medium text-ink">{r.name}</div>
                    <div className="text-[11px] text-muted">{r.description}{r.auc != null ? ` · AUC ${r.auc.toFixed(3)}` : ''}</div>
                  </td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{pct(r.recall, 1)}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600">{pct(r.precision, 1)}</td>
                  <td className="py-2.5 px-3 text-right text-slate-600 whitespace-nowrap">{num(r.alerts)} <span className="text-[11px] text-muted">({pct(r.alert_rate, 1)})</span></td>
                  <td className="py-2.5 px-3 text-right font-semibold text-ink whitespace-nowrap">
                    {pct(r.prahari_recall_at_same_alerts, 1)}
                    <span className="text-[11px] text-muted font-normal ml-1">prec. {pct(r.prahari_precision_at_same_alerts, 1)}</span>
                  </td>
                  <td className="py-2.5 pl-3 text-right">
                    <span className="inline-flex px-2 py-0.5 rounded-md text-xs font-bold" style={{ color: upColor, background: `${upColor}14` }}>
                      {up != null ? `${up.toFixed(2)}x` : '-'}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted mt-3">
        Uplift is PRAHARI's recall divided by the baseline's recall at the same alert count. Below 1.0x means the rule already catches those few accounts (it fires only once arrears exist); above 1.0x is what the behavioural model adds before arrears.
      </p>
    </Card>
  )
}

// ------------------------------------------------------------------ 6. calibration
function CalibrationPanel({ c, method }: { c: Calibration; method: string }) {
  return (
    <Card className="p-5">
      <SectionTitle sub={`Predicted versus observed default rate by PD band, so a 10 percent PD means the same thing on every facility · ${method}`}>
        Calibration
      </SectionTitle>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <MiniStat label="Brier score" value={c.brier.toFixed(4)} sub="mean squared error of PD" />
        <MiniStat label="Expected calibration error" value={c.expected_calibration_error.toFixed(4)} sub="n-weighted gap across bands" />
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
            <th className="py-2 pr-2 font-medium">PD band</th>
            <th className="py-2 px-2 font-medium text-right">n</th>
            <th className="py-2 px-2 font-medium text-right">Mean predicted</th>
            <th className="py-2 px-2 font-medium text-right">Observed</th>
            <th className="py-2 pl-2 font-medium text-right">Gap</th>
          </tr>
        </thead>
        <tbody>
          {c.bins.map((b) => {
            const gap = b.observed - b.mean_predicted
            return (
              <tr key={b.bin} className="border-b border-line last:border-0">
                <td className="py-1.5 pr-2 font-mono text-xs text-ink">{b.bin}</td>
                <td className="py-1.5 px-2 text-right text-slate-600">{num(b.n)}</td>
                <td className="py-1.5 px-2 text-right text-slate-600">{pct(b.mean_predicted, 1)}</td>
                <td className="py-1.5 px-2 text-right font-semibold text-ink">{pct(b.observed, 1)}</td>
                <td className="py-1.5 pl-2 text-right text-xs" style={{ color: Math.abs(gap) > 0.05 ? RAG.amber : '#5B6B85' }}>
                  {gap > 0 ? '+' : ''}{(gap * 100).toFixed(1)} pp
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Card>
  )
}

// ------------------------------------------------------------------ 7. segments
const SEGMENT_GROUPS: { key: string; label: string }[] = [
  { key: 'loan_type', label: 'Loan type' },
  { key: 'sector', label: 'Sector' },
  { key: 'vintage', label: 'Vintage' },
  { key: 'as_of_month', label: 'As-of month' },
]

function sortSegment(key: string, rows: SegmentRow[]): SegmentRow[] {
  if (key === 'vintage' || key === 'as_of_month') {
    return [...rows].sort((a, b) => parseInt(a.value, 10) - parseInt(b.value, 10))
  }
  return rows
}

function Segments({ rows }: { rows: SegmentRow[] }) {
  const groups = useMemo(() => {
    const known = SEGMENT_GROUPS.map((g) => g.key)
    const extra = Array.from(new Set(rows.map((r) => r.segment))).filter((k) => !known.includes(k)).map((k) => ({ key: k, label: k.replace('_', ' ') }))
    return [...SEGMENT_GROUPS, ...extra]
      .map((g) => ({ ...g, rows: sortSegment(g.key, rows.filter((r) => r.segment === g.key)) }))
      .filter((g) => g.rows.length > 0)
  }, [rows])

  return (
    <Card className="p-5">
      <SectionTitle sub="Does the model hold across loan types, sectors, vintages and as-of months? AUC per segment and recall at the operating threshold.">
        Performance by segment
      </SectionTitle>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {groups.map((g) => (
          <div key={g.key}>
            <div className="text-[11px] uppercase tracking-wide text-muted font-medium mb-1">{g.label}</div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-muted border-b border-line">
                  <th className="py-1 pr-2 font-medium">Segment</th>
                  <th className="py-1 px-2 font-medium text-right">n</th>
                  <th className="py-1 px-2 font-medium text-right">Defaults</th>
                  <th className="py-1 px-2 font-medium text-right">AUC</th>
                  <th className="py-1 pl-2 font-medium text-right">Recall</th>
                </tr>
              </thead>
              <tbody>
                {g.rows.map((r) => (
                  <tr key={r.value} className="border-b border-line last:border-0">
                    <td className="py-1 pr-2 text-ink font-medium capitalize">{r.value.replace('_', ' ')}</td>
                    <td className="py-1 px-2 text-right text-slate-600">{num(r.n)}</td>
                    <td className="py-1 px-2 text-right text-slate-600">{r.defaults}</td>
                    <td className="py-1 px-2 text-right text-slate-600">{r.auc != null ? r.auc.toFixed(3) : '-'}</td>
                    <td className="py-1 pl-2 text-right font-semibold" style={{ color: r.recall == null ? '#5B6B85' : r.recall >= 0.8 ? RAG.green : r.recall >= 0.6 ? RAG.amber : RAG.red }}>
                      {r.recall != null ? pct(r.recall, 0) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted mt-3">AUC is blank where a segment has no defaults (or no survivors) in the fold.</p>
    </Card>
  )
}

// ------------------------------------------------------------------ 8. validation design
function ValidationDesign({ m }: { m: ModelMetrics }) {
  const psi = m.psi_between_as_ofs
  const psiNote = psi < 0.1 ? 'stable (below 0.10)' : psi < 0.25 ? 'moderate shift' : 'material shift'
  return (
    <Card className="p-5">
      <SectionTitle sub="Borrower-disjoint and temporal. Nothing is tuned on the fold that is reported.">Validation design</SectionTitle>
      <p className="text-sm text-slate-700 leading-relaxed">{m.validation}</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
        <MiniStat label="Train rows" value={num(m.n_train)} sub={`${num(m.n_borrowers_train)} borrowers · fold A`} />
        <MiniStat label="Calibration rows" value={num(m.n_calibration)} sub="fold B · thresholds chosen here" />
        <MiniStat label="Validation rows" value={num(m.n_valid)} sub={`${num(m.n_borrowers_valid)} borrowers · fold C`} />
        <MiniStat label="PSI between as-ofs" value={psi.toFixed(4)} sub={psiNote} />
        <MiniStat label="Default rate" value={`${pct(m.train_positive_rate, 1)} / ${pct(m.valid_positive_rate, 1)}`} sub="train / validation" size="sm" />
        <MiniStat label="Calibration method" value={m.calibration_method} size="sm" />
      </div>
    </Card>
  )
}

// ------------------------------------------------------------------ 9. confusion matrix
function ConfusionPanel({ m }: { m: ModelMetrics }) {
  const [[tn, fp], [fn, tp]] = m.confusion_matrix
  return (
    <Card className="p-5">
      <SectionTitle sub={`Validation fold: ${num(m.n_valid)} account-months · operating threshold ${m.operating_threshold.toFixed(3)}`}>
        Confusion matrix
      </SectionTitle>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-2 text-sm">
        <div />
        <div className="text-center text-[11px] font-medium text-muted pb-1">Pred. no default</div>
        <div className="text-center text-[11px] font-medium text-muted pb-1">Pred. default</div>

        <div className="flex items-center text-[11px] font-medium text-muted pr-1">Actual<br />no default</div>
        <MatrixCell value={tn} label="True negative" good />
        <MatrixCell value={fp} label="False positive" />

        <div className="flex items-center text-[11px] font-medium text-muted pr-1">Actual<br />default</div>
        <MatrixCell value={fn} label="False negative (missed)" bad />
        <MatrixCell value={tp} label="True positive (caught)" good />
      </div>
      <div className="grid grid-cols-3 gap-3 mt-4">
        <MiniStat label="F1" value={m.f1.toFixed(3)} />
        <MiniStat label="Horizon" value={`${m.horizon_months} mo`} />
        <MiniStat label="Base rate" value={pct(m.valid_positive_rate, 1)} />
      </div>
    </Card>
  )
}

function MatrixCell({ value, label, good, bad }: { value: number; label: string; good?: boolean; bad?: boolean }) {
  const color = good ? RAG.green : bad ? RAG.red : '#5B6B85'
  const bg = good ? 'rgba(46,158,91,0.08)' : bad ? 'rgba(229,72,77,0.08)' : '#F7F9FC'
  return (
    <div className="rounded-xl border border-line p-3 text-center" style={{ background: bg }}>
      <div className="text-2xl font-bold" style={{ color }}>{num(value)}</div>
      <div className="text-[11px] text-muted mt-0.5">{label}</div>
    </div>
  )
}

// ------------------------------------------------------------------ runway model
function RunwayModelPanel({ r }: { r: RunwayCard }) {
  const m = r.metrics
  const f = (v: number | null | undefined, digits = 3) => (v == null ? '-' : v.toFixed(digits))
  return (
    <Card className="p-5">
      <SectionTitle sub={r.method}>Runway model (months to 90+ DPD)</SectionTitle>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <MiniStat label="Concordance" value={f(m.concordance_defaulters_fold_C)} sub="rank agreement on defaulters, fold C" />
        <MiniStat label="Median abs error"
          value={m.median_abs_error_months_defaulters == null ? '-' : `${m.median_abs_error_months_defaulters.toFixed(1)} mo`}
          sub="predicted vs observed, defaulters" />
        <MiniStat label="12-month hazard AUC" value={f(m.hazard_model_12m_auc)} sub={`Brier ${f(m.hazard_model_12m_brier, 4)}`} />
        <MiniStat label="Agreement with PD model" value={f(m.agreement_with_pd_model_corr)} sub="correlation of 12-month risk" />
        <MiniStat label="Validation rows" value={num(m.n_valid)} sub={`${num(m.n_defaulters_valid)} defaulters · fold C`} />
        <MiniStat label="Train person-periods" value={num(m.n_person_periods_train)} sub={`horizon ${m.horizon_months} mo · cap ${m.max_runway} mo`} />
      </div>
      {r.calibration.length > 0 && (
        <div className="overflow-x-auto mt-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                <th className="py-2 pr-2 font-medium">Calibrated PD band</th>
                <th className="py-2 px-2 font-medium text-right">n</th>
                <th className="py-2 px-2 font-medium text-right">Defaults</th>
                <th className="py-2 px-2 font-medium text-right">Predicted median runway</th>
                <th className="py-2 pl-2 font-medium text-right">Observed median (Kaplan-Meier)</th>
              </tr>
            </thead>
            <tbody>
              {r.calibration.map((c) => {
                const gap = c.predicted_median_months - c.observed_km_median_months
                return (
                  <tr key={c.band} className="border-b border-line last:border-0">
                    <td className="py-1.5 pr-2 font-mono text-xs text-ink">{c.band}</td>
                    <td className="py-1.5 px-2 text-right text-slate-600">{num(c.n)}</td>
                    <td className="py-1.5 px-2 text-right text-slate-600">{c.events}</td>
                    <td className="py-1.5 px-2 text-right font-semibold text-ink">{c.predicted_median_months.toFixed(1)} mo</td>
                    <td className="py-1.5 pl-2 text-right text-slate-600">
                      {c.observed_km_median_months.toFixed(1)} mo
                      <span className="text-[11px] ml-1" style={{ color: Math.abs(gap) > 3 ? RAG.amber : '#5B6B85' }}>
                        ({gap > 0 ? '+' : ''}{gap.toFixed(1)})
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="text-[11px] text-muted mt-2">Observed medians are Kaplan-Meier estimates on the validation fold, censored at {m.max_runway} months; the gap is predicted minus observed.</p>
        </div>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------ cost of error
function CostOfErrorPanel({ c }: { c: CostOfError }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Why modest precision with high recall is the correct, honest operating point - priced in rupees.">
        Cost of error (in rupees)
      </SectionTitle>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Headline */}
        <div className="rounded-xl bg-rag-green/5 border border-rag-green/20 p-5 flex flex-col justify-center text-center">
          <div className="text-[11px] uppercase tracking-wide text-muted">Provisioning preserved</div>
          <div className="text-3xl font-bold text-rag-green mt-1">
            <CountUpCr value={c.provision_preserved} />
          </div>
          <div className="text-[11px] text-muted mt-1.5">
            {inr(c.provision_at_risk_without_ews)} at risk without EWS · {inr(c.residual_cost_with_ews)} residual with it
          </div>
        </div>

        {/* Asymmetry + error economics table */}
        <div className="lg:col-span-2">
          <div className="rounded-xl bg-rag-red/[0.04] border border-rag-red/20 p-3.5 mb-3 text-sm text-slate-700">
            A missed default costs <b style={{ color: RAG.red }}>~{c.asymmetry_ratio}×</b> a false alarm - so the
            model is tuned to catch stress (<b>{c.caught}</b> of <b>{c.defaults_in_validation}</b> defaults), accepting
            more alerts for officer review.
          </div>
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-sm">
              <tbody>
                <tr className="border-b border-line">
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: RAG.red }} />
                      <span className="font-medium text-ink">Missed default</span>
                    </div>
                    <div className="text-[11px] text-muted mt-0.5 ml-4">provision jumps 0.4% → 15% · {c.missed} in validation</div>
                  </td>
                  <td className="py-3 px-4 text-right font-bold" style={{ color: RAG.red }}>{inr(c.cost_per_missed_default)}</td>
                </tr>
                <tr>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full" style={{ background: RAG.amber }} />
                      <span className="font-medium text-ink">False alarm</span>
                    </div>
                    <div className="text-[11px] text-muted mt-0.5 ml-4">one officer review · {c.false_alarms} in validation</div>
                  </td>
                  <td className="py-3 px-4 text-right font-bold" style={{ color: RAG.amber }}>{inr(c.cost_per_false_alarm)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <p className="text-[11px] text-muted italic mt-4">{c.note}</p>
    </Card>
  )
}

// ------------------------------------------------------------------ features by pillar
function Features({ card }: { card: Card_ }) {
  const inModel = new Set(card.features)
  const assigned = new Set(Object.values(card.pillars).flat())
  const groups: [string, string[]][] = Object.entries(card.pillars)
    .map(([k, v]) => [k, v.filter((f) => inModel.has(f))] as [string, string[]])
    .filter(([, v]) => v.length > 0)
  const other = card.features.filter((f) => !assigned.has(f))
  if (other.length) groups.push(['Other', other])
  return (
    <Card className="p-5">
      <SectionTitle sub={`${card.features.length} point-in-time behavioural features grouped by pillar - no feature uses data after the as-of month (leakage-tested).`}>
        Model features
      </SectionTitle>
      <div className="space-y-4">
        {groups.map(([pillar, feats]) => (
          <div key={pillar}>
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xs font-semibold text-ink">{pillar}</span>
              <span className="text-[11px] text-muted">{feats.length}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {feats.map((f) => (
                <span key={f} className="text-[11px] font-mono px-2 py-1 rounded-md bg-paper border border-line text-slate-600">{f}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
