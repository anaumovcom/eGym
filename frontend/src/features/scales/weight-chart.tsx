import { useId } from 'react'
import type { ScaleMeasurement } from './api'

const weight = (value: number) => value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })

/** Time-scaled chart; precise individual values remain accessible in the history. */
export function WeightChart({ measurements }: { measurements: ScaleMeasurement[] }) {
  const gradient = useId()
  const values = measurements.map(item => item.weightKg)
  const min = Math.min(...values) - 0.5
  const max = Math.max(...values) + 0.5
  const first = measurements[0]
  const last = measurements[measurements.length - 1]
  const start = Date.parse(first.timestamp)
  const span = Math.max(Date.parse(last.timestamp) - start, 1)
  const points = measurements.map(item => ({
    x: measurements.length === 1 ? 320 : 56 + (Date.parse(item.timestamp) - start) / span * 548,
    y: 168 - (item.weightKg - min) / (max - min) * 140,
    item,
  }))
  const line = points.map(point => `${point.x},${point.y}`).join(' ')

  return <div className="rounded-[28px] border border-white/10 bg-[#111419] p-5 sm:p-6">
    <svg viewBox="0 0 640 200" className="h-auto max-h-72 w-full" role="img" aria-label="Динамика веса тела">
      <title>Вес от {weight(first.weightKg)} до {weight(last.weightKg)} кг · {measurements.length} измерений</title>
      <defs><linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#d6b05f" stopOpacity="0.24" /><stop offset="100%" stopColor="#d6b05f" stopOpacity="0" /></linearGradient></defs>
      {[0, 0.5, 1].map(ratio => <g key={ratio}><line x1="56" x2="612" y1={168 - ratio * 140} y2={168 - ratio * 140} stroke="#ffffff12" /><text x="0" y={172 - ratio * 140} fill="#ffffff80" fontSize="12">{weight(min + ratio * (max - min))}</text></g>)}
      <polygon points={`${points[0].x},184 ${line} ${points[points.length - 1].x},184`} fill={`url(#${gradient})`} />
      <polyline points={line} fill="none" stroke="#d6b05f" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
      {points.map(({ x, y, item }) => <circle key={item.id} cx={x} cy={y} r="4" fill="#f1d391"><title>{weight(item.weightKg)} кг · {new Date(item.timestamp).toLocaleString('ru-RU')}</title></circle>)}
    </svg>
    <div className="flex justify-between gap-4 text-xs text-white/50"><span>{new Date(first.timestamp).toLocaleDateString('ru-RU')}</span><span>{new Date(last.timestamp).toLocaleDateString('ru-RU')}</span></div>
  </div>
}