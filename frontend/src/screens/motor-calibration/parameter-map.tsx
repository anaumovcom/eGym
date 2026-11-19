import { useState } from 'react'
import { formatValue, type CalibrationChange, type ValueInfo } from '@/features/motor/api/motor-api'

type Series = { name: string; info?: ValueInfo | null }
type Point = [number, number]

export function mapAxes(key: string, unit: string) {
  if (key === 'inertia_table') return { x: 'Нагрузка на сторону', xUnit: 'Н', y: 'Компенсация', yUnit: '%', differenceUnit: 'п. п.', factor: 100 }
  const speed = key.startsWith('travel_table_') || key.startsWith('friction_table_')
  const quantity: Record<string, string> = { friction_map: 'Отклонение трения', gravity_map: 'Сила баланса', tight_spots: 'Добавочное усилие',
    friction_table_up: 'Сила трения', friction_table_down: 'Сила трения' }
  return { x: speed ? 'Скорость' : 'Высота', xUnit: speed ? 'мм/с' : 'мм', y: quantity[key] ?? 'Усилие', yUnit: unit, differenceUnit: unit, factor: 1 }
}

function recordedPoints(info?: ValueInfo | null): Point[] | null {
  if (Array.isArray(info?.rows)) return info.rows
  return info?.points === 0 ? [] : null
}

export function mapChangeLabel(change: CalibrationChange): string {
  if (!change.changed) return 'Без изменений'
  const old = recordedPoints(change.old), next = recordedPoints(change.new)
  if (!next) return 'Координаты нового замера недоступны'
  if (!old) return change.old?.points != null || change.old?.value != null || change.old?.runId || change.old?.provenance === 'measured'
    ? 'Для сравнения нужны прежние координаты' : 'Первая карта'
  if (old.length !== next.length) return 'Изменилось число точек'
  // Tight spots may arrive in a different order. Compare coordinates and values together.
  const sort = (points: Point[]) => [...points].sort(([x, y], [u, v]) => x - u || y - v)
  const ordered = sort(next)
  return sort(old).every(([x, y], i) => x === ordered[i][0] && y === ordered[i][1])
    ? 'Карта подтверждена' : 'Изменились точки карты'
}

const fmt = (n: number, unit = '') => formatValue(n, 'float', unit)

function Plot({ paramKey, unit, series }: { paramKey: string; unit: string; series: Series[] }) {
  const axes = mapAxes(paramKey, unit)
  const [picked, setPicked] = useState<number | null>(null)
  const sets = series.map(s => recordedPoints(s.info))
  const points = sets.flatMap(rows => rows ?? [])
  const coordinates = [...new Set(points.map(([x]) => x))].sort((a, b) => a - b)
  if (!coordinates.length) return <p>{sets.every(rows => rows !== null && !rows.length) && paramKey === 'tight_spots'
    ? 'В записанных картах тугих участков не обнаружено.' : 'Для графика нужны записанные координаты точек.'}</p>
  const byCoordinate = sets.map(rows => {
    const values = new Map<number, number[]>()
    for (const [x, y] of rows ?? []) {
      const at = values.get(x)
      if (at) at.push(y * axes.factor)
      else values.set(x, [y * axes.factor])
    }
    return values
  })
  // Compare only unambiguous pairs at exactly the same physical coordinate.
  const common = coordinates.flatMap(x => {
    const [a, b] = byCoordinate.map(values => values.get(x))
    return a?.length === 1 && b?.length === 1 ? [{ x, difference: Math.abs(a[0] - b[0]) }] : []
  })
  const peak = common.reduce<(typeof common)[number] | null>((best, p) => !best || p.difference > best.difference ? p : best, null)
  const index = picked !== null && coordinates.includes(picked) ? coordinates.indexOf(picked) : coordinates.indexOf(peak?.x ?? coordinates[0])
  const selected = coordinates[index]
  const first = coordinates[0], last = coordinates[coordinates.length - 1]
  const ys = points.map(([, y]) => y * axes.factor)
  const lo = Math.min(...ys), hi = Math.max(...ys)
  const xPos = (x: number) => first === last ? 400 : 12 + (x - first) * 776 / (last - first)
  const yPos = (y: number) => hi === lo ? 70 : 126 - (y - lo) * 112 / (hi - lo)
  return <figure className="cal-evidence-plot">
    <figcaption><strong>{axes.y}, {axes.yUnit}</strong>
      <span className="cal-evidence-legend">{series.map((s, i) => <span data-series={i} key={s.name}>{i ? '◇' : '●'} {s.name}</span>)}</span>
    </figcaption>
    <div className="cal-plot-body"><div className="cal-plot-scale"><span>{fmt(hi)}</span><span>{fmt(lo)}</span></div>
      <svg viewBox="0 0 800 140" preserveAspectRatio="none" role="img" aria-label={axes.y + ' по точкам профиля'}>
        <line x1="0" x2="800" y1="126" y2="126" stroke="#425c6c" />
        {lo < 0 && hi > 0 && <g><line x1="0" x2="800" y1={yPos(0)} y2={yPos(0)} stroke="#7e9aab" strokeDasharray="2 5" />
          <text x="1" y={yPos(0) - 2} fill="#c5d9e6" fontSize="9">0</text></g>}
        <line x1={xPos(selected)} x2={xPos(selected)} y1="3" y2="137" stroke="#cad8e1" strokeDasharray="3 4" />
        {sets.map((rows, i) => <g key={series[i].name} data-series={i}>{(rows ?? []).map(([x, y], n) => {
          const px = xPos(x), py = yPos(y * axes.factor)
          return i === 0 ? <circle key={n} cx={px} cy={py} r="3.6" fill="currentColor" />
            : <path key={n} d={`M${px} ${py - 6}l6 6 -6 6 -6 -6z`} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        })}</g>)}
      </svg></div>
    <div className="cal-time-axis"><span>{fmt(first, axes.xUnit)}</span><span>{axes.x}</span><span>{fmt(last, axes.xUnit)}</span></div>
    {coordinates.length > 1 && <input type="range" aria-label="Координата карты" min="0" max={coordinates.length - 1} step="1" value={index}
      aria-valuetext={fmt(selected, axes.xUnit)} onChange={e => setPicked(coordinates[Number(e.target.value)])} />}
    <div className="cal-map-readout"><strong>{axes.x} · {fmt(selected, axes.xUnit)}</strong>{series.map((s, i) => {
      const values = byCoordinate[i].get(selected) ?? []
      return <span key={s.name}>{s.name} · {values.length ? values.map(y => fmt(y, axes.yUnit)).join(' / ')
        : sets[i] === null ? 'нет координат' : 'нет точки'}</span>
    })}</div>
    {series.length === 2 && <p>{peak
      ? `Сопоставлено общих точек · ${common.length}. Наибольшая разница · ${fmt(peak.difference, axes.differenceUnit)} при ${fmt(peak.x, axes.xUnit)}.`
      : 'Общих точек для прямого сравнения нет.'}</p>}
  </figure>
}

export function ParameterMap({ paramKey, unit, label, series }: { paramKey: string; unit: string; label: string; series: Series[] }) {
  const [open, setOpen] = useState(false)
  return <details className="cal-map-compare" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{label}</summary>{open && <Plot paramKey={paramKey} unit={unit} series={series} />}
  </details>
}
