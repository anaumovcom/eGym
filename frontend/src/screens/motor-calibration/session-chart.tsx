import { memo, useState } from 'react'
import type { CalibrationLog, WorkingWindow } from '@/features/motor/api/motor-api'
import { railColor } from './friction-track-model'

const METRICS = {
  height: { label: 'Высота', unit: 'мм' },
  speed: { label: 'Скорость', unit: 'м/с' },
  force: { label: 'Усилие приводов', unit: 'Н' },
  skew: { label: 'Перекос', unit: 'мм' },
  holdError: { label: 'Отклонение от фиксации', unit: 'мм' },
  cycle: { label: 'Цикл шины', unit: 'мс' },
  load: { label: 'Нагрузка', unit: 'кг' },
}
type Metric = keyof typeof METRICS
type Signal = { name: string; points: (number | null)[]; color: string; dashed?: boolean }
const blue = '#6fc9ff'
const amber = '#ffc478'
const fmt = (value: number, places = 1) => value.toLocaleString('ru-RU', { maximumFractionDigits: places })

function focusMetric(code: string): Metric {
  if (code === 'B0' || code === 'B1') return 'cycle'
  if (['B2', 'D1', 'M1', 'S5', 'N1'].includes(code)) return 'force'
  if (['B6', 'B7', 'B8', 'C1', 'H1', 'H2', 'H3', 'M4', 'P1', 'P2', 'V3'].includes(code)) return 'height'
  if (['EXERCISE', 'M2', 'C3', 'E1', 'R1', 'F4', 'F5', 'F6', 'F7', 'F10', 'W2', 'V1', 'V2'].includes(code)) return 'speed'
  if (code.startsWith('X')) return 'skew'
  if (/^(S|L|N|H|W|F|G)/.test(code) && code !== 'WIZARD') return 'force'
  if (/^(V|D|A|P)/.test(code) || ['M3', 'M5', 'M6'].includes(code)) return 'speed'
  return 'height'
}

function signals(log: CalibrationLog, metric: Metric): Signal[] {
  if (metric === 'load') return [{ name: 'Задано', points: log.targetKg ?? [], color: amber, dashed: true }, { name: 'Включено контроллером', points: log.loadKg ?? [], color: blue }]
  if (metric === 'skew') return [{ name: 'Левая минус правая', points: log.skewMm ?? log.xL.map((x, i) => x - log.xR[i]), color: blue }]
  if (metric === 'holdError') {
    const offsets = (xs: number[]) => xs.map((x, i) => { const target = log.holdTargetMm?.[i]; return target == null ? null : x - target })
    return [{ name: 'Левая', points: offsets(log.xL), color: railColor.left }, { name: 'Правая', points: offsets(log.xR), color: railColor.right, dashed: true }]
  }
  if (metric === 'cycle') return [{ name: 'Период', points: log.cycleMs ?? [], color: blue }]
  const [left, right] = metric === 'height' ? [log.xL, log.xR] : metric === 'force' ? [log.fL, log.fR]
    : [log.vL.map(v => v / 1000), log.vR.map(v => v / 1000)]
  return [{ name: 'Левая', points: left, color: railColor.left }, { name: 'Правая', points: right, color: railColor.right, dashed: true }]
}

