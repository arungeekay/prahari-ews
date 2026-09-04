import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, LabelList,
} from 'recharts'
import { api } from '../api'
import type { Backtest as BacktestT, BacktestRow, BacktestSummary, LeadBin } from '../types'
import { useNav } from '../nav'
import { Card, SectionTitle, Spinner, ErrorBox, RAG, RagChip, MiniStat, Chip } from '../components/ui'
import { inr, pct, num, ymLabel, months } from '../format'

const LEAD_BINS: LeadBin[] = ['1-3', '4-6', '7-9', '10-12']
const BRAND = '#0B3D91'
const TEAL = '#0E7C7B'
const TOOLTIP_STYLE = { borderRadius: 12, border: '1px solid #E3E8F0', fontSize: 12 }

/** Validation fold each borrower sat in: A trained the model, B chose the thresholds, C was held out. */
const GROUP_HINT: Record<string, string> = {
  A: 'Fold A: this borrower was used to train the model',
  B: 'Fold B: used only to choose thresholds, never to train',
  C: 'Fold C: held out entirely',
}

export function Backtest() {
  const [bt, setBt] = useState<BacktestT | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.backtest().then(setBt).catch((e) => setErr(String(e)))
  }, [])

  if (err) return <ErrorBox message={err} />
  if (!bt) return <Spinner label="Rewinding the book twelve months and scoring it again…" />

  const asOf = ymLabel(bt.as_of_label)
  const outcome = ymLabel(bt.outcome_label)
  const nMissed = bt.all.n_realised_defaults - bt.all.n_caught

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-ink tracking-tight">Backtest</h2>
          <p className="text-muted text-sm mt-1">
            A twelve-month replay on this book. Nothing after the as-of month is used to score; outcomes are the observed 90+ DPD months that followed.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip dot={false} title="The month the book was re-scored as of">as of {bt.as_of_label} (month {bt.as_of})</Chip>
          <Chip dot={false}>{bt.horizon_months}-month outcome window</Chip>
          <Chip dot={false} title="Realised 90+ DPD months observed up to this month">outcomes to {bt.outcome_label}</Chip>
        </div>
      </div>

      {/* Headline banner */}
      <Card className="p-5 border-teal/30 bg-teal/[0.03]">
        <div className="flex items-start gap-3">
          <span className="mt-2 w-2.5 h-2.5 rounded-full shrink-0 bg-teal" />
          <div>
            <div className="text-lg font-bold text-ink leading-snug">
              Rewind to {asOf}: score the book with only what was known then, compare with what happened by {outcome}
            </div>
            <p className="text-sm text-slate-700 mt-1.5 leading-relaxed">
              {num(bt.all.n_realised_defaults)} of the {num(bt.all.n_scored)} scorable accounts went 90+ DPD in the following {bt.horizon_months} months.
              PRAHARI had already flagged {num(bt.all.n_caught)} of them ({pct(bt.all.capture, 0)} capture), a median {months(bt.all.median_lead_months)} ahead;
              an arrears-based system would have shown {num(bt.all.arrears_visible_at_as_of)} at the time. {num(nMissed)} were missed.
            </p>
          </div>
        </div>
      </Card>

      {/* Two scopes side by side */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <SummaryColumn
          s={bt.all} horizon={bt.horizon_months} title="All scorable accounts"
          caption="Every account standard or SMA at the as-of month, including the borrowers the model was trained on."
        />
        <SummaryColumn
          s={bt.unseen} horizon={bt.horizon_months} title="Borrowers never used to train the model" honest
          caption="The honest number. These borrowers sat in folds B and C, so the model had never seen them when it scored them."
        />
      </div>

      <LeadChart bt={bt} />

      <RowsTable
        title="Caught early" rows={bt.caught} total={bt.all.n_caught}
        sub={`Realised defaulters that were amber or red at ${asOf}, furthest lead first. Click a row to open the account.`}
      />
      <RowsTable
        title="Missed" rows={bt.missed} total={nMissed} missed
        sub={`Realised defaulters that were still green at ${asOf}, largest exposure first. Click a row to open the account.`}
      />

      <p className="text-[11px] text-muted italic leading-snug">{bt.note}</p>
    </div>
  )
}

