import { useInfiniteQuery } from '@tanstack/react-query'
import { ArrowRight, ChartNoAxesCombined, Gauge, ListRestart, Scale, SlidersHorizontal, Waypoints } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motorApi, type FrictionSource, type PlotStage } from '@/features/motor/api/motor-api'
import { archiveLabel, archiveSources } from './archive-labels'
import { PriorityTag } from './calibration-priority'
import { isPlotStage, plotNames } from './measurement-model'
import { MeasurementPlot } from './measurement-plot'

const views = [
  { code: 'S7', icon: Scale, caption: 'Трогание и поддержка', color: '#70d8c5' },
  { code: 'D2', icon: Gauge, caption: 'Подъём и спуск', color: '#72cce9' },
  { code: 'X3', icon: SlidersHorizontal, caption: 'Выравнивание кареток', color: '#b9a3f7' },
  { code: 'M5', icon: Waypoints, caption: 'Поддержка и торможение', color: '#efbb79' },
  { code: 'G4', icon: ListRestart, caption: 'Три прохода', color: '#a4d991' },
] as const
const scenario: Record<PlotStage, string> = { S7: 'motion', D2: 'motion', F3: 'motion', X3: 'protection', M5: 'speed', G4: 'smith' }

export function MeasurementArchiveTab({ activeAdapter }: { activeAdapter?: string }) {
  const [url, setUrl] = useSearchParams()
  const requested = url.get('plot'), code = isPlotStage(requested) ? requested : 'S7'
  const requestedSource = url.get('source')
  const source = requestedSource && Object.hasOwn(archiveSources, requestedSource) ? requestedSource as FrictionSource : undefined
  const [selected, setSelected] = useState('')
  const archive = useInfiniteQuery({
    queryKey: ['motor', 'runs', 'measurement-plots', code, source ?? activeAdapter ?? 'current'],
    initialPageParam: 0, queryFn: ({ pageParam }) => motorApi.measurementPlots(code, pageParam, source),
    getNextPageParam: (last, pages) => last.hasMore ? pages.reduce((count, page) => count + page.items.length, 0) : undefined,
  })
  const records = archive.data?.pages.flatMap(p => p.items) ?? []
  const current = records.find(r => r.id === selected) ?? records[0]
  const page = archive.data?.pages[0]
  const shownSource = source ?? page?.source
  const change = (key: 'source' | 'plot', value: string) => {
    const next = new URLSearchParams(url)
    next.set(key, value)
    setUrl(next)
    setSelected('')
  }
  return <section className="cal-surface mp-archive" aria-label="Графики замеров">
    <header className="bs-archive-heading"><div className="bs-heading-icon"><ChartNoAxesCombined size={27} aria-hidden="true" /></div>
      <div><h2>Графики замеров</h2><p>Сравните усилия кареток, перекос и тормозной путь по записям калибровок.</p></div>
      <div className="mp-launch">{page?.priority && <PriorityTag level={page.priority} reason={page.priorityReason} />}
        <Link className="bs-scan-link" to={'?tab=calibrations&scenario=' + scenario[code] + '&code=' + code}>Открыть замер {code} <ArrowRight size={17} aria-hidden="true" /></Link></div></header>
    <div className="mp-views" role="group" aria-label="Что проверить">{views.map(({ code: stage, icon: Icon, caption, color }) =>
      <button key={stage} type="button" aria-pressed={code === stage || (code === 'F3' && stage === 'D2')} onClick={() => change('plot', stage)}>
        <Icon aria-hidden="true" style={{ color }} size={24} /><span><strong>{plotNames[stage]}</strong><small>{caption}</small></span>
        <em>{stage === 'D2' ? 'D2 / F3' : stage}</em></button>)}</div>
    <div className="bs-filters mp-filters">
      <label>Источник<select aria-label="Источник" value={shownSource ?? ''} onChange={e => change('source', e.target.value)}>
        {!shownSource && <option value="">Текущий режим тренажёра</option>}
        {Object.entries(archiveSources).map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select></label>
      {(code === 'D2' || code === 'F3') && <label>Процедура<select aria-label="Процедура" value={code} onChange={e => change('plot', e.target.value)}>
        <option value="D2">D2 · Трение в движении</option><option value="F3">F3 · Скорости упражнения</option></select></label>}
      {current && <label>Запуск калибровки<select aria-label="Запуск калибровки" value={current.id} onChange={e => setSelected(e.target.value)}>
        {records.map(r => <option value={r.id} key={r.id}>{archiveLabel(r)}</option>)}</select></label>}
      {archive.hasNextPage && <button type="button" className="cal-link" disabled={archive.isFetchingNextPage} onClick={() => void archive.fetchNextPage()}>Более ранние запуски</button>}
    </div>
    {archive.isError && <p role="alert">Не удалось получить записи. <button type="button" className="cal-link" onClick={() => void archive.refetch()}>Повторить</button></p>}
    {current ? <>
      <div className="bs-scan-meta"><strong>{code} · {plotNames[code]}</strong>
        {current.workingZone && <span>Средняя зона {current.workingZone.lowMm}–{current.workingZone.highMm} мм</span>}
        <span>{current.stageStatus === 'failed' ? 'Этап завершился с ошибкой' : current.stageStatus === 'aborted' ? 'Этап прерван' : current.stageStatus === 'done' ? 'Этап завершён' : 'Архивный замер'}</span>
        {current.code !== code && <span>В составе серии {current.code}</span>}</div>
      {current.reason && <p role="status" className="mp-problem">{current.reason}</p>}
      <MeasurementPlot key={code + current.id} code={code} result={current.result} mapSource={shownSource} />
    </> : archive.isPending ? <p role="status">Загрузка измерений…</p> : !archive.isError && <div className="bs-empty">
      <h3>Для этого источника ещё нет измерений {code}</h3><p>Откройте замер {code}. Здесь появятся результаты отдельных запусков и этапов автоматических серий.</p></div>}
  </section>
}
