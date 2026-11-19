import type { PlotStage, Side } from '@/features/motor/api/motor-api'
import { rails } from './friction-track-model'

export type Result = Record<string, unknown>
export type Direction = 'up' | 'down'
export const plotNames: Record<PlotStage, string> = {
  S7: 'Баланс по высоте', D2: 'Трение и скорость', F3: 'Трение и скорость', X3: 'Перекос сторон',
  M5: 'Путь торможения', G4: 'Повторяемость хода',
}
export const isPlotStage = (code: string | null): code is PlotStage => code !== null && Object.hasOwn(plotNames, code)
export const finite = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null
const record = (v: unknown): Result => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Result : {}
const list = (v: unknown): unknown[] => Array.isArray(v) ? v : []
type Precision = 0 | 1 | 2 | 3
const formats = [0, 1, 2, 3].map(maximumFractionDigits => new Intl.NumberFormat('ru-RU', { maximumFractionDigits }))
export const fmt = (v: number | null, digits: Precision = 1) => v === null ? '—' : formats[digits].format(v)
export const withUnit = (v: number | null, unit: string, digits: Precision = 1) => v === null ? 'Нет замера' : fmt(v, digits) + ' ' + unit

export type ForcePoint = { x: number; y: number; low: number | null; high: number | null }
export function forcePoints(code: 'S7' | 'D2' | 'F3', result: Result, side: Side, dir: Direction): ForcePoint[] {
  const channel = record(record(result.sides)[side])
  const source = code === 'S7' ? channel.map : code === 'D2' ? channel['table_' + dir]
    : record(record(result.points)[dir === 'up' ? '1' : '-1'])[side]
  const edges = new Map(list(channel.edges).filter(Array.isArray).map(row => [row[0], row]))
  return list(source).flatMap(item => {
    const [x, y] = list(item).map(finite)
    if (x == null || y == null) return []
    const edge = edges.get(x)
    return [{ x, y, low: finite(edge?.[1]), high: finite(edge?.[2]) }]
  }).sort((a, b) => a.x - b.x)
}

export function syncRuns(result: Result) {
  return list(result.runs).flatMap(item => {
    const run = record(item), k = finite(run.k)
    if (k === null) return []
    return [{ k, up: finite(record(run.up).peak), down: finite(record(run.down).peak), rms: finite(run.rms_mm),
      max: finite(run.max_mm), oscillation: finite(run.oscillation) }]
  })
}

export function brakeRuns(result: Result) {
  return list(result.runs).flatMap(item => {
    const run = record(item)
    if ((run.direction !== 1 && run.direction !== -1) || (run.mode !== 'coast' && run.mode !== 'brake')) return []
    const measured = run.ok === true
    const coast = measured ? finite(run.coast_mm) : null
    const brake = measured ? finite(run.brake_mm) : null
    return [{ dir: run.direction === 1 ? 'up' : 'down', direct: run.mode === 'brake', target: finite(run.target_mm_s),
      failed: run.ok === false, coast, brake, total: coast === null || brake === null ? null : coast + brake,
      startSpeed: measured ? finite(run.v_mm_s) : null, brakeSpeed: measured ? finite(run.brake_v_mm_s) : null,
      time: measured ? finite(run.brake_s) : null }]
  })
}

export function repeatRows(result: Result, dir: Direction) {
  const passes = list(result.passes), limits = record(record(result.spreadLimitsN)[dir])
  return list(result.heightsMm).flatMap((h, i) => {
    const height = finite(h)
    if (height === null) return []
    return rails.map(side => {
      const legs = [0, 1, 2].map(p => passes[2 * p + (dir === 'up' ? 0 : 1)])
      const values = legs.map(pass => finite(list(record(pass)[side])[i]))
      const available = values.filter((v): v is number => v !== null)
      const spread = available.length === 3 ? Math.max(...available) - Math.min(...available) : null
      const limit = finite(list(limits[side])[i])
      return { height, side, values, attempted: legs.map(p => p != null), count: available.length, spread, limit, ok: limit === null || spread === null ? null : spread <= limit }
    })
  })
}

// Rounded tick intervals, including negative and submillimetre measurements.
export function axis(values: number[], count = 5) {
  let lo = Math.min(...values), hi = Math.max(...values)
  if (!values.length) { lo = 0; hi = 1 }
  if (lo === hi) { const pad = Math.max(Math.abs(lo) * 0.04, 0.1); lo -= pad; hi += pad }
  const rough = (hi - lo) / count
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = ([1, 2, 2.5, 5, 10].find(n => n * power >= rough) ?? 10) * power
  const first = Math.floor(lo / step), last = Math.ceil(hi / step)
  const ticks = Array.from({ length: last - first + 1 }, (_, i) => Number(((first + i) * step).toPrecision(12)))
  return { min: ticks[0], max: ticks[ticks.length - 1], ticks }
}
