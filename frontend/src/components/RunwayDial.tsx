import { Gauge } from './Gauge'
import { useTween } from './anim'
import { runwayColor } from './ui'

/**
 * Prominent runway clock. Shows months to projected 90+ DPD, clamped to 24
 * ("24+" green). Animates smoothly when the value changes (what-if simulator).
 */
export function RunwayDial({ runway, size = 230 }: { runway: number; size?: number }) {
  const animated = useTween(Math.min(Math.max(runway, 0), 24), 900)
  const fraction = animated / 24
  const color = runwayColor(animated)
  const shown = animated >= 23.5 ? '24+' : String(Math.round(animated))
  return (
    <Gauge fraction={fraction} color={color} size={size} thickness={20}>
      <div className="text-[52px] leading-none font-bold" style={{ color }}>{shown}</div>
      <div className="text-xs text-muted mt-1 font-medium tracking-wide">MONTHS RUNWAY</div>
    </Gauge>
  )
}
