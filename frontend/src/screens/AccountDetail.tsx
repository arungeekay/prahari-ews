import { useEffect, useMemo, useState } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine,
} from 'recharts'
import { motion } from 'framer-motion'
import { api } from '../api'
import type {
  AccountDetail as Detail, WhatIf, ReasonCode, Beat, ComplianceClock, DocResp, Bucket,
  Pillar, OfficerNote, NoteScore, ContagionNodeResult, RecommendedAction,
  EwsIndicator, ReviewState, ReviewStatus, ReviewAction, ReviewRecord,
  PdHistory, Coverage, Confidence,
} from '../types'
import { useNav } from '../nav'
import { useFramework, thresholdsOf } from '../framework'
import {
  Card, SectionTitle, RagChip, Spinner, ErrorBox, RAG, RAG_TINT, GradeBadge, Chip, SentimentChip, PdDelta,
  smaColor, sentimentColor,
} from '../components/ui'
import { Gauge } from '../components/Gauge'
import { RunwayDial } from '../components/RunwayDial'
import { DocumentModal } from '../components/DocumentModal'
import { inr, pct, pp, monthLabel, ymLabel, shiftYm, timestamp } from '../format'
import { useTween } from '../components/anim'

const ACTION_LABEL: Record<string, string> = {
  enhanced_monitoring: 'Enhanced monitoring',
  restructure: 'Restructure',
  limit_reduction: 'Limit reduction',
  collateral_topup: 'Collateral top-up',
}

const SMA_CAPTION =
  'Statutory SMA is defined by RBI on days past due (SMA-0: 1-30, SMA-1: 31-60, SMA-2: 61-90). ' +
  'The model flag is a behavioural early-warning equivalent shown beside it; it never replaces the statutory status.'

/** Pillar score colour: 70 and above green, 40 to 69 amber, below 40 red. */
function pillarColor(score: number): string {
  if (score >= 70) return RAG.green
  if (score >= 40) return RAG.amber
  return RAG.red
}

interface DocState {
  open: boolean
  title: string
  subtitle?: string
  text: string | null
  loading: boolean
  provider?: string
  /** Backend document_type of the drafted document; becomes the review record's document_type on filing. */
  documentType?: string
  filing?: boolean
  filedBy?: string | null
  fileError?: string | null
}

/** The reviewer's name is remembered per browser so the officer types it once. Storage may be unavailable. */
const REVIEWER_KEY = 'prahari.reviewer'
function loadReviewer(): string {
  try { return window.localStorage.getItem(REVIEWER_KEY) ?? '' } catch { return '' }
}
function saveReviewer(name: string): void {
  try { window.localStorage.setItem(REVIEWER_KEY, name) } catch { /* storage unavailable: keep in memory only */ }
}

const NPA_COLOR = '#A8262B'