export const SessionChart = memo(function SessionChart({ log: source, code = '', zone }: {
  log: CalibrationLog; code?: string; zone?: WorkingWindow | null
}) {
  const [picked, setPicked] = useState<{ code: string; metric: Metric } | null>(null)
  const [cursor, setCursor] = useState<{ code: string; time: number } | null>(null)
  const selectedTime = cursor?.code === code ? cursor.time : null
  const preferred = picked?.code === code ? picked.metric : code === 'H3' && source.holdTargetMm ? 'holdError' : focusMetric(code)
  const metric = (preferred === 'cycle' && !source.cycleMs) || (preferred === 'holdError' && !source.holdTargetMm) ? 'height' : preferred
  let log = source
  if (metric === 'holdError' && source.holdTargetMm) {
    const active = source.holdTargetMm.flatMap((target, i) => target === null ? [] : [i])
    if (active.length) {
      log = Object.fromEntries(Object.entries(source).map(([key, column]) => [key, column.slice(active[0], active.at(-1)! + 1)])) as CalibrationLog
    }
  }
  const { label, unit } = METRICS[metric]
  const series = signals(log, metric)
  const values = series.flatMap(s => s.points).filter((v): v is number => v !== null && Number.isFinite(v))
  const band = metric === 'height' ? zone : null
  const min = Math.min(...values, ...(band ? [band.lowMm] : []), ...(metric === 'holdError' ? [-6] : []))
  const max = Math.max(...values, ...(band ? [band.highMm] : []), ...(metric === 'holdError' ? [6] : []))
  const margin = Math.max((max - min) * 0.08, metric === 'speed' ? 0.002 : 0.1)
  const from = log.t[0] ?? 0
  const until = log.t.at(-1) ?? from
  const sample = selectedTime === null ? log.t.length - 1 : log.t.reduce((closest, t, i) =>
    Math.abs(t - selectedTime) < Math.abs(log.t[closest] - selectedTime) ? i : closest, 0)
  const x = (i: number) => 3 + 794 * (log.t[i] - from) / Math.max(until - from, 0.001)
  const y = (value: number) => 134 - 128 * (value - min + margin) / (max - min + 2 * margin)
  const places = metric === 'speed' ? 3 : 1

  return (
    <section className="cal-plot" aria-label={code === 'EXERCISE' ? 'График подхода' : 'График калибровки'}>
      <div className="cal-plot-tools" role="group" aria-label="Сигнал на графике">
        {(Object.keys(METRICS) as Metric[]).filter(id => (id !== 'cycle' || log.cycleMs) && (id !== 'load' || log.targetKg) && (id !== 'holdError' || log.holdTargetMm)).map(id => (
          <button type="button" key={id} aria-pressed={metric === id} onClick={() => setPicked({ code, metric: id })}>{METRICS[id].label}</button>
        ))}
      </div>
      {values.length ? (
        <figure>
          <figcaption>
            <strong>{label}, {unit}</strong>
            <span className="cal-plot-legend">{series.map(s => (
              <span key={s.name} style={{ color: s.color }}>{s.name} <b>{s.points[sample] == null ? '—' : fmt(s.points[sample], places)}</b></span>
            ))}</span>
          </figcaption>
          <div className="cal-plot-body">
            <div className="cal-plot-scale"><span>{fmt(max + margin, places)}</span><span>{fmt(min - margin, places)}</span></div>
            <svg viewBox="0 0 800 140" preserveAspectRatio="none" role="img" aria-label={`${label} во времени, от ${fmt(from)} до ${fmt(until)} секунд`}>
              {[6, 38, 70, 102, 134].map(row => <line key={row} x1="0" x2="800" y1={row} y2={row} stroke="#233d4c" strokeDasharray="3 5" />)}
              {band ? <rect x="0" y={y(band.highMm)} width="800" height={y(band.lowMm) - y(band.highMm)} fill="#69cdad" opacity=".13" /> : null}
              {metric === 'holdError' && <rect x="0" y={y(6)} width="800" height={y(-6) - y(6)} fill="#69cdad" opacity=".16" />}
              {min < 0 && max > 0 && <line x1="0" x2="800" y1={y(0)} y2={y(0)} stroke="#8b9aa5" strokeDasharray="2 4" />}
              {selectedTime !== null && <line x1={x(sample)} x2={x(sample)} y1="0" y2="140" stroke="#ccdce6" strokeDasharray="3 3" />}
              {series.map(s => {
                const path = s.points.map((v, i) => {
                  if (v === null || !Number.isFinite(v)) return ''
                  const start = !i || s.points[i - 1] == null || log.segment?.[i] !== log.segment?.[i - 1]
                  return `${start ? 'M' : 'L'}${x(i).toFixed(2)},${y(v).toFixed(2)}`
                }).join(' ')
                const value = s.points[sample]
                return <g key={s.name}>
                  <path d={path} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? '6 3' : undefined} vectorEffect="non-scaling-stroke" />
                  {value != null ? <circle cx={x(sample)} cy={y(value)} r="3" fill={s.color} /> : null}
                </g>
              })}
            </svg>
          </div>
          <div className="cal-time-axis"><span>{fmt(from)} с</span><span>{code === 'EXERCISE' ? 'Время от начала подхода' : 'Время от начала записи'}</span><span>{fmt(until)} с</span></div>
          {log.t.length > 1 && <div className="cal-plot-cursor">
            <label>Кадр · {fmt(log.t[sample], 2)} с
              <input type="range" aria-label="Момент записи" min={0} max={log.t.length - 1} value={sample}
                aria-valuetext={`${fmt(log.t[sample], 2)} с`} onChange={event => setCursor({ code, time: log.t[Number(event.target.value)] })} />
            </label>
            {selectedTime !== null && <button type="button" className="cal-link" onClick={() => setCursor(null)}>К последнему кадру</button>}
          </div>}
          {band ? <p>Выделен участок измерения {fmt(band.lowMm)}–{fmt(band.highMm)} мм</p> : null}
          {metric === 'force' ? <p>Усилие рассчитано по обратной связи момента PA_1C4.</p> : null}
          {metric === 'speed' && <p>Выше нуля — подъём, ниже — спуск. Переход через ноль показывает смену направления.</p>}
          {metric === 'skew' && <p>Выше нуля левая каретка выше правой, ниже нуля — правая выше левой. {log.skewMm ? 'Позиции совмещены по времени опроса.' : 'Архивная запись показывает разницу исходных показаний.'}</p>}
          {metric === 'holdError' && <p>Ноль — заданная высота. Зелёная полоса ±6 мм показывает допуск после снятия пробного усилия. Линии видны во время фиксации.</p>}
          {metric === 'cycle' && <p>Время между последовательными кадрами обеих сторон. Чем выше линия, тем дольше длился обмен.</p>}
          {metric === 'load' && <p>Заданная нагрузка и нагрузка, которую контроллер включил с учётом плавного набора.</p>}
        </figure>
      ) : <p className="cal-empty">{log.t.length ? 'Для этого сигнала нужен следующий кадр.' : 'Ожидание первого кадра телеметрии.'}</p>}
    </section>
  )
})
