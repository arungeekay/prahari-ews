import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ModelCard as Card_, CostOfError } from '../types'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, CountUpCr } from '../components/ui'
import { pct, num, inr } from '../format'

export function ModelCard() {
  const [mc, setMc] = useState<Card_ | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.modelCard().then(setMc).catch((e) => setErr(String(e)))
  }, [])

  if (err) return <ErrorBox message={err} />
  if (!mc) return <Spinner label="Loading model card…" />

  const m = mc.metrics
  const [[tn, fp], [fn, tp]] = m.confusion_matrix

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-ink tracking-tight">{mc.name}</h2>
        <p className="text-muted text-sm mt-1">{mc.task} · {mc.algorithm}</p>
      </div>

      {/* Headline metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Headline label="AUC" value={m.auc.toFixed(4)} big accent={RAG.green} sub="ranking quality" />
        <Headline label="Balanced accuracy" value={pct(m.balanced_accuracy, 1)} big accent={RAG.green} sub="headline (not raw accuracy)" />
        <Headline label="Recall" value={pct(m.recall, 1)} sub="stress caught" />
        <Headline label="Precision" value={pct(m.precision, 1)} sub="at chosen threshold" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Confusion matrix */}
        <Card className="p-5">
          <SectionTitle sub={`Validation set: ${num(m.n_valid)} accounts · operating threshold ${m.operating_threshold}`}>
            Confusion matrix
          </SectionTitle>
          <div className="grid grid-cols-[auto_1fr_1fr] gap-2 text-sm">
            <div />
            <div className="text-center text-[11px] font-medium text-muted pb-1">Pred. no default</div>
            <div className="text-center text-[11px] font-medium text-muted pb-1">Pred. default</div>

            <div className="flex items-center text-[11px] font-medium text-muted pr-1">Actual<br/>no default</div>
            <MatrixCell value={tn} label="True negative" good />
            <MatrixCell value={fp} label="False positive" />

            <div className="flex items-center text-[11px] font-medium text-muted pr-1">Actual<br/>default</div>
            <MatrixCell value={fn} label="False negative (missed)" bad />
            <MatrixCell value={tp} label="True positive (caught)" good />
          </div>
          <div className="grid grid-cols-3 gap-3 mt-4">
            <MiniStat label="F1" value={m.f1.toFixed(3)} />
            <MiniStat label="Horizon" value={`${m.horizon_months} mo`} />
            <MiniStat label="Base rate" value={pct(m.valid_positive_rate, 1)} />
          </div>
        </Card>

        {/* Validation + honesty */}
        <div className="space-y-6">
          <Card className="p-5">
            <SectionTitle>Temporal validation</SectionTitle>
            <p className="text-sm text-slate-700 leading-relaxed">{m.validation}</p>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <MiniStat label="Train rows" value={num(m.n_train)} />
              <MiniStat label="Validation rows" value={num(m.n_valid)} />
            </div>
          </Card>

          <Card className="p-5 border-teal/30 bg-teal/[0.03]">
            <SectionTitle>Honesty note</SectionTitle>
            <p className="text-sm text-slate-700 leading-relaxed">{mc.honesty_note}</p>
          </Card>
        </div>
      </div>

      {/* Cost of error - the money argument for high recall */}
      {mc.cost_of_error && <CostOfErrorPanel c={mc.cost_of_error} />}

      {/* Features */}
      <Card className="p-5">
        <SectionTitle sub={`${mc.features.length} point-in-time behavioural features - no data after the as-of month (leakage-tested).`}>
          Model features
        </SectionTitle>
        <div className="flex flex-wrap gap-1.5">
          {mc.features.map((f) => (
            <span key={f} className="text-[11px] font-mono px-2 py-1 rounded-md bg-paper border border-line text-slate-600">{f}</span>
          ))}
        </div>
      </Card>
    </div>
  )
}

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

function Headline({ label, value, sub, big, accent }: { label: string; value: string; sub?: string; big?: boolean; accent?: string }) {
  return (
    <Card className="p-4">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`font-bold mt-1 ${big ? 'text-3xl' : 'text-2xl'}`} style={{ color: accent ?? '#0A1F44' }}>{value}</div>
      {sub && <div className="text-[11px] text-muted mt-0.5">{sub}</div>}
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

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-paper border border-line p-3 text-center">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-bold text-ink mt-0.5">{value}</div>
    </div>
  )
}
