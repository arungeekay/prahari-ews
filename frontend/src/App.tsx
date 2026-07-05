import { useEffect, useState } from 'react'
import { api } from './api'
import type { Portfolio } from './types'
import { NavContext, type Route, type Screen } from './nav'
import { Kpi } from './components/ui'
import { inrCr } from './format'
import { Portfolio as PortfolioScreen } from './screens/Portfolio'
import { AccountDetail } from './screens/AccountDetail'
import { Contagion } from './screens/Contagion'
import { AgentRun } from './screens/AgentRun'
import { ModelCard } from './screens/ModelCard'

const DEMO_ACCOUNT = 'MSME00001' // Sharma Fabricators — scripted demo (BUILD_SPEC §9.1)

const NAV: { key: Screen; label: string; icon: string }[] = [
  { key: 'portfolio', label: 'Portfolio Heat Map', icon: '▦' },
  { key: 'contagion', label: 'Contagion Map', icon: '◈' },
  { key: 'agent', label: 'Agent Run', icon: '⟳' },
  { key: 'model', label: 'Model Card', icon: '◔' },
]

export default function App() {
  const [route, setRoute] = useState<Route>({ screen: 'portfolio' })
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)

  useEffect(() => {
    api.portfolio().then(setPortfolio).catch(() => setPortfolio(null))
  }, [])

  const go = (screen: Screen, accountId?: string) => {
    setRoute({ screen, accountId })
    window.scrollTo({ top: 0 })
  }
  const openAccount = (id: string) => go('account', id)

  return (
    <NavContext.Provider value={{ route, go, openAccount }}>
      <div className="min-h-full flex">
        {/* Left nav */}
        <aside className="w-64 shrink-0 bg-ink text-white/90 flex flex-col sticky top-0 h-screen">
          <div className="px-5 pt-6 pb-5 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-teal flex items-center justify-center font-bold text-white text-lg">
                प
              </div>
              <div>
                <div className="font-bold text-white text-lg leading-none tracking-tight">PRAHARI</div>
                <div className="text-[10px] text-white/50 mt-1 uppercase tracking-wider">Early Warning System</div>
              </div>
            </div>
            <p className="text-[11px] text-white/45 mt-3 leading-snug">
              Behavioural default-prediction for MSME loan books · Track 4
            </p>
          </div>

          <nav className="px-3 py-4 flex-1">
            {NAV.map((n) => {
              const active = route.screen === n.key
              return (
                <button
                  key={n.key}
                  onClick={() => go(n.key)}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm mb-1 transition-colors ${
                    active ? 'bg-white/10 text-white font-semibold' : 'text-white/60 hover:bg-white/5 hover:text-white/90'
                  }`}
                >
                  <span className="text-base w-5 text-center opacity-80">{n.icon}</span>
                  {n.label}
                </button>
              )
            })}

            {/* Pinned demo shortcut */}
            <div className="mt-6 px-3">
              <div className="text-[10px] uppercase tracking-wider text-white/35 mb-2">Demo shortcut</div>
              <button
                onClick={() => openAccount(DEMO_ACCOUNT)}
                className={`w-full text-left px-3 py-2.5 rounded-xl border transition-colors ${
                  route.accountId === DEMO_ACCOUNT
                    ? 'border-teal bg-teal/15'
                    : 'border-white/10 hover:border-teal/60 hover:bg-white/5'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-rag-red" />
                  <span className="text-sm font-semibold text-white">Sharma Fabricators</span>
                </div>
                <div className="text-[11px] text-white/50 mt-0.5">Ludhiana · runway 7 mo · red</div>
              </button>
            </div>
          </nav>

          <div className="px-5 py-4 border-t border-white/10 text-[10px] text-white/35 leading-relaxed">
            IDBI Innovate 2026 · Synthetic data · AI recommends, an officer decides.
          </div>
        </aside>

        {/* Main */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Top bar with live KPI chips */}
          <header className="sticky top-0 z-30 bg-paper/90 backdrop-blur border-b border-line px-8 py-3 flex items-center justify-between gap-4">
            <div>
              <h1 className="text-ink font-semibold text-[15px] tracking-tight">
                PRAHARI watches the economy between the accounts
              </h1>
              <p className="text-muted text-xs">Live portfolio surveillance · numbers computed from the book, not hardcoded</p>
            </div>
            {portfolio && (
              <div className="flex items-center gap-2">
                <Kpi label="Accounts" value={portfolio.n_accounts.toLocaleString('en-IN')} />
                <Kpi label="Red exposure" value={inrCr(portfolio.red_exposure)} accent="#E5484D"
                  hint={`${portfolio.buckets.red.count} accounts`} />
                <Kpi label="Avg runway (red)" value={`${portfolio.avg_runway_red.toFixed(1)} mo`}
                  accent="#E5484D" hint={`${portfolio.buckets.red.count} red accounts`} />
              </div>
            )}
          </header>

          <main className="flex-1 p-8">
            {route.screen === 'portfolio' && <PortfolioScreen portfolio={portfolio} />}
            {route.screen === 'account' && route.accountId && <AccountDetail id={route.accountId} />}
            {route.screen === 'contagion' && <Contagion />}
            {route.screen === 'agent' && <AgentRun />}
            {route.screen === 'model' && <ModelCard />}
          </main>
        </div>
      </div>
    </NavContext.Provider>
  )
}
