import type { CalibrationLog } from '@/features/motor/api/motor-api'

const WIDTH = 640
const HEIGHT = 120
const PAD = 4

type Series = { values: number[]; color: string; label: string }

function Plot({ t, series, unit, title }: { t: number[]; series: Series[]; unit: string; title: string }) {
  const all = series.flatMap((s) => s.values)
  let lo = Math.min(...all)
  let hi = Math.max(...all)
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1 }
  if (hi - lo < 1e-6) { lo -= 1; hi += 1 }
  const t0 = t[0] ?? 0
  const span = Math.max((t[t.length - 1] ?? 0) - t0, 1e-6)
  const x = (value: number) => PAD + ((value - t0) / span) * (WIDTH - 2 * PAD)
  const y = (value: number) => HEIGHT - PAD - ((value - lo) / (hi - lo)) * (HEIGHT - 2 * PAD)
  const zero = lo < 0 && hi > 0 ? y(0) : null

  return (
    <figure className="space-y-1">
      <figcaption className="flex items-center justify-between text-xs text-white/45">
        <span>{title}</span>
        <span className="flex gap-3">
          {series.map((s) => (
            <span key={s.label} className="flex items-center gap-1">
              <span className="inline-block h-[3px] w-4 rounded-full" style={{ background: s.color }} />
              {s.label} {s.values.length ? `${s.values[s.values.length - 1].toFixed(1)} ${unit}` : ''}
            </span>
          ))}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" className="h-28 w-full rounded-2xl border border-white/8 bg-black/20">
        {zero !== null ? <line x1={0} x2={WIDTH} y1={zero} y2={zero} stroke="rgba(255,255,255,0.12)" strokeDasharray="4 4" /> : null}
        {series.map((s) => (
          <polyline
            key={s.label}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            points={s.values.map((value, index) => `${x(t[index] ?? t0).toFixed(1)},${y(value).toFixed(1)}`).join(' ')}
          />
        ))}
        <text x={WIDTH - PAD} y={12} textAnchor="end" fontSize={10} fill="rgba(255,255,255,0.35)">{hi.toFixed(1)} {unit}</text>
        <text x={WIDTH - PAD} y={HEIGHT - 6} textAnchor="end" fontSize={10} fill="rgba(255,255,255,0.35)">{lo.toFixed(1)} {unit}</text>
      </svg>
    </figure>
  )
}

export function SessionChart({ log }: { log: CalibrationLog }) {
  if (log.t.length < 2) {
    return <p className="rounded-2xl border border-white/8 bg-black/20 p-4 text-sm text-white/40">Данные появятся после старта.</p>
  }
  return (
    <div className="space-y-3" aria-label="График калибровки">
      <Plot t={log.t} unit="мм" title="Положение" series={[
        { values: log.xL, color: '#7fb8ff', label: 'Л' },
        { values: log.xR, color: '#f2a65a', label: 'П' },
      ]} />
      <Plot t={log.t} unit="Н" title="Сила мотора" series={[
        { values: log.fL, color: '#7fb8ff', label: 'Л' },
        { values: log.fR, color: '#f2a65a', label: 'П' },
      ]} />
    </div>
  )
}
