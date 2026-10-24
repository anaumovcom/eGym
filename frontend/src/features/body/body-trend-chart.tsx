import { useId, useState } from 'react'
import { useElementWidth } from '@/shared/lib/use-element-width'
import { formatBody, type BodyPoint } from './body-metrics'

const dayFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' })
const fullFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })

/** Rounds a span to a 1/2/2.5/5 × 10ⁿ step so axis labels stay readable. */
function niceStep(value: number) {
  const power = 10 ** Math.floor(Math.log10(Math.max(value, 0.01)))
  return ([1, 2, 2.5, 5, 10].find((item) => item * power >= value) ?? 10) * power
}

/** Time-scaled line chart: spacing reflects real gaps between measurements. */
export function BodyTrendChart({ points, unit, label, height = 260 }: { points: BodyPoint[]; unit: string; label: string; height?: number }) {
  const [ref, measured] = useElementWidth<HTMLDivElement>()
  // Before layout (and in tests) there is no width yet; draw at a sensible default instead of nothing.
  const width = measured || 640
  const [active, setActive] = useState<number | null>(null)
  const gradient = useId()
  const pad = { top: 18, right: 18, bottom: 30, left: 48 }
  const plotWidth = Math.max(width - pad.left - pad.right, 0)
  const plotHeight = height - pad.top - pad.bottom
  const values = points.map((point) => point.value)
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const step = niceStep(Math.max(rawMax - rawMin, 1) / 2)
  const min = Math.floor((rawMin - step * 0.25) / step) * step
  const max = Math.max(Math.ceil((rawMax + step * 0.25) / step) * step, min + step * 2)
  const ticks = Array.from({ length: Math.round((max - min) / step) + 1 }, (_, index) => min + index * step).filter((_, index, all) => all.length <= 5 || index % 2 === 0)
  const start = Date.parse(points[0]?.date ?? '')
  const span = Math.max(Date.parse(points.at(-1)?.date ?? '') - start, 1)
  const xFor = (index: number) => pad.left + (points.length === 1 ? plotWidth / 2 : ((Date.parse(points[index].date) - start) / span) * plotWidth)
  const yFor = (value: number) => pad.top + plotHeight - ((value - min) / (max - min)) * plotHeight
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${xFor(index)},${yFor(point.value)}`).join(' ')
  // Several weigh-ins can share a day and sit pixels apart: label each day once, at least 80px apart, always keeping the last.
  const labelIndexes: number[] = []
  for (let index = points.length - 1; index >= 0; index--) {
    const previous = labelIndexes.at(-1)
    const sameDay = previous !== undefined && new Date(points[previous].date).toDateString() === new Date(points[index].date).toDateString()
    if (previous === undefined || (!sameDay && xFor(previous) - xFor(index) >= 80)) labelIndexes.push(index)
  }
  const current = active === null ? null : points[active]

  function pick(clientX: number) {
    const box = ref.current?.getBoundingClientRect()
    if (!box || !points.length) return
    const x = clientX - box.left
    let nearest = 0
    for (let index = 1; index < points.length; index++) if (Math.abs(xFor(index) - x) < Math.abs(xFor(nearest) - x)) nearest = index
    setActive(nearest)
  }

  return (
    <div ref={ref} className="body-chart" onPointerMove={(event) => pick(event.clientX)} onPointerDown={(event) => pick(event.clientX)} onPointerLeave={() => setActive(null)}>
      {points.length ? (
        <svg width={width} height={height} role="img" aria-label={label}>
          <title>{`${label}: от ${formatBody(points[0].value)} до ${formatBody(points.at(-1)!.value)} ${unit}, ${points.length} измерений`}</title>
          <defs><linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#d7b15d" stopOpacity=".2" /><stop offset="100%" stopColor="#d7b15d" stopOpacity="0" /></linearGradient></defs>
          {ticks.map((tick) => <g key={tick}><line className="body-chart-grid" x1={pad.left} x2={width - pad.right} y1={yFor(tick)} y2={yFor(tick)} /><text className="body-chart-axis" x={pad.left - 10} y={yFor(tick) + 4} textAnchor="end">{formatBody(tick)}</text></g>)}
          {points.length > 1 ? <path d={`${line} L${xFor(points.length - 1)},${pad.top + plotHeight} L${xFor(0)},${pad.top + plotHeight} Z`} fill={`url(#${gradient})`} /> : null}
          {points.length > 1 ? <path className="body-chart-line" d={line} /> : null}
          {current && active !== null ? <line className="body-chart-crosshair" x1={xFor(active)} x2={xFor(active)} y1={pad.top} y2={pad.top + plotHeight} /> : null}
          {points.map((point, index) => <circle key={point.id} className="body-chart-point" data-active={active === index || undefined} data-last={index === points.length - 1 || undefined} cx={xFor(index)} cy={yFor(point.value)} r={active === index ? 6 : points.length > 40 ? 2.5 : 4} />)}
          {labelIndexes.map((index) => <text key={index} className="body-chart-axis" x={xFor(index)} y={height - 8} textAnchor={points.length > 1 && xFor(index) - pad.left < 30 ? 'start' : points.length > 1 && width - pad.right - xFor(index) < 30 ? 'end' : 'middle'}>{dayFormat.format(new Date(points[index].date)).replace('.', '')}</text>)}
        </svg>
      ) : <div style={{ height }} />}
      {current && active !== null ? (
        <div className="body-tooltip" role="tooltip" style={{ left: xFor(active), top: yFor(current.value), transform: `translate(${xFor(active) > width - 190 ? 'calc(-100% - 12px)' : '12px'}, -50%)` }}>
          <span>{fullFormat.format(new Date(current.date))}</span>
          <strong>{formatBody(current.value)} {unit}</strong>
          {active > 0 ? <small>{(() => { const delta = current.value - points[active - 1].value; return `${delta > 0 ? '+' : delta < 0 ? '−' : '±'}${formatBody(Math.abs(delta))} ${unit} к прошлому` })()}</small> : <small>первое измерение</small>}
        </div>
      ) : null}
    </div>
  )
}

/** Decorative trend line: the card around it already states the value and the change in text. */
export function BodySparkline({ points }: { points: BodyPoint[] }) {
  if (points.length < 2) return <div className="body-spark body-spark-empty" aria-hidden="true" />
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const range = Math.max(Math.max(...values) - min, 0.5)
  const path = values.map((value, index) => `${index ? 'L' : 'M'}${(index / (values.length - 1)) * 100},${28 - ((value - min) / range) * 24}`).join(' ')
  return <svg className="body-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><path d={path} vectorEffect="non-scaling-stroke" /></svg>
}
