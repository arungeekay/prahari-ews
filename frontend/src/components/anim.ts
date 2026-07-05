import { useEffect, useRef, useState } from 'react'

/** Tween a numeric value toward `target` with an ease-out cubic.
 *  Starts from 0 on mount (so counters/dials visibly animate up), then
 *  tweens from the previous value whenever `target` changes. */
export function useTween(target: number, duration = 800): number {
  const [val, setVal] = useState(0)
  const fromRef = useRef(0)
  useEffect(() => {
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
  }, [target, duration])
  return val
}
