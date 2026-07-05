import { createContext, useContext } from 'react'

export type Screen = 'portfolio' | 'account' | 'contagion' | 'agent' | 'model'

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
