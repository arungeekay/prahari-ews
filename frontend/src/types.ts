// Types mirror the PRAHARI backend (prahari/backend/app.py) exactly.
// Shapes for the model card come from core/models/pd_model.py + core/models/metrics.py,
// the contagion payload from core/models/contagion.py, the framework from core/interpret.

export type Bucket = 'red' | 'amber' | 'green'

/** Data-coverage confidence from months of conduct on file: high 18+, medium 12 to 17, low below 12 (Bundle.coverage()). */
export type Confidence = 'high' | 'medium' | 'low'

/** Unified risk grades from the interpretation framework, best to worst. */
export const GRADES = ['PR1', 'PR2', 'PR3', 'PR4', 'PR5', 'PR6', 'PR7'] as const
export type Grade = (typeof GRADES)[number]

/** Statutory SMA labels (RBI, by days past due) in ladder order. */
export const SMA_ORDER = ['Standard', 'SMA-0', 'SMA-1', 'SMA-2', 'NPA'] as const

export interface BucketStat {
  count: number
  exposure: number
}

// ------------------------------------------------------------------ portfolio
/** Portfolio figures describe the prediction book (accounts still standard or SMA); accounts already
 *  at 90+ DPD are reported separately as n_npa / npa_exposure, and n_book is the full book. */
export interface Portfolio {
  n_accounts: number
  n_npa: number
  npa_exposure: number
  n_book: number
  total_exposure: number
  avg_runway: number
  avg_runway_red: number | null
  avg_runway_flagged: number | null
  n_flagged: number
  buckets: Record<Bucket, BucketStat>
  red_exposure: number
  provision_now: number
  provision_at_npa: number
  provision_saved_acting_now: number
  sector_exposure: Record<string, number>
  loan_type_mix: Record<string, number>
  grades: Record<string, BucketStat>
  statutory_sma_mix: Record<string, number>
  n_movers_up: number
  /** Accounts an officer cleared that are still inside the cooling period (suppressed from movers and the watch-list). */
  n_suppressed: number
  /** Date label of the as-of month, e.g. 2026-06 (never a bare month index). */
  as_of_label: string
  framework_version: string
  data_source: string | null
}

/** One scored row of the book (GET /api/accounts, agent watch-list). */
export interface Account {
  borrower_id: string
  name: string
  sector: string
  city: string
  state: string
  loan_type: string
  sanctioned_limit: number
  pd: number
  pd_prev: number
  pd_delta: number
  runway_months: number
  runway_label: string
  bucket: Bucket
  grade: string
  grade_label: string
  grade_score: number
  statutory_sma: string
  dpd: number
  model_implied_sma: string
  exposure: number
  utilisation: number
  drawing_power_pct: number
  is_anchor_supplier: boolean
  anchor_id: string
  /** Already 90+ DPD: a classification fact, not a prediction target. */
  is_npa: boolean
  /** Months of conduct on file (24 is a full window) and the confidence label it implies. */
  months_on_file: number
  confidence: Confidence
  demo: string
  as_of: number
}

export interface AccountsResp {
  count: number
  accounts: Account[]
}

/** GET /api/portfolio/movers */
export interface Mover {
  borrower_id: string
  name: string
  sector: string
  loan_type: string
  pd_prev: number
  pd: number
  pd_delta: number
  bucket: Bucket
  grade: string
  runway_months: number
  exposure: number
  statutory_sma: string
  top_reasons: string[]
}

export interface MoversResp {
  count: number
  movers: Mover[]
}

// ------------------------------------------------------------------ account detail
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

/** Monthly behavioural series. Columns after `month_end_balance` are only present when the
 *  underlying frame carries them (app.py filters _SERIES_COLS by availability). */
export interface SeriesPoint {
  month_index: number
  month_date: string
  credits: number
  limit_utilisation: number
  drawing_power_pct?: number
  gst_filing_delay_days: number
  cheque_bounces_outward: number
  dpd: number
  electricity_units: number
  month_end_balance: number
  stock_statement_submitted?: number
  lien_count?: number
  anchor_inflow?: number
}

