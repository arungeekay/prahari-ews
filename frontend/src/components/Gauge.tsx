import type { ReactNode } from 'react'

/**
 * 270-degree arc gauge (SVG). `fraction` is 0..1; the arc fills from the
 * lower-left around the top to the lower-right, leaving a gap at the bottom.
 */
export function Gauge({
  fraction, color, size = 220, thickness = 18, track = '#EDF1F8', children,
}: {
  fraction: number
  color: string
  size?: number
  thickness?: number
  track?: string
  children?: ReactNode
}) {
  const cx = size / 2
  const cy = size / 2
  const r = (size - thickness) / 2
  const C = 2 * Math.PI * r
  const ARC = 0.75 // 270deg
  const f = Math.max(0, Math.min(1, fraction))
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="block">
        <g transform={`rotate(135 ${cx} ${cy})`}>
          <circle
            cx={cx} cy={cy} r={r} fill="none" stroke={track} strokeWidth={thickness}
            strokeDasharray={`${ARC * C} ${C}`} strokeLinecap="round"
          />
          <circle
            cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth={thickness}
            strokeDasharray={`${f * ARC * C} ${C}`} strokeLinecap="round"
          />
        </g>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        {children}
      </div>
    </div>
  )
}
