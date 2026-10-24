import { ChevronRight, Plus, Ruler, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/shared/ui/button'
import { BodyMetricCard } from './body-metric-card'
import { bodyMetrics, deltaTone, formatBody, formatSigned, metricSeries, previousValue, type BodyMeasurement, type BodyMetricKey } from './body-metrics'
import { BodyTrendChart } from './body-trend-chart'
import { DeleteMeasurementDialog, MeasurementDialog } from './measurement-dialogs'
import './body.css'

const rowDate = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
const rowTime = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' })

/**
 * Body measurements: metric cards double as a chart switch.
 * `full` adds the editable history table; `summary` links to it instead.
 */
export function BodyMeasurementsView({ userId, measurements, metrics = bodyMetrics.map((metric) => metric.key), mode = 'full', title = 'Измерения тела', description }: {
  userId: string
  measurements: BodyMeasurement[]
  metrics?: BodyMetricKey[]
  mode?: 'full' | 'summary'
  title?: string
  description?: string
}) {
  const shownMetrics = bodyMetrics.filter((metric) => metrics.includes(metric.key))
  const firstWithData = shownMetrics.find((metric) => metricSeries(measurements, metric.key).length > 1) ?? shownMetrics.find((metric) => metricSeries(measurements, metric.key).length) ?? shownMetrics[0]
  const [selectedKey, setSelectedKey] = useState<BodyMetricKey>(firstWithData.key)
  const [adding, setAdding] = useState(false)
  const [deleting, setDeleting] = useState<BodyMeasurement | null>(null)
  const [showAll, setShowAll] = useState(false)
  const selected = shownMetrics.find((metric) => metric.key === selectedKey) ?? firstWithData
  const series = metricSeries(measurements, selected.key)
  const rows = [...measurements].sort((a, b) => Date.parse(b.measuredAt) - Date.parse(a.measuredAt) || b.id - a.id)
  const visibleRows = showAll ? rows : rows.slice(0, 12)
  const tableMetrics = shownMetrics.filter((metric) => metricSeries(measurements, metric.key).length > 0)

  return (
    <section className="body-view" aria-label={title}>
      <header className="body-view-head">
        <div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>
        <Button iconLeft={<Plus aria-hidden="true" />} onClick={() => setAdding(true)}>Добавить измерение</Button>
      </header>
      {measurements.length ? (
        <>
          <div className="body-cards" role="group" aria-label="Показатель на графике">
            {shownMetrics.map((metric) => <BodyMetricCard key={metric.key} metric={metric} measurements={measurements} selected={metric.key === selected.key} onSelect={() => setSelectedKey(metric.key)} />)}
          </div>
          <article className="body-panel">
            <header><div><h3>{selected.label}</h3><p>{series.length ? `${series.length} ${series.length === 1 ? 'измерение' : series.length < 5 ? 'измерения' : 'измерений'} · с ${rowDate.format(new Date(series[0].date))}` : 'Нет измерений'}</p></div></header>
            {series.length ? <BodyTrendChart points={series} unit={selected.unit} label={`Динамика: ${selected.label}`} /> : <p className="body-muted">Добавьте измерение «{selected.label.toLowerCase()}», чтобы увидеть динамику.</p>}
          </article>
          {mode === 'full' ? (
            <article className="body-panel">
              <header><div><h3>История измерений</h3><p>Изменение указано относительно предыдущего замера того же показателя</p></div></header>
              <div className="body-table-wrap">
                <table className="body-table">
                  <thead><tr><th>Дата</th>{tableMetrics.map((metric) => <th key={metric.key}>{metric.label}</th>)}<th><span className="sr-only">Действия</span></th></tr></thead>
                  <tbody>
                    {visibleRows.map((row) => (
                      <tr key={row.id}>
                        <td><b>{rowDate.format(new Date(row.measuredAt))}</b><small>{rowTime.format(new Date(row.measuredAt))}</small></td>
                        {tableMetrics.map((metric) => {
                          const value = row[metric.key] != null && Number(row[metric.key]) > 0 ? Number(row[metric.key]) : null
                          const before = value === null ? null : previousValue(measurements, metric.key, row)
                          const change = value !== null && before !== null ? value - before : null
                          return <td key={metric.key}>{value === null ? <span className="body-empty-cell">·</span> : <><b>{formatBody(value)} <small>{metric.unit}</small></b>{change !== null && Math.abs(change) >= 0.05 ? <small className="body-cell-delta" data-tone={deltaTone(metric, change)}>{formatSigned(Math.round(change * 10) / 10)}</small> : null}</>}</td>
                        })}
                        <td><button type="button" className="body-row-delete" aria-label={`Удалить измерение от ${rowDate.format(new Date(row.measuredAt))}`} onClick={() => setDeleting(row)}><Trash2 aria-hidden="true" /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {rows.length > 12 ? <button type="button" className="body-more" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Свернуть' : `Показать все ${rows.length}`}</button> : null}
            </article>
          ) : <Link className="body-link" to="/profile?tab=measurements">Вся история и редактирование измерений<ChevronRight aria-hidden="true" /></Link>}
        </>
      ) : (
        <div className="body-empty"><span><Ruler aria-hidden="true" /></span><h3>Измерений пока нет</h3><p>Записывайте вес и объёмы раз в 1–2 недели в одно и то же время — так изменения будут честными.</p><Button onClick={() => setAdding(true)}>Добавить первое измерение</Button></div>
      )}
      <MeasurementDialog open={adding} onOpenChange={setAdding} userId={userId} measurements={measurements} />
      <DeleteMeasurementDialog measurement={deleting} onClose={() => setDeleting(null)} userId={userId} />
    </section>
  )
}
