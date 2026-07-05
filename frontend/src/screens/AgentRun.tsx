import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api'
import type { MonthlyRun } from '../types'
import { useNav } from '../nav'
import { Card, SectionTitle, RagChip, RAG } from '../components/ui'
import { inr, pct } from '../format'

export function AgentRun() {
  const { openAccount } = useNav()
  const [result, setResult] = useState<MonthlyRun | null>(null)
  const [running, setRunning] = useState(false)
  const [shownLines, setShownLines] = useState(0)
  const [done, setDone] = useState(false)
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
      timers.current.push(window.setTimeout(() => { setDone(true); setRunning(false) }, 550 * (r.activity_log.length + 1)))
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

          {/* Watch-list + commentary */}
          <div className="lg:col-span-2 space-y-6">
            <AnimatePresence>
              {done && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                  <Card className="p-5">
                    <SectionTitle sub="Shortest-runway red accounts — action these first.">
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
                            <th className="py-2 pl-3 font-medium">Bucket</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.watchlist.map((a) => (
                            <tr key={a.borrower_id}
                              onClick={() => openAccount(a.borrower_id)}
                              className="border-b border-line last:border-0 hover:bg-paper cursor-pointer">
                              <td className="py-2.5 pr-3">
                                <div className="font-medium text-ink">{a.name}</div>
                                <div className="text-[11px] text-muted">{a.borrower_id} · {a.city}</div>
                              </td>
                              <td className="py-2.5 px-3 capitalize text-slate-600">{a.sector.replace('_', ' ')}</td>
                              <td className="py-2.5 px-3 text-right font-semibold text-ink">{inr(a.exposure)}</td>
                              <td className="py-2.5 px-3 text-right" style={{ color: RAG.red }}>{pct(a.pd, 0)}</td>
                              <td className="py-2.5 px-3 text-right font-semibold">{a.runway_label} mo</td>
                              <td className="py-2.5 pl-3"><RagChip bucket={a.bucket} /></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>

                  <Card className="p-5">
                    <SectionTitle sub="Auto-drafted — for officer review.">Portfolio early-warning commentary</SectionTitle>
                    <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">{result.commentary}</pre>
                  </Card>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  )
}
