import { createContext, useContext, useMemo } from 'react'
import type { Bucket, Framework } from './types'
import {
  FALLBACK_THRESHOLDS, pdBucket, pdColor as pdColorAt, runwayBucket, runwayColor as runwayColorAt,
  type Thresholds,
} from './components/ui'

/**
 * The interpretation framework (GET /api/framework) loaded once in App.tsx. Every RAG colour
 * for PD and runway is derived from it, so a threshold changed in
 * data/interpretation_framework.json changes every screen without touching the frontend.
 * Until it loads (or if it fails) the shipped defaults in FALLBACK_THRESHOLDS apply.
 */
export const FrameworkContext = createContext<Framework | null>(null)

/** Thresholds for a loan type, honouring rag.per_loan_type overrides when the framework has them. */
export function thresholdsOf(fw: Framework | null, loanType?: string): Thresholds {
  if (!fw) return FALLBACK_THRESHOLDS
  const over = (loanType && fw.rag?.per_loan_type?.[loanType]) || {}
  return {
    amber_pd: over.amber_pd ?? fw.rag?.amber_pd ?? FALLBACK_THRESHOLDS.amber_pd,
    red_pd: over.red_pd ?? fw.rag?.red_pd ?? FALLBACK_THRESHOLDS.red_pd,
    green_min_months: fw.runway_colours?.green_min_months ?? FALLBACK_THRESHOLDS.green_min_months,
    amber_min_months: fw.runway_colours?.amber_min_months ?? FALLBACK_THRESHOLDS.amber_min_months,
  }
}

export interface FrameworkApi {
  framework: Framework | null
  loaded: boolean
  thresholds: Thresholds
  pdColor: (pd: number, loanType?: string) => string
  pdBucket: (pd: number, loanType?: string) => Bucket
  runwayColor: (months: number) => string
  runwayBucket: (months: number) => Bucket
  /** Grade band (PR1..PR7) for a PD, from the framework's grade_bands. */
  gradeOf: (pd: number) => string | null
}

export function useFramework(): FrameworkApi {
  const fw = useContext(FrameworkContext)
  return useMemo<FrameworkApi>(() => {
    const t = thresholdsOf(fw)
    return {
      framework: fw,
      loaded: fw != null,
      thresholds: t,
      pdColor: (pd, loanType) => pdColorAt(pd, thresholdsOf(fw, loanType)),
      pdBucket: (pd, loanType) => pdBucket(pd, thresholdsOf(fw, loanType)),
      runwayColor: (m) => runwayColorAt(m, t),
      runwayBucket: (m) => runwayBucket(m, t),
      gradeOf: (pd) => {
        if (!fw?.grade_bands?.length) return null
        const band = fw.grade_bands.find((b) => pd < b.pd_max) ?? fw.grade_bands[fw.grade_bands.length - 1]
        return band.grade
      },
    }
  }, [fw])
}
