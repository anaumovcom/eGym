import { useState, type ReactNode } from 'react'
import { useElementWidth } from '@/shared/lib/use-element-width'
import type { ProgressActivityDay, ProgressExerciseSession, ProgressTimelinePoint } from '@/entities/stage4/model/types'
import { formatDay, formatNumber } from './progress-format'

const weekdayLabels = ['Пн', '', 'Ср', '', 'Пт', '', 'Вс']
const monthShort = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

/** Rounds the axis maximum up to 1/2/2.5/5 × 10ⁿ so tick labels stay readable. */
function niceMax(value: number) {
  if (value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find((item) => item * power >= value) ?? 10
  return step * power
}

function ChartTooltip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const flip = x > width - 180
  return <div className="progress-tooltip" role="tooltip" style={{ left: x, top: y, transform: `translate(${flip ? 'calc(-100% - 12px)' : '12px'}, -50%)` }}>{children}</div>
}

export function Sparkline({ values, label }: { values: number[]; label: string }) {
  const max = Math.max(...values, 0)
  if (!values.length || max <= 0) return <div className="progress-spark progress-spark-empty" aria-hidden="true" />
  const gap = values.length > 20 ? 1 : 2
  const barWidth = (100 - gap * (values.length - 1)) / values.length
  return (
    <svg className="progress-spark" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label={label}>
      {values.map((value, index) => {
        const height = value > 0 ? Math.max(3, (value / max) * 32) : 1
        return <rect key={index} x={index * (barWidth + gap)} y={32 - height} width={barWidth} height={height} rx={Math.min(1.5, barWidth / 2)} data-zero={value <= 0 || undefined} />
      })}
    </svg>
  )
}

export function VolumeTimeline({ points, granularity }: { points: ProgressTimelinePoint[]; granularity: 'day' | 'week' | 'month' }) {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const [active, setActive] = useState<number | null>(null)
  const height = 260
  const pad = { top: 16, right: 8, bottom: 30, left: 56 }
  const max = niceMax(Math.max(...points.map((point) => point.volumeKg), 0))
  const plotWidth = Math.max(width - pad.left - pad.right, 0)
  const plotHeight = height - pad.top - pad.bottom
  const slot = points.length ? plotWidth / points.length : 0
  const barWidth = Math.max(2, Math.min(36, slot - Math.max(2, slot * 0.28)))
  const labelEvery = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(plotWidth / 64))))
  const active_ = active === null ? null : points[active]
  const unitLabel = granularity === 'day' ? 'день' : granularity === 'week' ? 'неделя с' : 'месяц'

  function pick(clientX: number) {
    const box = ref.current?.getBoundingClientRect()
    if (!box || !slot) return
    const index = Math.floor((clientX - box.left - pad.left) / slot)
    setActive(index >= 0 && index < points.length ? index : null)
  }

  return (
    <div ref={ref} className="progress-chart" onPointerMove={(event) => pick(event.clientX)} onPointerDown={(event) => pick(event.clientX)} onPointerLeave={() => setActive(null)}>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label={`Объём тренировок: ${points.filter((point) => point.volumeKg > 0).length} активных периодов`}>
          {[0, 0.5, 1].map((tick) => {
            const y = pad.top + plotHeight * (1 - tick)
            return <g key={tick}><line className="progress-chart-grid" x1={pad.left} x2={width - pad.right} y1={y} y2={y} /><text className="progress-chart-axis" x={pad.left - 10} y={y + 4} textAnchor="end">{formatNumber(max * tick)}</text></g>
          })}
          {points.map((point, index) => {
            const x = pad.left + index * slot + (slot - barWidth) / 2
            const barHeight = point.volumeKg > 0 ? Math.max(4, (point.volumeKg / max) * plotHeight) : 0
            return (
              <g key={point.start}>
                {active === index ? <rect className="progress-chart-hover" x={pad.left + index * slot} y={pad.top} width={slot} height={plotHeight} rx={6} /> : null}
                {barHeight ? <path className="progress-chart-bar" data-active={active === index || undefined} d={roundedTopBar(x, pad.top + plotHeight - barHeight, barWidth, barHeight, Math.min(4, barWidth / 2))} /> : point.days ? <circle className="progress-chart-dot" cx={x + barWidth / 2} cy={pad.top + plotHeight - 4} r={3} /> : null}
                {index % labelEvery === 0 ? <text className="progress-chart-axis" x={x + barWidth / 2} y={height - 8} textAnchor="middle">{point.label}</text> : null}
              </g>
            )
          })}
          <line className="progress-chart-baseline" x1={pad.left} x2={width - pad.right} y1={pad.top + plotHeight} y2={pad.top + plotHeight} />
        </svg>
      ) : <div style={{ height }} />}
      {active_ && active !== null ? (
        <ChartTooltip x={pad.left + active * slot + slot / 2} y={pad.top + plotHeight / 2} width={width}>
          <span>{unitLabel} {active_.label}</span>
          <strong>{formatNumber(active_.volumeKg)} кг</strong>
          <small>{active_.sets ? `${active_.sets} подх. · ${active_.days} ${active_.days === 1 ? 'тренировка' : 'трен.'}` : active_.days ? 'Без веса' : 'Нет тренировок'}</small>
        </ChartTooltip>
      ) : null}
    </div>
  )
}

