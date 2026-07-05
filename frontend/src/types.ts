// Types mirror the PRAHARI backend (prahari/backend/app.py) exactly.

export type Bucket = 'red' | 'amber' | 'green'

export interface BucketStat {
  count: number
  exposure: number
}

export interface Portfolio {
  n_accounts: number
  total_exposure: number
  avg_runway: number
  avg_runway_flagged: number
  avg_runway_red: number
  n_flagged: number
  buckets: Record<Bucket, BucketStat>
  red_exposure: number
  provision_now: number
  provision_at_npa: number
  provision_saved_acting_now: number
  sector_exposure: Record<string, number>
}

export interface Account {
  borrower_id: string
  name: string
  sector: string
  city: string
  state: string
  loan_type: string
  sanctioned_limit: number
  pd: number
  runway_months: number
  runway_label: string
  bucket: Bucket
  exposure: number
  utilisation: number
  is_anchor_supplier: boolean
  anchor_id: string
  contagion_induced: boolean
  demo: string
  as_of: number
}

export interface AccountsResp {
  count: number
  accounts: Account[]
}

export interface ReasonCode {
  factor: string
  plain: string
  contribution: number
  value: number
}

export interface AuditorRow {
  factor: string
  value: number
  shap_value: number
  plain: string
}

export interface Beat {
  month: number
  month_label: string
  text: string
}

export interface ComplianceClock {
  name: string
  window_days: number
  days_remaining: number
  detail: string
}

export interface SeriesPoint {
  month_index: number
  month_date: string
  credits: number
  limit_utilisation: number
  gst_filing_delay_days: number
  cheque_bounces_outward: number
  dpd: number
  electricity_units: number
  month_end_balance: number
}

export interface AccountDetail {
  borrower_id: string
  name: string
  sector: string
  city: string
  state: string
  loan_type: string
  sanctioned_limit: number
  pd: number
  bucket: Bucket
  runway_months: number
  runway_label: string
  exposure: number
  utilisation: number
  reason_codes: ReasonCode[]
  auditor_table: AuditorRow[]
  storyline: string
  beats: Beat[]
  compliance_clocks: ComplianceClock[]
  contagion: unknown | null
  series: SeriesPoint[]
  whatif_actions: string[]
}

export interface WhatIf {
  action: string
  label: string
  note: string
  runway_before: number
  runway_after: number
  runway_delta: number
  exposure_before: number
  exposure_after: number
  provision_before: number
  provision_after: number
  provision_saved_vs_npa: number
}

export interface AnchorNode {
  id: string
  label: string
  kind: 'anchor'
  sector: string
  n_suppliers: number
  stress: number
}

export interface SupplierNode {
  id: string
  label: string
  kind: 'supplier'
  sector: string
  own_pd: number
  stress: number
  contagion_adjusted_pd: number
  runway_delta: number
  anchor_id: string
}

export type GraphNode = AnchorNode | SupplierNode

export interface GraphEdge {
  source: string
  target: string
  amount: number
  inflow_share: number
}

export interface ContagionGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ConfMatrix {
  auc: number
  balanced_accuracy: number
  precision: number
  recall: number
  f1: number
  operating_threshold: number
  confusion_matrix: [[number, number], [number, number]]
  n_train: number
  n_valid: number
  valid_positive_rate: number
  validation: string
  horizon_months: number
}

export interface CostOfError {
  cost_per_missed_default: number
  cost_per_false_alarm: number
  asymmetry_ratio: number
  defaults_in_validation: number
  caught: number
  missed: number
  false_alarms: number
  provision_at_risk_without_ews: number
  residual_cost_with_ews: number
  provision_preserved: number
  note: string
}

export interface ModelCard {
  name: string
  task: string
  algorithm: string
  features: string[]
  metrics: ConfMatrix
  honesty_note: string
  cost_of_error?: CostOfError
}

export interface MonthlyRun {
  activity_log: string[]
  watchlist: Account[]
  commentary: string
}

export interface DocResp {
  document_type: string
  account_id: string
  text: string
}
