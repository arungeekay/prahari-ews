import type {
  Portfolio, AccountsResp, AccountDetail, WhatIf, ContagionGraph,
  ModelCard, MonthlyRun, DocResp, Framework, MoversResp, NoteScore, DataSources,
  EwsSummary, ReviewIn, ReviewResp, AccountReviewsResp, ReviewsResp, Scenario,
  Backtest, PdHistory, ValueAtScale, AdapterDemo,
} from './types'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

const BASE = '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${res.status} ${res.statusText} on ${path}${body ? ` - ${body}` : ''}`)
  }
  return (await res.json()) as T
}

export const api = {
  /** Interpretation framework: thresholds, grade bands, vocabulary (one source of truth). */
  framework: () => req<Framework>('/framework'),
  portfolio: () => req<Portfolio>('/portfolio'),
  /** Accounts whose calibrated PD rose most since last month. */
  movers: (limit = 15) => req<MoversResp>(`/portfolio/movers?limit=${limit}`),
  /** Scored rows. By default only the prediction book (accounts not yet 90+ DPD); pass
   *  include_npa to add NPA accounts, or bucket 'npa' for NPA accounts alone. */
  accounts: (params: { bucket?: string; sort?: string; limit?: number; include_npa?: boolean } = {}) => {
    const q = new URLSearchParams()
    if (params.bucket) q.set('bucket', params.bucket)
    if (params.sort) q.set('sort', params.sort)
    if (params.limit) q.set('limit', String(params.limit))
    if (params.include_npa) q.set('include_npa', '1')
    const qs = q.toString()
    return req<AccountsResp>(`/accounts${qs ? `?${qs}` : ''}`)
  },
  account: (id: string) => req<AccountDetail>(`/accounts/${id}`),
  whatif: (id: string, action: string) =>
    req<WhatIf>(`/accounts/${id}/whatif?action=${encodeURIComponent(action)}`),
  /** Score a fresh officer observation and preview the PD response (nothing is persisted). */
  scoreNote: (id: string, text: string) =>
    req<NoteScore>(`/accounts/${id}/notes/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  contagion: () => req<ContagionGraph>('/contagion/graph'),
  /** Portfolio stress test: override one anchor's stress (0..1) and re-run the same diffusion. */
  scenario: (anchor_id: string, stress: number) =>
    req<Scenario>('/contagion/scenario', {
      method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ anchor_id, stress }),
    }),
  /** RBI EWS indicator families and their source line. */
  ewsIndicators: () => req<EwsSummary>('/ews-indicators'),
  /** Maker-checker: record a named officer's decision on a flag or drafted document. */
  review: (id: string, body: ReviewIn) =>
    req<ReviewResp>(`/accounts/${id}/review`, { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body) }),
  accountReviews: (id: string) => req<AccountReviewsResp>(`/accounts/${id}/reviews`),
  reviews: (limit = 100) => req<ReviewsResp>(`/reviews?limit=${limit}`),
  memo: (id: string) => req<DocResp>(`/accounts/${id}/memo`, { method: 'POST' }),
  crilc: (id: string) => req<DocResp>(`/accounts/${id}/crilc`, { method: 'POST' }),
  monthlyRun: () => req<MonthlyRun>('/agent/monthly-run', { method: 'POST' }),
  modelCard: () => req<ModelCard>('/model-card'),
  dataSources: () => req<DataSources>('/data-sources'),
  /** Twelve-month replay: score the book at a past as-of month with only what was known then. */
  backtest: (asOf?: number) => req<Backtest>(`/backtest${asOf != null ? `?as_of=${asOf}` : ''}`),
  /** Calibrated PD at every month the account could be scored: first flag versus first arrears. */
  history: (id: string) => req<PdHistory>(`/accounts/${id}/history`),
  /** Illustrative bank-scale arithmetic. default_rate is a fraction (0.053), not a percent. */
  value: (p: { book_cr: number; default_rate: number; avg_ticket_lakh: number; review_cost: number }) => {
    const q = new URLSearchParams({
      book_cr: String(p.book_cr), default_rate: String(p.default_rate),
      avg_ticket_lakh: String(p.avg_ticket_lakh), review_cost: String(p.review_cost),
    })
    return req<ValueAtScale>(`/value?${q.toString()}`)
  },
  /** Run the IDBI-catalogue adapter through the Finacle-shaped mock for the demo cast (2 to 5 seconds). */
  adapterDemo: () => req<AdapterDemo>('/data-sources/adapter-demo', { method: 'POST' }),
}
