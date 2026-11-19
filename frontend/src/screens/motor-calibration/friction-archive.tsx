import { useInfiniteQuery } from '@tanstack/react-query'
import { ArrowRight, ScanLine } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { motorApi, type FrictionSource } from '@/features/motor/api/motor-api'
import { archiveLabel, archiveSources as sources } from './archive-labels'
import { BallScrewMap } from './friction-track-chart'
import { binWidth, comparisonIssue, format } from './friction-track-model'

export function FrictionArchiveTab({ activeAdapter }: { activeAdapter?: string }) {
  const [url, setUrl] = useSearchParams()
  const requested = url.get('source')
  const source = requested && Object.hasOwn(sources, requested) ? requested as FrictionSource : undefined
  const requestedHeight = url.get('height')
  const height = requestedHeight && Number.isFinite(Number(requestedHeight)) ? Number(requestedHeight) : undefined
  const [selected, setSelected] = useState('')
  const [reference, setReference] = useState('')
  const archive = useInfiniteQuery({
    queryKey: ['motor', 'runs', 'friction-tracks', source ?? activeAdapter ?? 'current'],
    initialPageParam: 0, queryFn: ({ pageParam }) => motorApi.frictionTracks(pageParam, source),
    getNextPageParam: (last, pages) => last.hasMore ? pages.reduce((n, p) => n + p.items.length, 0) : undefined,
  })
  const records = archive.data?.pages.flatMap(p => p.items) ?? []
  const current = records.find(r => r.id === selected) ?? records[0]
  const previous = current ? records.slice(records.indexOf(current) + 1) : []
  const before = previous.find(r => r.id === reference)
  const shownSource = source ?? archive.data?.pages[0]?.source
  const issue = before && current && shownSource ? comparisonIssue(current.track, before.track, shownSource) : null
  return <section className="cal-surface bs-archive" aria-label="Карта ШВП">
    <header className="bs-archive-heading">
      <div className="bs-heading-icon"><ScanLine size={25} aria-hidden="true" /></div>
      <div><h2>Сопротивление ШВП</h2><p>Найдите, где туже идёт левая или правая каретка, и сравните ход после регулировки.</p></div>
      <Link className="bs-scan-link" to="?tab=calibrations&scenario=motion&code=S10">Открыть замер S10 <ArrowRight size={16} aria-hidden="true" /></Link>
    </header>
    <div className="bs-filters">
      <label>Источник<select value={shownSource ?? ''} onChange={e => {
        const next = new URLSearchParams(url)
        next.set('source', e.target.value)
        next.delete('height')
        next.delete('from')
        setUrl(next)
        setSelected('')
        setReference('')
      }}>
        {!shownSource && <option value="">Текущий режим тренажёра</option>}
        {Object.entries(sources).map(([v, name]) => <option key={v} value={v}>{name}</option>)}
      </select></label>
      {current && <><label>Показать замер<select value={current.id} onChange={e => { setSelected(e.target.value); setReference('') }}>
        {records.map(r => <option key={r.id} value={r.id}>{archiveLabel(r)}</option>)}
      </select></label>
        <label>Сравнить с замером до регулировки<select value={before?.id ?? ''} disabled={!previous.length} onChange={e => setReference(e.target.value)}>
          <option value="">{previous.length ? 'Без сравнения' : 'Нет более раннего замера'}</option>
          {previous.map(r => <option key={r.id} value={r.id}>{archiveLabel(r)}</option>)}
        </select></label></>}
    </div>
    {archive.hasNextPage && <button type="button" className="cal-link" disabled={archive.isFetchingNextPage} onClick={() => void archive.fetchNextPage()}>Показать более ранние замеры</button>}
    {archive.isError && <p role="alert">Не удалось загрузить карты. <button type="button" className="cal-link" onClick={() => void archive.refetch()}>Повторить</button></p>}
    {archive.isPending ? <p role="status">Загрузка карт ШВП…</p> : !current ? !archive.isError && <div className="bs-empty">
      <h3>Для этого источника пока нет карты</h3>
      <p>Откройте S10 и выполните подъём и спуск пустого грифа. Здесь появятся участки повышенного сопротивления по каждой стороне. Подходит также замер S10 из серии «Направляющие и баланс».</p>
    </div> : <>
      <div className="bs-scan-meta"><strong>{shownSource && sources[shownSource]}</strong><span>S10 · пустой гриф</span>
        {current.track.speedMmS != null && <span>Скорость {format(current.track.speedMmS)} мм/с</span>}
        <span>Шаг {format(binWidth(current.track))} мм</span></div>
      {issue && <p className="bs-compare-issue" role="status">Сравнение недоступно. {issue}</p>}
      <BallScrewMap key={current.id} track={current.track} before={!issue ? before?.track : undefined} atHeight={height}
        heightFrom={url.get('from') === 'calibration' ? 'calibration' : 'exercise'} />
    </>}
  </section>
}