export interface Pillar {
  pillar: string
  score: number
  risk_contribution: number
  percentile_risk: number
  description: string
  /** False when the pillar has nothing to score on this account (no anchor concentration, no notes). */
  applicable: boolean
}

export interface OfficerNote {
  month_index: number
  month_date: string
  text: string
  sentiment: number
  themes: string[]
  severity: number
}

export interface RecommendedAction {
  action: string
  detail: string
}

export interface ContagionContribution {
  payer: string
  payer_name: string
  added_stress: number
}

/** ContagionGraph.node_result(): present on account detail for anchor suppliers only. */
export interface ContagionNodeResult {
  borrower_id: string
  own_pd: number
  contagion_adjusted_pd: number
  runway_months: number
  contagion_runway_months: number
  runway_delta: number
  why: string | null
  contributions: ContagionContribution[]
}

export interface AccountDetail {
  borrower_id: string
  name: string
  sector: string
  city: string
  state: string
  loan_type: string
  sanctioned_limit: number
  vintage_years: number
  promoter_experience_years: number
  promoter_qualification: string
  pd: number
  pd_prev: number
  pd_delta: number
  bucket: Bucket
  from_bucket: Bucket
  repayment_state: string
  grade: string
  grade_label: string
  grade_score: number
  statutory_sma: string
  dpd: number
  model_implied_sma: string
  recommended_action: RecommendedAction
  runway_months: number
  runway_label: string
  /** S(t) for months 1..24 from the runway (discrete-time hazard) model. */
  survival_curve: number[]
  is_npa: boolean
  exposure: number
  utilisation: number
  drawing_power_pct: number
  reason_codes: ReasonCode[]
  auditor_table: AuditorRow[]
  explainer_backend: string
  pillars: Pillar[]
  ews_indicators: EwsIndicator[]
  review: ReviewState
  coverage: Coverage
  notes: OfficerNote[]
  storyline: string
  beats: Beat[]
  compliance_clocks: ComplianceClock[]
  contagion: ContagionNodeResult | null
  series: SeriesPoint[]
  whatif_actions: string[]
}

/** Bundle.coverage(): how much conduct history the score rests on. */
export interface Coverage {
  months_on_file: number
  /** months_on_file / 24 */
  coverage: number
  confidence: Confidence
  /** Thin-file caveat; empty unless confidence is low. */
  note: string
}

/** GET /api/accounts/{id}/history (Bundle.pd_history()): one point per month the account could be scored. */
export interface PdHistoryPoint {
  month_index: number
  /** YYYY-MM */
  month_date: string
  pd: number
  bucket: Bucket
  dpd: number
  statutory_sma: string
  /** False in the first months, when the feature window is not yet full and the flag is not trusted. */
  full_window: boolean
}

export interface PdHistory {
  borrower_id: string
  points: PdHistoryPoint[]
  first_flag_month: number | null
  first_flag_label: string | null
  first_red_month: number | null
  first_arrears_month: number | null
  first_arrears_label: string | null
  /** Month index of the observed or projected 90+ DPD month; null when the account never defaults. */
  projected_default_month: number | null
  lead_over_arrears_months: number | null
  lead_over_default_months: number | null
}

export interface WhatIf {
  action: string
  label: string
  note: string
  basis: string
  runway_before: number
  runway_after: number
  runway_after_range: [number, number]
  runway_delta: number
  exposure_before: number
  exposure_after: number
  provision_before: number
  provision_after: number
  provision_saved_vs_npa: number
}

/** POST /api/accounts/{id}/notes/score */
export interface NoteScore {
  account_id: string
  text: string
  sentiment: number
  themes: string[]
  severity: number
  scorer: string
  pd_before: number
  pd_after: number
  pd_delta: number
  bucket_before: Bucket
  bucket_after: Bucket
  grade_after: string
}

// ------------------------------------------------------------------ RBI EWS indicators (prahari/backend/ews.py)
export interface EwsIndicator {
  id: string
  indicator: string
  features: string[]
  triggered: boolean
  evidence: string
}

/** GET /api/ews-indicators */
export interface EwsSummary {
  source: string
  indicators: Pick<EwsIndicator, 'id' | 'indicator' | 'features'>[]
}

