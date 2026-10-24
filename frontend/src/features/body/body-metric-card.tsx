import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { BodySparkline } from './body-trend-chart'
import { deltaTone, formatBody, formatSigned, metricSummary, type BodyMeasurement, type BodyMetric } from './body-metrics'
import './body.css'

const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' })

export function DeltaChip({ metric, delta, suffix }: { metric: BodyMetric; delta: number | null; suffix?: string }) {
  if (delta === null) return null
  const tone = deltaTone(metric, delta)
  const Icon = tone === 'flat' ? Minus : delta > 0 ? TrendingUp : TrendingDown
  return <span className="body-delta" data-tone={tone}><Icon aria-hidden="true" />{formatSigned(Math.round(delta * 10) / 10)} {metric.unit}{suffix ? <small>{suffix}</small> : null}</span>
}

/** One body metric: latest value, change since the first record and a trend line. */
export function BodyMetricCard({ metric, measurements, selected, onSelect }: { metric: BodyMetric; measurements: BodyMeasurement[]; selected?: boolean; onSelect?: () => void }) {
  const summary = metricSummary(measurements, metric.key)
  const body = (
    <>
      <span className="body-card-label">{metric.label}</span>
      <strong className="body-card-value">{summary.last ? <>{formatBody(summary.last.value)}<small> {metric.unit}</small></> : '—'}</strong>
      <span className="body-card-meta">
        {summary.last ? <>{summary.sinceFirst !== null ? <DeltaChip metric={metric} delta={summary.sinceFirst} /> : <span className="body-card-hint">одно измерение</span>}<span className="body-card-hint">{dateFormat.format(new Date(summary.last.date)).replace('.', '')}</span></> : <span className="body-card-hint">нет данных</span>}
      </span>
      <BodySparkline points={summary.series} />
    </>
  )
  return onSelect
    ? <button type="button" className="body-card" aria-pressed={selected} onClick={onSelect} data-empty={!summary.last || undefined}>{body}</button>
    : <article className="body-card" data-empty={!summary.last || undefined}>{body}</article>
}
