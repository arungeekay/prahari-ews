import { createContext, useContext } from 'react'

export type Screen = 'portfolio' | 'backtest' | 'account' | 'contagion' | 'agent' | 'model' | 'sources'

export interface Route {
  screen: Screen
  accountId?: string
}

export interface NavCtx {
  route: Route
  go: (screen: Screen, accountId?: string) => void
  openAccount: (id: string) => void
}

export const NavContext = createContext<NavCtx | null>(null)

export function useNav(): NavCtx {
  const ctx = useContext(NavContext)
  if (!ctx) throw new Error('useNav must be used within NavContext')
  return ctx
}

// ------------------------------------------------------------------ URL hash routing
// Every screen is deep-linkable, so headless screenshots and the deck can open one directly:
//   #/portfolio  #/backtest  #/account/{id}  #/contagion  #/agent  #/model  #/sources
// App.tsx keeps the state-based NavContext and syncs it with window.location.hash.

const SCREENS: readonly Screen[] = ['portfolio', 'backtest', 'account', 'contagion', 'agent', 'model', 'sources']

export const DEFAULT_ROUTE: Route = { screen: 'portfolio' }

/** Parse a location hash into a route. Anything unrecognised falls back to the portfolio. */
export function parseHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, '').replace(/\/+$/, '')
  const [screen, ...rest] = path.split('/')
  if (screen === 'account') {
    let id = rest.join('/')
    try { id = decodeURIComponent(id) } catch { /* keep the raw segment */ }
    return id ? { screen: 'account', accountId: id } : DEFAULT_ROUTE
  }
  return (SCREENS as readonly string[]).includes(screen) ? { screen: screen as Screen } : DEFAULT_ROUTE
}

export function toHash(route: Route): string {
  return route.screen === 'account' && route.accountId
    ? `#/account/${encodeURIComponent(route.accountId)}`
    : `#/${route.screen}`
}

export const sameRoute = (a: Route, b: Route): boolean =>
  a.screen === b.screen && (a.accountId ?? '') === (b.accountId ?? '')