// ------------------------------------------------------------------ maker-checker reviews (prahari/backend/reviews.py)
export type ReviewAction = 'approve' | 'return' | 'clear' | 'file'
export type ReviewStatus = 'unreviewed' | 'approved' | 'returned' | 'cleared' | 'filed'

export interface ReviewRecord {
  id: string
  account_id: string
  action: ReviewAction
  reviewer: string
  note: string
  document_type: string
  as_of_month: number | null
  /** Wall-clock UTC ISO timestamp: audit data, not generated data. */
  timestamp: string
}

export interface ReviewState {
  status: ReviewStatus
  /** True inside the cooling period after a 'clear'. */
  suppressed: boolean
  last: ReviewRecord | null
  n_reviews?: number
}

export interface ReviewIn {
  action: ReviewAction
  reviewer: string
  note: string
  document_type: string
}

/** POST /api/accounts/{id}/review */
export interface ReviewResp {
  record: ReviewRecord
  state: ReviewState
}

/** GET /api/accounts/{id}/reviews */
export interface AccountReviewsResp {
  account_id: string
  state: ReviewState
  history: ReviewRecord[]
}

/** GET /api/reviews */
export interface ReviewsResp {
  count: number
  reviews: ReviewRecord[]
}

// ------------------------------------------------------------------ contagion graph
export interface AnchorNode {
  id: string
  label: string
  kind: 'anchor'
  sector: string
  n_suppliers: number
  stress: number
  inflow_decline: number | null
  n_suppliers_measured: number
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
  regularity: number
}

export interface ContagionMethod {
  equation: string
  iterations: number
  anchor_stress: string
  elasticity: number
}

export interface ContagionGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
  method: ContagionMethod
}

/** POST /api/contagion/scenario: one anchor's stress overridden, diffusion re-run. */
export interface ScenarioIn {
  anchor_id: string
  /** 0..1; 1.0 means the anchor stops paying. */
  stress: number
}

export interface ScenarioSupplier {
  borrower_id: string
  name: string
  exposure: number
  own_pd: number
  pd_before: number
  pd_after: number
  bucket_before: Bucket
  bucket_after: Bucket
  runway_before: number
  runway_after: number
}

export interface Scenario {
  anchor_id: string
  anchor_name: string
  stress_before: number
  stress_after: number
  n_suppliers: number
  supplier_exposure: number
  n_rebucketed: number
  exposure_rebucketed: number
  provisioning_at_risk_delta: number
  exposure_weighted_pd_before: number
  exposure_weighted_pd_after: number
  expected_loss_proxy_before: number
  expected_loss_proxy_after: number
  red_exposure_before: number
  red_exposure_after: number
  avg_runway_before: number
  avg_runway_after: number
  suppliers: ScenarioSupplier[]
}

// ------------------------------------------------------------------ backtest (Bundle.backtest())
export type LeadBin = '1-3' | '4-6' | '7-9' | '10-12'

/** One scope of the replay: every scorable account, or only borrowers never used to train the model. */
export interface BacktestSummary {
  scope: string
  n_scored: number
  n_flagged: number
  flag_rate: number
  n_realised_defaults: number
  n_caught: number
  n_caught_red: number
  capture: number
  capture_red: number
  precision: number
  median_lead_months: number | null
  mean_lead_months: number | null
  lead_distribution: Record<LeadBin, number>
  caught_exposure: number
  provisioning_actionable: number
  missed_exposure: number
  /** Realised defaulters that already had days past due at the as-of month: what an arrears rule would have shown. */
  arrears_visible_at_as_of: number
}

export interface BacktestRow {
  borrower_id: string
  name: string
  loan_type: string
  sector: string
  /** Calibrated PD at the as-of month. */
  pd: number
  bucket: Bucket
  exposure: number
  /** Months between the as-of month and the 90+ DPD month. */
  months_ahead: number
  dpd_at_as_of: number
  /** Validation fold: A trained the model, B chose the thresholds, C was held out. */
  group: string
}

/** GET /api/backtest */
export interface Backtest {
  as_of: number
  as_of_label: string
  outcome_month: number
  outcome_label: string
  horizon_months: number
  all: BacktestSummary
  unseen: BacktestSummary
  caught: BacktestRow[]
  missed: BacktestRow[]
  note: string
}

