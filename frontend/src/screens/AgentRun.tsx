import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api'
import type { MonthlyRun, ReviewRecord } from '../types'
import { useNav } from '../nav'
import { useFramework } from '../framework'
import { Card, SectionTitle, RagChip, RAG, GradeBadge, smaColor, Chip, Spinner } from '../components/ui'
import { inr, pct, timestamp } from '../format'

export function AgentRun() {
  const { openAccount } = useNav()
  const fw = useFramework()
  const [result, setResult] = useState<MonthlyRun | null>(null)
  const [running, setRunning] = useState(false)
  const [shownLines, setShownLines] = useState(0)
  const [done, setDone] = useState(false)
  const [runCount, setRunCount] = useState(0)
  const timers = useRef<number[]>([])

  useEffect(() => () => { timers.current.forEach(clearTimeout) }, [])

  const run = async () => {
    setRunning(true); setResult(null); setShownLines(0); setDone(false)
    timers.current.forEach(clearTimeout); timers.current = []
    try {
      const r = await api.monthlyRun()
      setResult(r)
      // Reveal the activity log line-by-line, then unveil results.
      r.activity_log.forEach((_, i) => {
        timers.current.push(window.setTimeout(() => setShownLines(i + 1), 550 * (i + 1)))
      })
      timers.current.push(window.setTimeout(() => {
        setDone(true); setRunning(false); setRunCount((n) => n + 1)
      }, 550 * (r.activity_log.length + 1)))
    } catch {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink tracking-tight">Monthly Agent Run</h2>
          <p className="text-muted text-sm mt-1">
            One click recomputes every account, refreshes the watch-list, drafts memos and writes portfolio commentary.
          </p>
        </div>
        <button
          onClick={run}
          disabled={running}
          className="px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-brand hover:bg-ink transition-colors shadow-soft disabled:opacity-60"
        >
          {running ? 'Running…' : result ? 'Run again' : 'Run monthly surveillance'}
        </button>
      </div>

      {!result && !running && (
        <Card className="p-10 text-center text-muted">
          <div className="text-5xl mb-3 opacity-30">⟳</div>
          Press “Run monthly surveillance” to start the agent.
        </Card>
      )}

      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Activity log */}
          <Card className="p-5 lg:col-span-1 self-start">
            <SectionTitle sub="What the agent did, in order.">Activity log</SectionTitle>
            <div className="space-y-2.5">
              {result.activity_log.slice(0, shownLines).map((line, i) => {
                const isLast = i === result.activity_log.length - 1
                return (
                  <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                    className="flex items-start gap-2.5 text-sm">
                    <span className="mt-1 w-4 h-4 shrink-0 rounded-full flex items-center justify-center text-[10px] text-white"
                      style={{ background: isLast && done ? RAG.green : RAG.amber }}>
                      {isLast && done ? '✓' : '•'}
                    </span>
                    <span className={isLast && done ? 'text-ink font-medium' : 'text-slate-600'}>{line}</span>
                  </motion.div>
                )
              })}
              {running && shownLines < result.activity_log.length && (
                <div className="flex items-center gap-2 text-xs text-muted pl-6">
                  <span className="w-3 h-3 rounded-full border-2 border-line border-t-brand animate-spin" /> working…
                </div>
              )}
            </div>
          </Card>

          {/* Watch-list + contagion re-buckets + commentary */}
          <div className="lg:col-span-2 space-y-6">
            <AnimatePresence>
              {done && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                  <Card className="p-5">
                    <SectionTitle sub="Shortest-runway red accounts - action these first.">
                      Watch-list ({result.watchlist.length})
                    </SectionTitle>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                            <th className="py-2 pr-3 font-medium">Account</th>
                            <th className="py-2 px-3 font-medium">Sector</th>
                            <th className="py-2 px-3 font-medium text-right">Exposure</th>
                            <th className="py-2 px-3 font-medium text-right">PD</th>
                            <th className="py-2 px-3 font-medium text-right">Runway</th>
                            <th className="py-2 px-3 font-medium">Statutory</th>
                            <th className="py-2 pl-3 font-medium">Bucket</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.watchlist.map((a) => (
                            <tr key={a.borrower_id}
                              onClick={() => openAccount(a.borrower_id)}
                              className="border-b border-line last:border-0 hover:bg-paper cursor-pointer">
                              <td className="py-2.5 pr-3">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-ink">{a.name}</span>
                                  <GradeBadge grade={a.grade} label={a.grade_label} compact />
                                </div>
                                <div className="text-[11px] text-muted">{a.borrower_id} · {a.city}</div>
                              </td>
                              <td className="py-2.5 px-3 capitalize text-slate-600">{a.sector.replace('_', ' ')}</td>
                              <td className="py-2.5 px-3 text-right font-semibold text-ink">{inr(a.exposure)}</td>
                              <td className="py-2.5 px-3 text-right" style={{ color: fw.pdColor(a.pd, a.loan_type) }}>{pct(a.pd, 0)}</td>
                              <td className="py-2.5 px-3 text-right font-semibold">{a.runway_label} mo</td>
                              <td className="py-2.5 px-3 whitespace-nowrap">
                                <span className="inline-flex items-center gap-1.5 text-xs font-semibold" style={{ color: smaColor(a.statutory_sma) }}>
                                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: smaColor(a.statutory_sma) }} />
                                  {a.statutory_sma} <span className="text-muted font-normal">({a.dpd} DPD)</span>
                                </span>
                              </td>
                              <td className="py-2.5 pl-3"><RagChip bucket={a.bucket} /></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>

                  <Card className="p-5">
                    <SectionTitle sub="Supplier accounts moved to a worse bucket only because their anchor buyer's payments slowed; their own repayment record is still clean.">
                      Re-bucketed by contagion while their own conduct is clean ({result.contagion_flagged.length})
                    </SectionTitle>
                    {result.contagion_flagged.length === 0 ? (
                      <p className="text-sm text-muted">No supplier account was re-bucketed by contagion this month.</p>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {result.contagion_flagged.map((c) => (
                          <button key={c.id} onClick={() => openAccount(c.id)}
                            className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-line hover:border-teal/50 hover:bg-teal/5 transition-colors text-left">
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-ink truncate">{c.label}</div>
                              <div className="text-[11px] text-muted">{c.id}</div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0 text-sm whitespace-nowrap">
                              <span style={{ color: fw.pdColor(c.own_pd) }}>{pct(c.own_pd)}</span>
                              <span className="text-muted">→</span>
                              <span className="font-bold" style={{ color: fw.pdColor(c.contagion_adjusted_pd) }}>{pct(c.contagion_adjusted_pd)}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </Card>

                  <Card className="p-5">
                    <SectionTitle sub="Auto-drafted - for officer review.">Portfolio early-warning commentary</SectionTitle>
                    <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">{result.commentary}</pre>
                  </Card>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}

      <ReviewLog refreshKey={runCount} />
    </div>
  )
}

const REVIEW_ACTION_COLOR: Record<string, string> = {
  approve: RAG.green, return: RAG.amber, clear: '#0E7C7B', file: '#0B3D91',
}

/** Maker-checker audit trail (GET /api/reviews), newest first. Re-fetched after each agent run. */
function ReviewLog({ refreshKey }: { refreshKey: number }) {
  const { openAccount } = useNav()
  const [rows, setRows] = useState<ReviewRecord[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = () => {
    setErr(null)
    api.reviews(50).then((r) => setRows(r.reviews)).catch((e) => setErr(String(e)))
  }
  useEffect(() => { load() }, [refreshKey])

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <SectionTitle sub="Maker-checker audit trail: every approval, return, clearance and filing by a named officer, newest first.">
          Review log{rows ? ` (${rows.length})` : ''}
        </SectionTitle>
        <button onClick={load} className="text-xs font-medium text-brand hover:underline">Refresh</button>
      </div>
      {err ? (
        <div className="text-sm text-rag-red">{err}</div>
      ) : !rows ? (
        <Spinner label="Loading review log…" />
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">
          No officer decisions recorded yet. Approve, return, clear or file from an account's Review card, or "Approve and file" a drafted memo.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted border-b border-line">
                <th className="py-2 pr-3 font-medium">Id</th>
                <th className="py-2 px-3 font-medium">Account</th>
                <th className="py-2 px-3 font-medium">Action</th>
                <th className="py-2 px-3 font-medium">Reviewer</th>
                <th className="py-2 px-3 font-medium">Note</th>
                <th className="py-2 pl-3 font-medium text-right">Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-line last:border-0 hover:bg-paper align-top">
                  <td className="py-2 pr-3 font-mono text-xs text-muted">{r.id}</td>
                  <td className="py-2 px-3">
                    <button onClick={() => openAccount(r.account_id)} className="font-medium text-brand hover:underline">{r.account_id}</button>
                    {r.document_type && <div className="text-[11px] text-muted">{r.document_type}</div>}
                  </td>
                  <td className="py-2 px-3"><Chip color={REVIEW_ACTION_COLOR[r.action] ?? '#5B6B85'} className="capitalize">{r.action}</Chip></td>
                  <td className="py-2 px-3 text-slate-700">{r.reviewer}</td>
                  <td className="py-2 px-3 text-slate-600 text-[12px] max-w-[320px]">{r.note || <span className="text-muted">-</span>}</td>
                  <td className="py-2 pl-3 text-right text-xs text-muted whitespace-nowrap">{timestamp(r.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