function SummaryColumn({
  s, title, caption, horizon, honest = false,
}: { s: BacktestSummary; title: string; caption: string; horizon: number; honest?: boolean }) {
  const missed = s.n_realised_defaults - s.n_caught
  return (
    <Card className={`p-5 ${honest ? 'border-teal/40 bg-teal/[0.03]' : ''}`}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub={caption}>{title}</SectionTitle>
        {honest && <Chip color={TEAL} dot={false} title={s.scope}>out of sample</Chip>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat label="Accounts scored" value={num(s.n_scored)} sub="standard or SMA at as-of" />
        <MiniStat label="Flagged" value={num(s.n_flagged)} accent={RAG.amber} sub={`${pct(s.flag_rate)} of the book, amber or red`} />
        <MiniStat label="Realised defaults" value={num(s.n_realised_defaults)} sub={`90+ DPD within ${horizon} months`} />
        <MiniStat label="Caught" value={num(s.n_caught)} accent={RAG.green}
          sub={`${pct(s.capture, 0)} capture · ${num(s.n_caught_red)} red (${pct(s.capture_red, 0)})`} />
        <MiniStat label="Arrears would have shown" value={num(s.arrears_visible_at_as_of)} accent="#5B6B85"
          sub="defaulters already past due at as-of" />
        <MiniStat label="Median lead" value={months(s.median_lead_months)} sub={`mean ${months(s.mean_lead_months)}`} />
        <MiniStat label="Provisioning actionable" value={inr(s.provisioning_actionable)} accent={RAG.green}
          sub={`on ${inr(s.caught_exposure)} caught`} />
        <MiniStat label="Missed" value={num(missed)} accent={missed > 0 ? RAG.red : RAG.green} sub={`${inr(s.missed_exposure)} exposure`} />
      </div>
      <p className="text-[11px] text-muted mt-3">
        Precision {pct(s.precision)}: that share of the flagged accounts went on to default within the window. Scope: {s.scope}.
      </p>
    </Card>
  )
}

function LeadChart({ bt }: { bt: BacktestT }) {
  const data = LEAD_BINS.map((b) => ({
    bin: `${b} mo`,
    all: bt.all.lead_distribution[b] ?? 0,
    unseen: bt.unseen.lead_distribution[b] ?? 0,
  }))
  return (
    <Card className="p-5">
      <SectionTitle sub={`Months between the flag at ${ymLabel(bt.as_of_label)} and the month the account reached 90+ DPD, for the defaults caught, in both scopes.`}>
        Lead time on the defaults caught
      </SectionTitle>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F8" vertical={false} />
            <XAxis dataKey="bin" tick={{ fontSize: 11, fill: '#5B6B85' }} tickLine={false} axisLine={{ stroke: '#E3E8F0' }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: '#5B6B85' }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(10,31,68,0.04)' }}
              formatter={(v: any, name: any) => [`${v} accounts`, name]} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="all" name="All scorable accounts" fill={BRAND} radius={[6, 6, 0, 0]}>
              <LabelList dataKey="all" position="top" style={{ fontSize: 11, fill: '#0A1F44', fontWeight: 600 }} />
            </Bar>
            <Bar dataKey="unseen" name="Never used to train" fill={TEAL} radius={[6, 6, 0, 0]}>
              <LabelList dataKey="unseen" position="top" style={{ fontSize: 11, fill: '#0A1F44', fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[11px] text-muted mt-2 leading-snug">
        The right-most bars are the accounts flagged 10 to 12 months before they slipped to 90+ DPD; a full year of runway for the officer.
      </p>
    </Card>
  )
}

function RowsTable({
  title, sub, rows, total, missed = false,
}: { title: string; sub: string; rows: BacktestRow[]; total: number; missed?: boolean }) {
  const { openAccount } = useNav()
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub={sub}>{title}</SectionTitle>
        <Chip color={missed ? RAG.red : RAG.green}>
          {rows.length < total ? `${num(rows.length)} of ${num(total)} shown` : `${num(total)} accounts`}
        </Chip>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">No accounts in this group.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                <th className="py-2 pr-3 font-medium">Account</th>
                <th className="py-2 px-3 font-medium">Facility</th>
                <th className="py-2 px-3 font-medium">Sector</th>
                <th className="py-2 px-3 font-medium text-right">PD then</th>
                <th className="py-2 px-3 font-medium">Bucket</th>
                <th className="py-2 px-3 font-medium text-right">Exposure</th>
                <th className="py-2 px-3 font-medium text-right whitespace-nowrap">Months ahead</th>
                {missed && <th className="py-2 px-3 font-medium text-right whitespace-nowrap">DPD at as-of</th>}
                <th className="py-2 pl-3 font-medium">Fold</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.borrower_id} onClick={() => openAccount(r.borrower_id)}
                  className="border-b border-line last:border-0 hover:bg-paper cursor-pointer align-top">
                  <td className="py-2 pr-3">
                    <div className="font-medium text-ink">{r.name}</div>
                    <div className="text-[11px] text-muted">{r.borrower_id}</div>
                  </td>
                  <td className="py-2 px-3 text-slate-600">{r.loan_type}</td>
                  <td className="py-2 px-3 text-slate-600 capitalize">{r.sector.replace('_', ' ')}</td>
                  <td className="py-2 px-3 text-right font-semibold text-ink">{pct(r.pd)}</td>
                  <td className="py-2 px-3"><RagChip bucket={r.bucket} /></td>
                  <td className="py-2 px-3 text-right font-semibold text-ink whitespace-nowrap">{inr(r.exposure)}</td>
                  <td className="py-2 px-3 text-right text-slate-600">{r.months_ahead}</td>
                  {missed && (
                    <td className="py-2 px-3 text-right font-semibold" style={{ color: r.dpd_at_as_of > 0 ? RAG.amber : '#5B6B85' }}>
                      {r.dpd_at_as_of}
                    </td>
                  )}
                  <td className="py-2 pl-3">
                    <Chip dot={false} color={r.group === 'A' ? '#5B6B85' : TEAL} title={GROUP_HINT[r.group] ?? r.group}>{r.group}</Chip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