// ------------------------------------------------------------------ model card
export type ConfusionMatrix = [[number, number], [number, number]]

/** metrics.confusion_at(): one point on the threshold trade-off curve. */
export interface ThresholdPoint {
  threshold: number
  accuracy: number
  balanced_accuracy: number
  recall: number
  precision: number
  f1: number
  alerts: number
  alert_rate: number
  missed: number
  confusion_matrix: ConfusionMatrix
}

export interface OperatingPoint extends ThresholdPoint {
  key: string
  label: string
}

export interface DecileRow {
  decile: number
  n: number
  defaults: number
  default_rate: number
  lift: number
  cum_capture: number
  min_pd: number
  max_pd: number
  exposure: number
}

export interface LeadTimeRow {
  months_ahead: string
  n: number
  flagged: number | null
}

export interface CalibrationBin {
  bin: string
  n: number
  mean_predicted: number
  observed: number
}

export interface Calibration {
  bins: CalibrationBin[]
  brier: number
  expected_calibration_error: number
}

export interface SegmentRow {
  segment: string
  value: string
  n: number
  defaults: number
  default_rate: number | null
  auc: number | null
  recall: number | null
  precision: number | null
  alert_rate: number | null
}

export interface BaselineRow {
  name: string
  description: string
  auc?: number
  recall: number
  precision: number
  alerts: number
  alert_rate: number
  prahari_recall_at_same_alerts: number
  prahari_precision_at_same_alerts: number
  uplift_x: number | null
}

/** metrics.ablation: the model retrained without the external feeds, held to the same alert budget. */
export interface Ablation {
  external_features_removed: string[]
  n_internal_features: number
  full_model_auc: number
  internal_only_auc: number
  full_model_recall_at_budget: number
  internal_only_recall_at_budget: number
  alert_budget: number
  note: string
}

/** metrics.segment_models: a dedicated challenger per loan type. AUCs are absent when there were too few defaults to fit one. */
export interface SegmentModelRow {
  loan_type: string
  n_train: number
  n_valid: number
  defaults_valid?: number
  global_model_auc?: number
  dedicated_model_auc?: number
  verdict: string
}

export interface AucCI {
  low: number | null
  high: number | null
  n_boot: number
}