function roundedTopBar(x: number, y: number, w: number, h: number, r: number) {
  const radius = Math.min(r, h)
  return `M${x},${y + h} V${y + radius} Q${x},${y} ${x + radius},${y} H${x + w - radius} Q${x + w},${y} ${x + w},${y + radius} V${y + h} Z`
}

export function ActivityHeatmap({ weeks }: { weeks: ProgressActivityDay[][] }) {
  const [active, setActive] = useState<ProgressActivityDay | null>(null)
  const monthLabels = weeks.map((week, index) => {
    const month = new Date(week[0].date).getMonth()
    const previous = index ? new Date(weeks[index - 1][0].date).getMonth() : -1
    return month !== previous ? monthShort[month] : ''
  })
  return (
    <div className="progress-heatmap" onPointerLeave={() => setActive(null)}>
      <div className="progress-heatmap-grid" style={{ gridTemplateColumns: `1.75rem repeat(${weeks.length}, minmax(0, 1fr))` }}>
        <span />
        {monthLabels.map((label, index) => <span key={index} className="progress-heatmap-month">{label}</span>)}
        {weekdayLabels.map((weekday, row) => (
          <HeatmapRow key={row} label={weekday} days={weeks.map((week) => week[row])} active={active} onActive={setActive} />
        ))}
      </div>
      <div className="progress-heatmap-footer">
        <p aria-live="polite">{active ? <><b>{formatDay(active.date, true)}</b> · {active.future ? 'ещё впереди' : active.sets ? `${active.sets} подх. · ${formatNumber(active.volumeKg)} кг` : 'отдых'}</> : 'Наведите на день, чтобы увидеть нагрузку'}</p>
        <div className="progress-heatmap-legend" aria-hidden="true"><span>меньше</span>{[0, 1, 2, 3, 4].map((level) => <i key={level} data-level={level} />)}<span>больше</span></div>
      </div>
    </div>
  )
}

function HeatmapRow({ label, days, active, onActive }: { label: string; days: ProgressActivityDay[]; active: ProgressActivityDay | null; onActive: (day: ProgressActivityDay) => void }) {
  return (
    <>
      <span className="progress-heatmap-weekday">{label}</span>
      {days.map((day) => (
        <span
          key={day.date}
          className="progress-heatmap-cell"
          data-level={day.level}
          data-future={day.future || undefined}
          data-active={active?.date === day.date || undefined}
          aria-label={`${formatDay(day.date, true)}: ${day.sets ? `${day.sets} подходов` : 'отдых'}`}
          onPointerEnter={() => onActive(day)}
          onPointerDown={() => onActive(day)}
        />
      ))}
    </>
  )
}

export type SessionMetric = 'e1rm' | 'weight' | 'volume' | 'reps'
const metricValue: Record<SessionMetric, (session: ProgressExerciseSession) => number> = {
  e1rm: (session) => session.e1rm ?? 0,
  weight: (session) => session.weightKg,
  volume: (session) => session.volumeKg,
  reps: (session) => session.repsPerSet,
}
const metricTitle: Record<SessionMetric, string> = { e1rm: 'Расчётный максимум', weight: 'Рабочий вес', volume: 'Объём', reps: 'Повторы в подходе' }

