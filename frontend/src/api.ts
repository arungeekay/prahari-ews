import type {
  Portfolio, AccountsResp, AccountDetail, WhatIf, ContagionGraph,
  ModelCard, MonthlyRun, DocResp,
} from './types'

const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status} ${res.statusText} on ${path}${body ? ` — ${body}` : ''}`)
  }
  return (await res.json()) as T
}

export const api = {
  portfolio: () => req<Portfolio>('/portfolio'),
  accounts: (params: { bucket?: string; sort?: string; limit?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.bucket) q.set('bucket', params.bucket)
    if (params.sort) q.set('sort', params.sort)
    if (params.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return req<AccountsResp>(`/accounts${qs ? `?${qs}` : ''}`)
  },
  account: (id: string) => req<AccountDetail>(`/accounts/${id}`),
  whatif: (id: string, action: string) =>
    req<WhatIf>(`/accounts/${id}/whatif?action=${encodeURIComponent(action)}`),
  contagion: () => req<ContagionGraph>('/contagion/graph'),
  memo: (id: string) => req<DocResp>(`/accounts/${id}/memo`, { method: 'POST' }),
  crilc: (id: string) => req<DocResp>(`/accounts/${id}/crilc`, { method: 'POST' }),
  monthlyRun: () => req<MonthlyRun>('/agent/monthly-run', { method: 'POST' }),
  modelCard: () => req<ModelCard>('/model-card'),
}