export interface ModelMetrics {
  auc: number
  auc_raw: number
  auc_ci95: AucCI
  ks: number
  operating_threshold: number
  accuracy: number
  balanced_accuracy: number
  precision: number
  recall: number
  f1: number
  confusion_matrix: ConfusionMatrix
  alerts: number
  alert_rate: number
  max_capture: ThresholdPoint
  thresholds: Record<string, number>
  operating_points: OperatingPoint[]
  threshold_curve: ThresholdPoint[]
  deciles: DecileRow[]
  lead_time: LeadTimeRow[]
  lead_time_threshold: number
  calibration: Calibration
  calibration_method: string
  segments: SegmentRow[]
  baselines: BaselineRow[]
  /** Same folds, bank-internal columns only: what the external feeds are worth. */
  ablation?: Ablation
  /** One dedicated model per loan type versus the global calibrated model. */
  segment_models?: SegmentModelRow[]
  psi_between_as_ofs: number
  n_train: number
  n_calibration: number
  n_valid: number
  n_borrowers_train: number
  n_borrowers_valid: number
  train_positive_rate: number
  valid_positive_rate: number
  validation: string
  horizon_months: number
  n_features: number
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

/** core/models/survival.py RunwayModel.card(): the runway (time-to-90+DPD) model's own evidence. */
export interface RunwayMetrics {
  concordance_defaulters_fold_C: number | null
  median_abs_error_months_defaulters: number | null
  n_valid: number
  n_defaulters_valid: number
  hazard_model_12m_auc: number | null
  hazard_model_12m_brier: number | null
  agreement_with_pd_model_corr: number | null
  n_person_periods_train: number
  horizon_months: number
  max_runway: number
}

export interface RunwayCalibrationRow {
  band: string
  n: number
  events: number
  predicted_median_months: number
  observed_km_median_months: number
}

export interface RunwayCard {
  method: string
  metrics: RunwayMetrics
  calibration: RunwayCalibrationRow[]
}

export interface ModelCard {
  name: string
  task: string
  algorithm: string
  features: string[]
  pillars: Record<string, string[]>
  metrics: ModelMetrics
  honesty_note: string
  cost_of_error?: CostOfError
  explainer_backend: string
  note_scorer: string
  runway: RunwayCard
}

/** GET /api/value: illustrative bank-scale arithmetic at the bank-90 operating point. default_rate is a fraction. */
export interface ValueInputs {
  book_cr: number
  default_rate: number
  avg_ticket_lakh: number
  review_cost: number
}

export interface ValueOperatingPoint {
  threshold: number | null
  recall: number
  precision: number
  alert_rate: number
}

export interface ValueAtScale {
  inputs: ValueInputs
  operating_point: ValueOperatingPoint
  n_accounts: number
  expected_default_exposure: number
  caught_default_exposure: number
  provisioning_actionable: number
  alerts_per_cycle: number
  review_cost_total: number
  actionable_per_review_rupee: number
  note: string
}

// ------------------------------------------------------------------ agent run + documents
export interface ContagionFlag {
  id: string
  label: string
  own_pd: number
  contagion_adjusted_pd: number
}

export interface MonthlyRun {
  activity_log: string[]
  watchlist: Account[]
  commentary: string
  contagion_flagged: ContagionFlag[]
}

export interface DocResp {
  document_type: string
  account_id: string
  text: string
  llm_provider: string
}

// ------------------------------------------------------------------ interpretation framework
export interface GradeBand {
  grade: string
  label: string
  pd_max: number
  score_max: number
}

export interface StatutorySmaBand {
  label: string
  dpd_min: number
  dpd_max: number
}

export interface FrameworkAction {
  bucket: Bucket
  action: string
  detail: string
}

/** GET /api/framework (core.interpret.framework.summary()). */
export interface Framework {
  version: string
  description: string
  grade_bands: GradeBand[]
  rag: {
    amber_pd: number
    red_pd: number
    rationale?: string
    per_loan_type?: Record<string, { amber_pd?: number; red_pd?: number }>
  }
  model_implied_sma: Record<string, string>
  statutory_sma: StatutorySmaBand[]
  irac_provisioning: { standard: number; restructured_standard: number; sub_standard: number; note?: string }
  crilc: { aggregate_exposure_threshold: number; note?: string }
  runway_colours: { green_min_months: number; amber_min_months: number }
  actions: FrameworkAction[]
  pillars: Record<string, { description: string }>
}

// ------------------------------------------------------------------ data sources
/** Ingest provenance. Synthetic and IDBI-sandbox sources expose different optional keys. */
export interface Provenance {
  source: string
  mode?: string
  seed?: number
  data_dir?: string
  as_of_month?: string
  point_in_time_enforced_at?: string
  base_url?: string
  history_months?: number
  catalogue?: string[]
  external_columns_filled?: Record<string, string[]>
  [key: string]: unknown
}

export interface Feed {
  feed: string
  idbi_apis: string[]
  columns: string[]
  mode: string | null
  status: string
}

export interface DataSources {
  provenance: Provenance
  rows: number
  borrowers: number
  months: [number, number]
  as_of_label: string
  feeds: Feed[]
  note_scorer: string
  llm_provider: string
  coverage_note: string
}

/** POST /api/data-sources/adapter-demo: the IDBI-catalogue adapter run live against the Finacle-shaped mock. */
export interface AdapterSample {
  request: unknown
  response: unknown
}

/** Parity of the adapter's msme_monthly against the book, per demo account: one key per mapped column holding the
 *  maximum absolute difference scaled by the column's magnitude (0 means identical). */
export interface AdapterParityRow {
  borrower_id: string
  name: string
  months: number
  [column: string]: number | string
}

export interface AdapterDemo {
  cif_ids: string[]
  api_calls: number
  seconds: number
  provenance: Provenance
  external_columns_filled: string[]
  /** Keyed api_394, api_391, api_441, api_402, api_404, api_393, api_362. */
  samples: Record<string, AdapterSample>
  parity: AdapterParityRow[]
  note: string
}