export function SessionTrendChart({ sessions, metric, unit }: { sessions: ProgressExerciseSession[]; metric: SessionMetric; unit: string }) {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const [active, setActive] = useState<number | null>(null)
  const values = sessions.map(metricValue[metric])
  const valueUnit = metric === 'reps' ? unit : 'кг'
  const height = 280
  const pad = { top: 24, right: 24, bottom: 30, left: 52 }
  const plotWidth = Math.max(width - pad.left - pad.right, 0)
  const plotHeight = height - pad.top - pad.bottom
  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const spread = Math.max(rawMax - rawMin, rawMax * 0.1, 1)
  const step = niceMax(spread * 0.6)
  const min = Math.max(0, Math.floor((rawMin - spread * 0.2) / step) * step)
  const max = min + step * (min + step * 2 >= rawMax + spread * 0.1 ? 2 : Math.ceil((rawMax + spread * 0.1 - min) / (step * 2)) * 2)
  const xFor = (index: number) => pad.left + (sessions.length === 1 ? plotWidth / 2 : (index / (sessions.length - 1)) * plotWidth)
  const yFor = (value: number) => pad.top + plotHeight - ((value - min) / Math.max(max - min, 1)) * plotHeight
  const line = values.map((value, index) => `${index ? 'L' : 'M'}${xFor(index)},${yFor(value)}`).join(' ')
  const area = `${line} L${xFor(values.length - 1)},${pad.top + plotHeight} L${xFor(0)},${pad.top + plotHeight} Z`
  const labelEvery = Math.max(1, Math.ceil(sessions.length / Math.max(1, Math.floor(plotWidth / 72))))
  const current = active === null ? null : sessions[active]

  function pick(clientX: number) {
    const box = ref.current?.getBoundingClientRect()
    if (!box || !sessions.length) return
    const ratio = (clientX - box.left - pad.left) / Math.max(plotWidth, 1)
    setActive(Math.min(sessions.length - 1, Math.max(0, Math.round(ratio * (sessions.length - 1)))))
  }

  return (
    <div ref={ref} className="progress-chart" onPointerMove={(event) => pick(event.clientX)} onPointerDown={(event) => pick(event.clientX)} onPointerLeave={() => setActive(null)}>
      {width > 0 ? (
        <svg width={width} height={height} role="img" aria-label={`${metricTitle[metric]} по тренировкам`}>
          <defs>
            <linearGradient id="progress-trend-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#d7b15d" stopOpacity=".22" /><stop offset="100%" stopColor="#d7b15d" stopOpacity="0" /></linearGradient>
          </defs>
          {[0, 0.5, 1].map((tick) => {
            const value = min + (max - min) * tick
            const y = yFor(value)
            return <g key={tick}><line className="progress-chart-grid" x1={pad.left} x2={width - pad.right} y1={y} y2={y} /><text className="progress-chart-axis" x={pad.left - 10} y={y + 4} textAnchor="end">{formatNumber(value)}</text></g>
          })}
          {sessions.length > 1 ? <path d={area} fill="url(#progress-trend-fill)" /> : null}
          {sessions.length > 1 ? <path className="progress-chart-line" d={line} /> : null}
          {current && active !== null ? <line className="progress-chart-crosshair" x1={xFor(active)} x2={xFor(active)} y1={pad.top} y2={pad.top + plotHeight} /> : null}
          {sessions.map((session, index) => (
            <g key={`${session.date}-${index}`}>
              {session.isPr ? <circle className="progress-chart-pr-ring" cx={xFor(index)} cy={yFor(values[index])} r={9} /> : null}
              <circle className="progress-chart-point" data-pr={session.isPr || undefined} data-active={active === index || undefined} cx={xFor(index)} cy={yFor(values[index])} r={active === index ? 6 : 4.5} />
              {index % labelEvery === 0 || index === sessions.length - 1 ? <text className="progress-chart-axis" x={xFor(index)} y={height - 8} textAnchor="middle">{formatDay(session.date)}</text> : null}
            </g>
          ))}
        </svg>
      ) : <div style={{ height }} />}
      {current && active !== null ? (
        <ChartTooltip x={xFor(active)} y={yFor(values[active])} width={width}>
          <span>{formatDay(current.date, true)}{current.isPr ? ' · рекорд' : ''}</span>
          <strong>{formatNumber(values[active])} {valueUnit}</strong>
          <small>{current.weightKg > 0 ? `${formatNumber(current.weightKg)} кг × ${current.repsPerSet} × ${current.sets}` : `${current.sets} подх. × ${current.repsPerSet} ${unit}`} · RPE {current.rpe}</small>
        </ChartTooltip>
      ) : null}
    </div>
  )
}
