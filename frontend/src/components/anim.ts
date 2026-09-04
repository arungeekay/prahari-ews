import { useEffect, useRef, useState } from 'react'

/** Static mode: no animation, values render at their final state immediately.
 *  Enabled by `?static=1` in the URL (headless screenshots, printing) or by the user's
 *  reduced-motion preference. */
export function isStatic(): boolean {
  try {
    if (typeof window === 'undefined') return false
    if (window.location.search.includes('static=1')) return true
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
  } catch {
    return false
  }
}

/** Tween a numeric value toward `target` with an ease-out cubic.
 *  Starts from 0 on mount (so counters/dials visibly animate up), then
 *  tweens from the previous value whenever `target` changes. In static mode
 *  it returns the target directly. */
export function useTween(target: number, duration = 800): number {
  const staticMode = isStatic()
  const [val, setVal] = useState(staticMode ? target : 0)
  const fromRef = useRef(staticMode ? target : 0)
  useEffect(() => {
    if (staticMode) {
      fromRef.current = target
      setVal(target)
      return
    }
    const from = fromRef.current
    if (from === target) return
    const start = performance.now()
    let raf = 0
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setVal(from + (target - from) * eased)
      if (p < 1) {
        raf = requestAnimationFrame(step)
      } else {
        fromRef.current = target
      }
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, staticMode])
  return val
}