export function AccountDetail({ id }: { id: string }) {
  const { go } = useNav()
  const fw = useFramework()
  const [d, setD] = useState<Detail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sim, setSim] = useState<WhatIf | null>(null)
  const [simLoading, setSimLoading] = useState<string | null>(null)
  const [doc, setDoc] = useState<DocState>({ open: false, title: '', text: null, loading: false })
  const [reviewer, setReviewerState] = useState<string>(() => loadReviewer())
  const setReviewer = (name: string) => { setReviewerState(name); saveReviewer(name) }

  useEffect(() => {
    setD(null); setErr(null); setSim(null)
    api.account(id).then(setD).catch((e) => setErr(String(e)))
  }, [id])

  if (err) return <ErrorBox message={err} />
  if (!d) return <Spinner label="Loading account…" />

  const runwayShown = sim ? sim.runway_after : d.runway_months
  const pdC = fw.pdColor(d.pd, d.loan_type)
  const smaCaption = fw.framework?.model_implied_sma?.note ?? SMA_CAPTION

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
      filing: false, filedBy: null, fileError: null,
    })
    try {
      const r: DocResp = kind === 'memo' ? await api.memo(id) : await api.crilc(id)
      setDoc((p) => ({
        ...p, loading: false, text: r.text, title: r.document_type, documentType: r.document_type, provider: r.llm_provider,
      }))
    } catch (e) {
      setDoc((p) => ({ ...p, loading: false, text: `Failed to generate document: ${e}` }))
    }
  }

  /** Maker-checker: record a named officer's decision and refresh this account's review state. */
  const submitReview = async (action: ReviewAction, note: string, documentType = ''): Promise<ReviewRecord> => {
    const r = await api.review(id, { action, reviewer: reviewer.trim() || 'officer', note, document_type: documentType })
    setD((prev) => (prev ? { ...prev, review: r.state } : prev))
    return r.record
  }

  /** "Approve and file" from the document modal: action "file" with the document's title as document_type. */
  const fileFromModal = async () => {
    setDoc((p) => ({ ...p, filing: true, fileError: null }))
    try {
      const rec = await submitReview('file', `Approved and filed from the drafted ${doc.title}.`, doc.documentType || doc.title)
      setDoc((p) => ({ ...p, filing: false, filedBy: rec.reviewer }))
    } catch (e) {
      setDoc((p) => ({ ...p, filing: false, fileError: String(e) }))
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
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-2xl font-bold text-ink tracking-tight">{d.name}</h2>
            <RagChip bucket={d.bucket} />
            {d.is_npa && (
              <Chip color="#A8262B" title="Already 90+ days past due: a classification fact, not a prediction">
                NPA · {d.dpd} DPD
              </Chip>
            )}
            {d.borrower_id === 'MSME00001' && (
              <span className="text-[11px] font-semibold text-teal border border-teal/30 bg-teal/5 rounded-full px-2.5 py-1">
                Demo character
              </span>
            )}
          </div>
          <p className="text-muted text-sm mt-1">
            {d.borrower_id} · <span className="capitalize">{d.sector.replace('_', ' ')}</span> · {d.city}, {d.state} · {d.loan_type} facility · {d.vintage_years} yrs on books
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

      {/* Grade + statutory vs model-implied SMA */}
      <Card className="px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <GradeBadge grade={d.grade} label={d.grade_label} score={d.grade_score} />
          {d.coverage && <CoverageChip coverage={d.coverage} />}
          <div className="hidden md:block h-8 w-px bg-line" />
          <Chip color={smaColor(d.statutory_sma)} title="Computed from actual days past due">
            Statutory: {d.statutory_sma} ({d.dpd} DPD)
          </Chip>
          <Chip color={RAG[d.bucket]} bg={RAG_TINT[d.bucket]} title="Behavioural early-warning equivalent from the model">
            Model-implied: {d.model_implied_sma}
          </Chip>
          <span className="text-xs text-muted ml-auto">Repayment: <b className="font-semibold text-slate-600">{d.repayment_state}</b></span>
        </div>
        <p className="text-[11px] text-muted mt-2 leading-snug">{smaCaption}</p>
        {d.coverage && d.coverage.confidence === 'low' && d.coverage.note && (
          <p className="text-[11px] mt-1 leading-snug font-medium" style={{ color: RAG.red }}>{d.coverage.note}</p>
        )}
      </Card>

      {d.is_npa && <NpaBanner dpd={d.dpd} statutory={d.statutory_sma} />}

      {/* Top row: runway dial + PD gauge + stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="p-5 flex flex-col items-center justify-center">
          <SectionTitle sub="Projected months to 90+ DPD on current trajectory.">Runway clock</SectionTitle>
          <RunwayDial runway={runwayShown} />
          {sim && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-2 text-center">
              <div className="text-sm font-semibold" style={{ color: sim.runway_delta >= 0 ? RAG.green : RAG.red }}>
                {sim.runway_delta >= 0 ? '+' : ''}{sim.runway_delta.toFixed(1)} months from “{ACTION_LABEL[sim.action] ?? sim.action}”
              </div>
              <div className="text-[11px] text-muted mt-0.5">
                Sensitivity: {sim.runway_after_range[0].toFixed(1)} to {sim.runway_after_range[1].toFixed(1)} months
              </div>
            </motion.div>
          )}
          {!sim && <SurvivalSparkline curve={d.survival_curve} />}
        </Card>

        <Card className="p-5 flex flex-col items-center justify-center">
          <SectionTitle sub="Calibrated probability of default within 12 months.">Probability of default</SectionTitle>
          <Gauge fraction={d.pd} color={pdC} size={200} thickness={18}>
            <div className="text-4xl font-bold" style={{ color: pdC }}>{pct(d.pd, 0)}</div>
            <div className="text-xs text-muted mt-1 font-medium tracking-wide">12-MONTH PD</div>
          </Gauge>
          <div className="mt-2 flex items-center gap-2 text-xs text-muted">
            <span>Last month {pct(d.pd_prev)}</span>
            <PdDelta delta={d.pd_delta} />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle>Exposure snapshot</SectionTitle>
          <Stat label="Exposure at risk" value={inr(d.exposure)} big />
          <Stat label="Sanctioned limit" value={inr(d.sanctioned_limit)} />
          <Stat label="Limit utilisation" value={pct(d.utilisation)} />
          {d.drawing_power_pct > 0 && <Stat label="Drawing power (of sanction)" value={pct(d.drawing_power_pct)} />}
          <Stat label="Runway (model)" value={`${d.runway_label} months`} />
          <Stat label="Promoter" value={`${d.promoter_experience_years} yrs experience · ${d.promoter_qualification}`} />
        </Card>
      </div>

      {/* PD history: when PRAHARI flagged versus when arrears appeared */}
      <PdHistoryChart id={id} loanType={d.loan_type} />

      {/* Recommended action + risk pillars */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <RecommendedActionCard action={d.recommended_action} bucket={d.bucket} />
        <div className="lg:col-span-2">
          <PillarStrip pillars={d.pillars} />
        </div>
      </div>

      {/* RBI EWS indicators + maker-checker review */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <EwsPanel indicators={d.ews_indicators} />
        </div>
        <ReviewCard review={d.review} reviewer={reviewer} onReviewer={setReviewer}
          onSubmit={(action, note) => submitReview(action, note)} />
      </div>

      {/* What-if simulator: hidden once an account is NPA, there is no runway left to extend */}
      {!d.is_npa && (
        <Card className="p-5">
          <SectionTitle sub="Simulate a supervisory action; the runway clock and provisioning update live. Runway gains are supervisory assumptions shown with their sensitivity range, not model outputs.">
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
              <Delta label="Runway" before={`${sim.runway_before.toFixed(1)} mo`} after={`${sim.runway_after.toFixed(1)} mo`}
                good={sim.runway_after >= sim.runway_before}
                sub={`Sensitivity range: ${sim.runway_after_range[0].toFixed(1)} to ${sim.runway_after_range[1].toFixed(1)} months`} />
              <Delta label="Provisioning" before={inr(sim.provision_before)} after={inr(sim.provision_after)}
                good={sim.provision_after <= sim.provision_before}
                sub={sim.exposure_after !== sim.exposure_before ? `Exposure ${inr(sim.exposure_before)} → ${inr(sim.exposure_after)}` : undefined} />
              <div className="rounded-xl bg-rag-green/5 border border-rag-green/20 p-3">
                <div className="text-[11px] uppercase tracking-wide text-muted">Saved vs. acting at NPA</div>
                <div className="text-xl font-bold text-rag-green mt-0.5">{inr(sim.provision_saved_vs_npa)}</div>
              </div>
              <div className="md:col-span-3 text-sm text-slate-600 bg-paper rounded-xl p-3 border border-line">
                <p>{sim.note}</p>
                <p className="text-[11px] text-muted italic mt-1.5">{sim.basis}</p>
              </div>
            </motion.div>
          ) : (
            <p className="text-sm text-muted">Select an action to preview its effect on runway and provisioning.</p>
          )}
        </Card>
      )}

      {/* Storyline + reason codes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Storyline storyline={d.storyline} beats={d.beats} from={d.from_bucket} to={d.bucket} />
        <ReasonCodes reasons={d.reason_codes} />
      </div>

      {/* Officer notes (unstructured) + live observation scoring */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <OfficerNotes notes={d.notes} />
        <AddObservation id={id} />
      </div>

      {/* Series chart + compliance clocks (+ contagion for anchor suppliers) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SeriesChart d={d} />
        </div>
        <div className="space-y-6">
          {d.contagion && <ContagionBlock c={d.contagion} />}
          <ComplianceClocks clocks={d.compliance_clocks} />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted pt-1">
        <span className="inline-flex items-center gap-2">
          Reason codes via <Chip dot={false} className="!py-0.5">{d.explainer_backend}</Chip> explainer
        </span>
        {fw.framework && <span>Interpretation framework {fw.framework.version}</span>}
      </div>

      <DocumentModal
        open={doc.open} title={doc.title} subtitle={doc.subtitle} text={doc.text} loading={doc.loading}
        footnote={doc.provider ? `Drafted via ${doc.provider}` : undefined}
        onFile={fileFromModal} filing={doc.filing} filedBy={doc.filedBy} fileError={doc.fileError}
        onClose={() => setDoc((p) => ({ ...p, open: false }))}
      />
    </div>
  )
}

function NpaBanner({ dpd, statutory }: { dpd: number; statutory: string }) {
  return (
    <div className="rounded-2xl border p-5 shadow-soft" style={{ borderColor: `${NPA_COLOR}66`, background: 'rgba(168,38,43,0.07)' }}>
      <div className="flex items-start gap-3">
        <span className="mt-1.5 w-2.5 h-2.5 rounded-full shrink-0" style={{ background: NPA_COLOR }} />
        <div>
          <div className="text-[11px] uppercase tracking-wide font-semibold" style={{ color: NPA_COLOR }}>
            Statutory {statutory} · {dpd} days past due
          </div>
          <div className="text-lg font-bold text-ink mt-0.5">
            Already NPA: this account is a classification fact, not a prediction target
          </div>
          <p className="text-sm text-slate-700 mt-1 leading-relaxed">
            It is counted in the NPA figures outside the prediction book. The what-if simulator is not shown because there is no runway left to extend; recovery and provisioning are handled under IRAC norms.
          </p>
        </div>
      </div>
    </div>
  )
}

/** The EWS source line is the same for every account; fetch it once per session. */
let ewsSourceCache: string | null = null

function EwsPanel({ indicators }: { indicators: EwsIndicator[] }) {
  const [source, setSource] = useState<string | null>(ewsSourceCache)
  const [showAll, setShowAll] = useState(false)

  useEffect(() => {
    if (ewsSourceCache) return
    api.ewsIndicators().then((r) => { ewsSourceCache = r.source; setSource(r.source) }).catch(() => setSource(null))
  }, [])

  const hit = indicators.filter((i) => i.triggered)
  const rest = indicators.filter((i) => !i.triggered)
  const tone = hit.length === 0 ? RAG.green : hit.length >= 4 ? RAG.red : RAG.amber
  return (
    <Card className="p-5 h-full">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub="Which RBI early-warning indicator families this account has tripped, with the values that evidence each one.">
          RBI EWS indicators
        </SectionTitle>
        <Chip color={tone}>{hit.length} of {indicators.length} indicator families triggered</Chip>
      </div>
      {hit.length === 0 ? (
        <p className="text-sm text-muted">No indicator family is triggered on this account.</p>
      ) : (
        <ul className="space-y-2">
          {hit.map((i) => (
            <li key={i.id} className="flex items-start gap-3 rounded-xl border border-line bg-paper/60 p-3">
              <span className="shrink-0 text-[11px] font-bold font-mono px-2 py-0.5 rounded-md"
                style={{ color: RAG.red, background: `${RAG.red}14` }} title={i.features.join(', ')}>
                {i.id}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink">{i.indicator}</div>
                {i.evidence && <div className="text-xs text-muted mt-0.5">{i.evidence}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {rest.length > 0 && (
        <div className="mt-3">
          <button onClick={() => setShowAll((v) => !v)} className="text-xs font-medium text-brand hover:underline">
            {showAll ? 'Hide' : 'Show'} the {rest.length} untriggered {rest.length === 1 ? 'family' : 'families'}
          </button>
          {showAll && (
            <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-1.5">
              {rest.map((i) => (
                <li key={i.id} className="flex items-start gap-2 text-xs text-muted">
                  <span className="shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded-md bg-paper border border-line" title={i.features.join(', ')}>
                    {i.id}
                  </span>
                  <span>{i.indicator}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {source && <p className="text-[11px] text-muted mt-3 leading-snug">{source}</p>}
    </Card>
  )
}

const REVIEW_STATUS_COLOR: Record<ReviewStatus, string> = {
  unreviewed: '#5B6B85', approved: RAG.green, returned: RAG.amber, cleared: '#0E7C7B', filed: '#0B3D91',
}

const REVIEW_ACTIONS: { action: ReviewAction; label: string; hint: string; color: string }[] = [
  { action: 'approve', label: 'Approve', hint: 'Agree with the flag; accept the drafted memo for filing', color: RAG.green },
  { action: 'return', label: 'Return', hint: 'Send back for more evidence, with a note', color: RAG.amber },
  { action: 'clear', label: 'Clear (cooling period)', hint: 'No action needed; suppressed from movers and the watch-list for the cooling period', color: '#0E7C7B' },
  { action: 'file', label: 'File', hint: 'Record to the credit file (audit trail)', color: '#0B3D91' },
]

function ReviewStatusChip({ review }: { review: ReviewState }) {
  const c = REVIEW_STATUS_COLOR[review.status] ?? '#5B6B85'
  return (
    <span className="inline-flex items-center gap-1.5">
      <Chip color={c} className="capitalize">{review.status}</Chip>
      {review.suppressed && <Chip color="#0E7C7B" dot={false} title="Cleared by an officer; suppressed from movers and the watch-list until the cooling period ends">cooling period</Chip>}
    </span>
  )
}

function ReviewCard({
  review, reviewer, onReviewer, onSubmit,
}: {
  review: ReviewState
  reviewer: string
  onReviewer: (name: string) => void
  onSubmit: (action: ReviewAction, note: string) => Promise<ReviewRecord>
}) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<ReviewAction | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const act = async (action: ReviewAction) => {
    setBusy(action); setErr(null)
    try {
      await onSubmit(action, note.trim())
      setNote('')
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(null)
    }
  }

  const last = review.last
  return (
    <Card className="p-5 h-full flex flex-col">
      <div className="flex items-start justify-between gap-2 flex-wrap">
        <SectionTitle sub="Maker-checker: a named officer decides; every decision is logged.">Review</SectionTitle>
        <ReviewStatusChip review={review} />
      </div>
      {last ? (
        <div className="rounded-xl bg-paper/60 border border-line p-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink capitalize">{last.action}</span>
            <span className="text-[11px] text-muted">{timestamp(last.timestamp)}</span>
          </div>
          <div className="text-xs text-muted mt-0.5">
            by {last.reviewer}{last.document_type ? ` · ${last.document_type}` : ''}{review.n_reviews ? ` · ${review.n_reviews} decision${review.n_reviews === 1 ? '' : 's'} on file` : ''}
          </div>
          {last.note && <p className="text-sm text-slate-700 mt-1.5 leading-relaxed">{last.note}</p>}
        </div>
      ) : (
        <p className="text-sm text-muted">No officer decision recorded yet.</p>
      )}
      <label className="block mt-3 text-[11px] uppercase tracking-wide text-muted" htmlFor="reviewer-name">Reviewer</label>
      <input
        id="reviewer-name"
        value={reviewer}
        onChange={(e) => onReviewer(e.target.value)}
        placeholder="Officer name (remembered on this device)"
        className="w-full mt-1 rounded-xl border border-line bg-paper/60 px-3 py-2 text-sm text-slate-700 placeholder:text-muted/70 focus:outline-none focus:border-teal/60 focus:bg-white"
      />
      <label className="block mt-2 text-[11px] uppercase tracking-wide text-muted" htmlFor="review-note">Note</label>
      <textarea
        id="review-note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        placeholder="Reason, evidence requested, or filing reference"
        className="w-full mt-1 rounded-xl border border-line bg-paper/60 px-3 py-2 text-sm text-slate-700 placeholder:text-muted/70 focus:outline-none focus:border-teal/60 focus:bg-white resize-y"
      />
      <div className="grid grid-cols-2 gap-2 mt-3">
        {REVIEW_ACTIONS.map((a) => (
          <button
            key={a.action}
            title={a.hint}
            disabled={busy != null}
            onClick={() => act(a.action)}
            className="px-3 py-2 rounded-xl text-xs font-semibold border transition-colors hover:bg-white disabled:opacity-50"
            style={{ color: a.color, borderColor: `${a.color}66`, background: `${a.color}0F` }}
          >
            {busy === a.action ? 'Saving…' : a.label}
          </button>
        ))}
      </div>
      {err && <div className="mt-2 text-xs text-rag-red">{err}</div>}
    </Card>
  )
}

function Stat({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-b border-line last:border-0">
      <span className="text-sm text-muted shrink-0">{label}</span>
      <span className={`font-semibold text-ink text-right ${big ? 'text-xl' : 'text-sm'}`}>{value}</span>
    </div>
  )
}

function Delta({ label, before, after, good, sub }: { label: string; before: string; after: string; good: boolean; sub?: string }) {
  return (
    <div className="rounded-xl bg-paper border border-line p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-sm text-muted line-through">{before}</span>
        <span className="text-muted">→</span>
        <span className="text-lg font-bold" style={{ color: good ? RAG.green : RAG.red }}>{after}</span>
      </div>
      {sub && <div className="text-[11px] text-muted mt-1">{sub}</div>}
    </div>
  )
}

function RecommendedActionCard({ action, bucket }: { action: RecommendedAction; bucket: Bucket }) {
  return (
    <div className="rounded-2xl border p-5 shadow-soft h-full"
      style={{ borderColor: `${RAG[bucket]}55`, background: RAG_TINT[bucket] }}>
      <div className="text-[11px] uppercase tracking-wide font-semibold" style={{ color: RAG[bucket] }}>
        Recommended action · {bucket} bucket
      </div>
      <div className="text-xl font-bold text-ink mt-1">{action.action}</div>
      <p className="text-sm text-slate-700 mt-2 leading-relaxed">{action.detail || 'No further action is prescribed by the framework for this bucket.'}</p>
      <p className="text-[11px] text-muted mt-3">Action ladder from the interpretation framework; an officer decides.</p>
    </div>
  )
}

function PillarStrip({ pillars }: { pillars: Pillar[] }) {
  return (
    <Card className="p-5 h-full">
      <SectionTitle sub="Same model, decomposed: each pillar's SHAP contribution ranked against the whole book. 100 is best; a score of 18 reads as worse than 82 percent of accounts on that pillar.">
        Risk pillars
      </SectionTitle>
      {pillars.length === 0 ? (
        <p className="text-sm text-muted">Pillar scores are not available for this account.</p>
      ) : (
        <div className="space-y-2">
          {pillars.map((p) => {
            const na = p.applicable === false
            const c = na ? '#A9B4C6' : pillarColor(p.score)
            return (
              <div key={p.pillar} title={p.description} className={`grid grid-cols-[130px_1fr_40px] items-center gap-3 ${na ? 'opacity-70' : ''}`}>
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-ink truncate">{p.pillar}</div>
                  <div className="text-[10px] text-muted truncate">{p.description}</div>
                </div>
                <div className="h-2.5 rounded-full bg-paper border border-line overflow-hidden">
                  {na ? (
                    <div className="h-full w-full" style={{ background: 'repeating-linear-gradient(135deg, #E3E8F0 0 4px, transparent 4px 8px)' }} />
                  ) : (
                    <div className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${Math.max(2, Math.min(100, p.score))}%`, background: c }} />
                  )}
                </div>
                <div className="text-sm font-bold text-right" style={{ color: c }}>{na ? 'n/a' : p.score}</div>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

/** S(t) for months 1..24 from the discrete-time hazard model; runway is where it crosses one half. */
function SurvivalSparkline({ curve }: { curve: number[] }) {
  if (!Array.isArray(curve) || curve.length === 0) return null
  const data = curve.map((s, i) => ({ m: i + 1, s: +(s * 100).toFixed(1) }))
  return (
    <div className="w-full mt-3">
      <div style={{ width: '100%', height: 72 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="survGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0B3D91" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#0B3D91" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="m" hide />
            <YAxis domain={[0, 100]} hide />
            <ReferenceLine y={50} stroke={RAG.red} strokeDasharray="3 3" strokeWidth={1} />
            <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #E3E8F0', fontSize: 12 }}
              formatter={(v: any) => [`${v}%`, 'Still standard']} labelFormatter={(m: any) => `Month ${m}`} />
            <Area type="monotone" dataKey="s" stroke="#0B3D91" strokeWidth={1.5} fill="url(#survGrad)" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="text-[10px] text-muted text-center mt-0.5">
        Survival curve over {curve.length} months; the runway is where it falls to one half
      </div>
    </div>
  )
}

function Storyline({ storyline, beats, from, to }: { storyline: string; beats: Beat[]; from: Bucket; to: Bucket }) {
  // Drop the trailing disclaimer + "Key beats" block from the prose (beats are shown as a timeline).
  const prose = storyline.split('Key beats:')[0].split('- Draft prepared')[0].trim()
  const tail = storyline.includes('- Draft prepared') ? '- Draft prepared' + storyline.split('- Draft prepared')[1] : ''
  return (
    <Card className="p-5">
      <SectionTitle sub={`How the account drifted from ${from} to ${to}.`}>Deterioration storyline</SectionTitle>
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

function ThemeTag({ theme }: { theme: string }) {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-paper border border-line text-muted capitalize">
      {theme.replace('_', ' ')}
    </span>
  )
}

function OfficerNotes({ notes }: { notes: OfficerNote[] }) {
  const sorted = [...notes].sort((a, b) => b.month_index - a.month_index)
  return (
    <Card className="p-5">
      <SectionTitle sub="Unstructured input: free-text observations from branch visits, scored for sentiment and risk themes. Newest first.">
        Officer notes
      </SectionTitle>
      {sorted.length === 0 ? (
        <p className="text-sm text-muted">No officer notes on file for the trailing 12 months.</p>
      ) : (
        <ol className="relative border-l-2 border-line ml-1.5 space-y-4 pt-1 max-h-[440px] overflow-y-auto pr-2">
          {sorted.map((n) => {
            const c = sentimentColor(n.sentiment)
            return (
              <li key={n.month_index} className="ml-4 relative">
                <span className="absolute -left-[22px] top-1.5 w-3 h-3 rounded-full"
                  style={{ background: c, boxShadow: `0 0 0 4px ${c}26` }} />
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-semibold text-teal uppercase tracking-wide">
                    Month {n.month_index} · {monthLabel(n.month_date)}
                  </span>
                  <SentimentChip sentiment={n.sentiment} />
                  {n.severity >= 2 && (
                    <Chip color={RAG.red} dot={false} title="Severity 0 none, 1 mild, 2 material, 3 severe">
                      severity {n.severity}
                    </Chip>
                  )}
                </div>
                <p className="text-sm text-slate-700 mt-1 leading-relaxed">{n.text}</p>
                {n.themes.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {n.themes.map((t) => <ThemeTag key={t} theme={t} />)}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

function AddObservation({ id }: { id: string }) {
  const fw = useFramework()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<NoteScore | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { setText(''); setRes(null); setErr(null) }, [id])

  const submit = async () => {
    const t = text.trim()
    if (!t) return
    setBusy(true); setErr(null)
    try {
      setRes(await api.scoreNote(id, t))
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle sub="Type a fresh branch observation. PRAHARI scores it and shows how the calibrated PD would respond if it were the latest note on file. Preview only; nothing is saved.">
        Add observation
      </SectionTitle>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="e.g. Unit visit: godown stock materially below statement; promoter evasive on receivables from the anchor buyer."
        className="w-full rounded-xl border border-line bg-paper/60 p-3 text-sm text-slate-700 placeholder:text-muted/70 focus:outline-none focus:border-teal/60 focus:bg-white resize-y"
      />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[11px] text-muted">{text.trim().length} characters</span>
        <button
          onClick={submit}
          disabled={busy || !text.trim()}
          className="px-4 py-2 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors disabled:opacity-50"
        >
          {busy ? 'Scoring…' : 'Score observation'}
        </button>
      </div>
      {err && <div className="mt-3 text-sm text-rag-red">{err}</div>}
      {res && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          className="mt-4 rounded-xl border border-line bg-paper/60 p-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <SentimentChip sentiment={res.sentiment} />
            <span className="text-xs text-muted">severity {res.severity} of 3</span>
            {res.themes.length > 0
              ? res.themes.map((t) => <ThemeTag key={t} theme={t} />)
              : <span className="text-xs text-muted">no themes detected</span>}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="rounded-xl bg-white border border-line p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">12-month PD</div>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <span className="text-sm text-muted">{pct(res.pd_before)}</span>
                <span className="text-muted">→</span>
                <span className="text-lg font-bold" style={{ color: fw.pdColor(res.pd_after) }}>{pct(res.pd_after)}</span>
                <PdDelta delta={res.pd_delta} />
              </div>
            </div>
            <div className="rounded-xl bg-white border border-line p-3">
              <div className="text-[11px] uppercase tracking-wide text-muted">Bucket</div>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <RagChip bucket={res.bucket_before} />
                <span className="text-muted">→</span>
                <RagChip bucket={res.bucket_after} />
                <GradeBadge grade={res.grade_after} compact />
              </div>
            </div>
          </div>
          <div className="text-[11px] text-muted">
            Scored by the <b className="font-semibold text-slate-600">{res.scorer}</b> scorer · PD change {pp(res.pd_delta, 2)} if this were the latest note on file
          </div>
        </motion.div>
      )}
    </Card>
  )
}

function ContagionBlock({ c }: { c: ContagionNodeResult }) {
  const fw = useFramework()
  const added = c.contagion_adjusted_pd - c.own_pd
  return (
    <Card className="p-5">
      <SectionTitle sub="This account supplies an anchor buyer. Anchor payment stress is diffused along the payment graph.">
        Contagion exposure
      </SectionTitle>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm text-muted">Own PD {pct(c.own_pd)}</span>
        <span className="text-muted">→</span>
        <span className="text-xl font-bold" style={{ color: fw.pdColor(c.contagion_adjusted_pd) }}>{pct(c.contagion_adjusted_pd)}</span>
        <span className="text-[11px] text-muted">contagion-adjusted</span>
        {added > 0.0005 && <PdDelta delta={added} />}
      </div>
      <div className="flex items-center justify-between py-2 mt-2 border-t border-line">
        <span className="text-sm text-muted">Runway impact</span>
        <span className="text-sm font-semibold" style={{ color: c.runway_delta < 0 ? RAG.red : '#0A1F44' }}>
          {c.runway_delta > 0 ? '+' : ''}{c.runway_delta.toFixed(1)} months
        </span>
      </div>
      {c.why ? (
        <p className="text-sm text-slate-700 mt-1 bg-rag-red/5 border border-rag-red/20 rounded-xl p-3 leading-relaxed">{c.why}</p>
      ) : (
        <p className="text-sm text-muted mt-1">No upstream anchor stress is adding to this account's PD at present.</p>
      )}
    </Card>
  )
}

function SeriesChart({ d }: { d: Detail }) {
  const hasDp = d.series.some((s) => (s.drawing_power_pct ?? 0) > 0)
  const data = d.series.map((s) => ({
    m: monthLabel(s.month_date),
    creditsL: +(s.credits / 1e5).toFixed(1),
    util: +(s.limit_utilisation * 100).toFixed(1),
    dp: hasDp && s.drawing_power_pct != null && s.drawing_power_pct > 0 ? +(s.drawing_power_pct * 100).toFixed(1) : null,
  }))
  return (
    <Card className="p-5">
      <SectionTitle sub={hasDp
        ? 'Sales inflows falling while limit utilisation creeps up and drawing power thins - drawings above drawing power are the classic stress signature.'
        : 'Sales inflows falling while limit utilisation creeps up - the classic stress signature.'}>
        Monthly credits vs. limit utilisation{hasDp ? ' and drawing power' : ''}
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
              label={{ value: '% of sanction', angle: 90, position: 'insideRight', fontSize: 10, fill: '#5B6B85', dy: -34 }} />
            <Tooltip
              contentStyle={{ borderRadius: 12, border: '1px solid #E3E8F0', fontSize: 12 }}
              formatter={(v: any, name: any) => name === 'Credits (₹ L)' ? [`₹${v} L`, name] : [`${v}%`, name]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area yAxisId="l" type="monotone" dataKey="creditsL" name="Credits (₹ L)" stroke={RAG.green} strokeWidth={2} fill="url(#credGrad)" />
            <Line yAxisId="r" type="monotone" dataKey="util" name="Utilisation %" stroke={RAG.red} strokeWidth={2} dot={false} />
            {hasDp && (
              <Line yAxisId="r" type="monotone" dataKey="dp" name="Drawing power %" stroke="#0B3D91" strokeWidth={1.75}
                strokeDasharray="5 4" dot={false} connectNulls />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function ComplianceClocks({ clocks }: { clocks: ComplianceClock[] }) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Regulatory timelines triggered for flagged accounts.">Compliance clocks</SectionTitle>
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

// ------------------------------------------------------------------ data coverage + PD history
const CONFIDENCE_COLOR: Record<Confidence, string> = { high: RAG.green, medium: RAG.amber, low: RAG.red }

/** How much conduct history the score rests on, with the backend's confidence label (Bundle.coverage()). */
function CoverageChip({ coverage }: { coverage: Coverage }) {
  const c = CONFIDENCE_COLOR[coverage.confidence] ?? '#5B6B85'
  return (
    <Chip color={c} title={`${pct(coverage.coverage, 0)} of a 24-month conduct window on file`}>
      Data: {coverage.months_on_file}/24 months, {coverage.confidence} confidence
    </Chip>
  )
}

const PARTIAL_COLOR = '#B8C2D4'
const HISTORY_AXIS = { fontSize: 10, fill: '#5B6B85' }

/** A point on the PD history line, coloured by the RAG bucket the account sat in that month. */
function BucketDot(props: any) {
  const { cx, cy, payload, dataKey } = props
  if (cx == null || cy == null || payload == null || payload[dataKey] == null) return <g />
  return <circle cx={cx} cy={cy} r={3.5} fill={RAG[payload.bucket as Bucket] ?? '#5B6B85'} stroke="#fff" strokeWidth={1.25} />
}

function HistoryTip({ active, payload }: { active?: boolean; payload?: any[] }) {
  const p = active ? payload?.[0]?.payload : undefined
  if (!p) return null
  return (
    <div className="rounded-xl border border-line bg-white px-3 py-2 text-xs shadow-soft">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-ink">{p.m}</span>
        <RagChip bucket={p.bucket as Bucket} />
        {!p.full_window && <span className="text-muted">partial window</span>}
      </div>
      <div className="text-muted mt-1">PD {pct(p.pd)} · {p.statutory_sma} ({p.dpd} DPD)</div>
    </div>
  )
}

/** GET /api/accounts/{id}/history: calibrated PD re-scored at every month the account had enough history. */
function PdHistoryChart({ id, loanType }: { id: string; loanType: string }) {
  const fw = useFramework()
  const [h, setH] = useState<PdHistory | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setH(null); setErr(null)
    api.history(id).then(setH).catch((e) => setErr(String(e)))
  }, [id])

  const t = thresholdsOf(fw.framework, loanType)

  const data = useMemo(() => {
    if (!h) return []
    const firstFull = h.points.findIndex((p) => p.full_window)
    return h.points.map((p, i) => {
      const v = +(p.pd * 100).toFixed(2)
      return {
        m: ymLabel(p.month_date), pd: p.pd, bucket: p.bucket, dpd: p.dpd, statutory_sma: p.statutory_sma, full_window: p.full_window,
        // the first full-window point sits in both series so the two lines join
        partial: firstFull === -1 || i <= firstFull ? v : null,
        full: p.full_window ? v : null,
      }
    })
  }, [h])

  const yMax = useMemo(() => {
    const top = Math.max(t.red_pd * 100 * 1.15, ...data.map((d) => d.pd * 100 * 1.1))
    return Math.min(100, Math.ceil(top / 10) * 10)
  }, [data, t.red_pd])

  const summary = useMemo(() => {
    if (!h) return ''
    const parts: string[] = []
    parts.push(h.first_flag_label ? `Flagged ${ymLabel(h.first_flag_label)}` : 'Not flagged on a full window yet')
    parts.push(`first arrears ${h.first_arrears_label ? ymLabel(h.first_arrears_label) : 'none yet'}`)
    const pdm = h.projected_default_month
    if (pdm != null && h.points.length) {
      const origin = h.points[0]
      parts.push(`projected 90+ DPD month ${ymLabel(shiftYm(origin.month_date, pdm - origin.month_index))} (month ${pdm})`)
    } else {
      parts.push('projected 90+ DPD month none')
    }
    if (h.lead_over_default_months != null) parts.push(`lead ${h.lead_over_default_months} months over 90+ DPD`)
    else if (h.lead_over_arrears_months != null) parts.push(`lead ${h.lead_over_arrears_months} months over first arrears`)
    if (h.lead_over_default_months != null && h.lead_over_arrears_months != null) {
      parts.push(`${h.lead_over_arrears_months} months over first arrears`)
    }
    return parts.join('; ')
  }, [h])

  return (
    <Card className="p-5">
      <SectionTitle sub="Calibrated 12-month PD re-scored at every month the account had enough history, using only data up to that month. Dashed grey points sit on a partial feature window and are not trusted as flags.">
        PD history: when PRAHARI flagged versus when arrears appeared
      </SectionTitle>
      {err ? (
        <div className="text-sm text-rag-red">{err}</div>
      ) : !h ? (
        <Spinner label="Re-scoring every month…" />
      ) : data.length === 0 ? (
        <p className="text-sm text-muted">Not enough history on file to score this account month by month.</p>
      ) : (
        <>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ top: 18, right: 64, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F8" vertical={false} />
                <XAxis dataKey="m" tick={HISTORY_AXIS} interval={data.length > 14 ? 1 : 0} tickLine={false} axisLine={{ stroke: '#E3E8F0' }} />
                <YAxis domain={[0, yMax]} tick={HISTORY_AXIS} tickLine={false} axisLine={false} tickFormatter={(v: any) => `${v}%`} />
                <Tooltip content={<HistoryTip />} />
                <ReferenceLine y={+(t.amber_pd * 100).toFixed(2)} stroke={RAG.amber} strokeDasharray="4 3"
                  label={{ value: `amber ${pct(t.amber_pd, 0)}`, position: 'right', fontSize: 10, fill: RAG.amber }} />
                <ReferenceLine y={+(t.red_pd * 100).toFixed(2)} stroke={RAG.red} strokeDasharray="4 3"
                  label={{ value: `red ${pct(t.red_pd, 0)}`, position: 'right', fontSize: 10, fill: RAG.red }} />
                {h.first_flag_label && (
                  <ReferenceLine x={ymLabel(h.first_flag_label)} stroke="#0B3D91" strokeWidth={1.5}
                    label={{ value: 'PRAHARI flag', position: 'insideTopRight', fontSize: 10, fill: '#0B3D91', fontWeight: 600 }} />
                )}
                {h.first_arrears_label && (
                  <ReferenceLine x={ymLabel(h.first_arrears_label)} stroke={NPA_COLOR} strokeWidth={1.5} strokeDasharray="6 3"
                    label={{ value: 'first arrears', position: 'insideBottomRight', fontSize: 10, fill: NPA_COLOR, fontWeight: 600 }} />
                )}
                <Line type="monotone" dataKey="partial" name="PD (partial window)" stroke={PARTIAL_COLOR} strokeWidth={1.5} strokeDasharray="4 3"
                  dot={{ r: 2.5, fill: PARTIAL_COLOR, stroke: '#fff', strokeWidth: 1 }} activeDot={{ r: 4, fill: PARTIAL_COLOR }} isAnimationActive={false} />
                <Line type="monotone" dataKey="full" name="Calibrated PD" stroke="#0B3D91" strokeWidth={2}
                  dot={(p: any) => <BucketDot key={p.key} {...p} />} activeDot={{ r: 5 }} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap items-center gap-4 mt-2 text-[11px] text-muted">
            <span className="inline-flex items-center gap-1.5"><span className="w-4 h-0.5 rounded bg-brand" /> full feature window</span>
            <span className="inline-flex items-center gap-1.5"><span className="w-4 border-t border-dashed" style={{ borderColor: PARTIAL_COLOR }} /> partial window</span>
            {(['green', 'amber', 'red'] as Bucket[]).map((b) => (
              <span key={b} className="inline-flex items-center gap-1.5 capitalize">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: RAG[b] }} />{b} that month
              </span>
            ))}
          </div>
          <p className="text-sm text-slate-700 mt-3 leading-relaxed">{summary}.</p>
        </>
      )}
    </Card>
  )
}
