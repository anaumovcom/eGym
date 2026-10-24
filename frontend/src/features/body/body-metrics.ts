export type BodyMeasurement = { id: number; measuredAt: string; weightKg: number | null; bodyFatPercent: number | null; chestCm: number | null; waistCm: number | null; hipsCm: number | null }
export type BodyMetricKey = 'weightKg' | 'bodyFatPercent' | 'waistCm' | 'chestCm' | 'hipsCm'
/** `down`: a decrease is progress for most users; `neutral`: direction depends on the goal. */
export type BodyMetric = { key: BodyMetricKey; label: string; unit: string; field: string; better: 'down' | 'neutral' }
export type BodyPoint = { date: string; value: number; id: number }

export const bodyMetrics: BodyMetric[] = [
  { key: 'weightKg', label: 'Вес', unit: 'кг', field: 'Вес, кг', better: 'neutral' },
  { key: 'bodyFatPercent', label: 'Жир', unit: '%', field: 'Жир, %', better: 'down' },
  { key: 'waistCm', label: 'Талия', unit: 'см', field: 'Талия, см', better: 'down' },
  { key: 'chestCm', label: 'Грудь', unit: 'см', field: 'Грудь, см', better: 'neutral' },
  { key: 'hipsCm', label: 'Бёдра', unit: 'см', field: 'Бёдра, см', better: 'neutral' },
]

const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 })
export const formatBody = (value: number) => numberFormat.format(value)
export const formatSigned = (value: number) => `${value > 0 ? '+' : value < 0 ? '−' : ''}${numberFormat.format(Math.abs(value))}`

/** Chronological points of one metric; empty and zero values are gaps, not measurements. */
export function metricSeries(measurements: BodyMeasurement[], key: BodyMetricKey): BodyPoint[] {
  return measurements
    .filter((item) => item[key] != null && Number(item[key]) > 0)
    .map((item) => ({ date: item.measuredAt, value: Number(item[key]), id: item.id }))
    .sort((a, b) => Date.parse(a.date) - Date.parse(b.date) || a.id - b.id)
}

export function metricSummary(measurements: BodyMeasurement[], key: BodyMetricKey) {
  const series = metricSeries(measurements, key)
  const last = series.at(-1)
  const first = series[0]
  const previous = series.at(-2)
  return {
    series,
    last,
    sinceFirst: last && first && series.length > 1 ? last.value - first.value : null,
    sincePrevious: last && previous ? last.value - previous.value : null,
  }
}

/** The previous non-empty value of a metric before a given measurement (for per-row deltas). */
export function previousValue(measurements: BodyMeasurement[], key: BodyMetricKey, measurement: BodyMeasurement) {
  const series = metricSeries(measurements, key)
  const index = series.findIndex((point) => point.id === measurement.id)
  return index > 0 ? series[index - 1].value : null
}

export function deltaTone(metric: BodyMetric, delta: number | null) {
  if (delta === null || Math.abs(delta) < 0.05) return 'flat'
  if (metric.better === 'neutral') return 'info'
  return delta < 0 ? 'good' : 'bad'
}

export function bodyMassIndex(weightKg: number | null | undefined, heightCm: number | null | undefined) {
  if (!weightKg || !heightCm) return null
  const value = weightKg / (heightCm / 100) ** 2
  const category = value < 18.5 ? 'ниже нормы' : value < 25 ? 'норма' : value < 30 ? 'выше нормы' : 'ожирение'
  return { value: Math.round(value * 10) / 10, category, tone: value >= 18.5 && value < 25 ? 'good' : 'warning' }
}

/** Nearest measured weight to a date (±10 days) — used to annotate progress photos. */
export function weightNear(measurements: BodyMeasurement[], date: string) {
  const target = Date.parse(date)
  let best: BodyPoint | null = null
  for (const point of metricSeries(measurements, 'weightKg')) {
    const distance = Math.abs(Date.parse(point.date) - target)
    if (distance <= 10 * 86_400_000 && (!best || distance < Math.abs(Date.parse(best.date) - target))) best = point
  }
  return best
}

export function daysBetween(from: string, to: string | Date = new Date()) {
  const start = new Date(from)
  const end = typeof to === 'string' ? new Date(to) : to
  return Math.round((new Date(end.getFullYear(), end.getMonth(), end.getDate()).getTime() - new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime()) / 86_400_000)
}
