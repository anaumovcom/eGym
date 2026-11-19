import { useState } from 'react'
import type { FrictionSource } from '@/features/motor/api/motor-api'
import { railColor, railName } from './friction-track-model'
import { DirectionChoice, HeightMapLink, Metric, NoPoints, PlotFrame } from './measurement-frame'
import { fmt, repeatRows, withUnit, type Direction, type Result } from './measurement-model'

export function RepeatabilityPlot({ result, mapSource }: { result: Result; mapSource?: FrictionSource }) {
  const [dir, setDir] = useState<Direction>('up')
  const [selected, setSelected] = useState<number | null>(null)
  const rows = repeatRows(result, dir)
  if (!rows.length) return <NoPoints />
  const risk = (r: typeof rows[number]) => r.spread !== null && r.limit !== null && r.limit > 0 ? r.spread / r.limit : -1
  const worst = rows.reduce((best, r, i) => risk(r) > risk(rows[best]) ? i : best, 0)
  const firstMissing = rows.findIndex(r => r.count < 3)
  const ix = selected ?? (rows[worst].ok === false || firstMissing < 0 ? worst : firstMissing)
  const current = rows[ix] ?? rows[0]
  const maxRatio = Math.max(1.25, ...rows.map(risk))
  const observed = rows.flatMap(r => r.values.filter((v): v is number => v !== null))
  const lo = Math.min(...observed), hi = Math.max(...observed)
  const sy = (v: number) => lo === hi ? 14 : 24 - 20 * (v - lo) / (hi - lo)
  const evaluated = rows.filter(r => r.ok !== null)
  const status = (r: typeof current) => r.count < 3 ? r.count + ' из 3' : r.ok === null ? result.partial ? 'Ожидает оценки' : 'Без допуска' : r.ok ? 'В допуске' : 'Превышен'
  return <PlotFrame title="Усилие в трёх проходах на одной высоте"
    description="Каждое число — медиана усилия привода на участке устойчивой скорости. Сравните одну каретку на одной высоте в трёх проходах."
    tools={<DirectionChoice dir={dir} onChange={next => { setDir(next); setSelected(null) }} />}
    inspector={<><h4>Участок повторного замера</h4>
      <label className="mp-select">Высота и сторона<select aria-label="Высота и сторона" value={ix} onChange={e => setSelected(Number(e.target.value))}>
        {rows.map((r, i) => <option key={i} value={i}>{fmt(r.height)} мм · {railName[r.side]}</option>)}</select></label>
      <div className="mp-large"><span>Разброс трёх проходов</span>{current.spread === null ? <b>{current.attempted.includes(false) ? current.count + ' из 3 проходов' : 'Мало данных'}</b> : <strong>{fmt(current.spread)} <small>Н</small></strong>}</div>
      <dl className="mp-metrics"><Metric label="Допуск участка">{current.limit === null ? result.partial ? 'При итоговой оценке' : 'Не записан' : withUnit(current.limit, 'Н')}</Metric>
        <Metric label="Оценка"><span className="mp-state" data-state={current.ok === null ? 'unknown' : current.ok ? 'ok' : 'exceeded'}>{status(current)}</span></Metric>
        <Metric label="В допуске в этом направлении">{evaluated.length ? rows.filter(r => r.ok === true).length + ' из ' + evaluated.length + ' оценённых' : 'Участки ещё не оценены'}</Metric></dl>
      <p className="mp-note">{result.partial ? 'Ячейка заполняется по завершении прохода при наличии отсчётов на рабочей скорости. Для итоговой оценки нужны три прохода в каждом направлении.'
        : current.count < 3 ? 'Пропуск означает, что для прохода нет достаточного числа отсчётов на рабочей скорости. Проверьте ход в M2 и повторите G4.'
        : current.ok === false ? 'На этой высоте усилие меняется от прохода к проходу сильнее допуска G4. Сопоставьте участок с картой ШВП и перекосом X3.'
        : 'Стабильное усилие может повторяться и на тугом участке. Его положение удобнее проверить по карте ШВП.'}</p>
      {mapSource && <HeightMapLink source={mapSource} height={current.height} />}
    </>}>
    <div className="mp-matrix-scroll"><table className="mp-matrix"><caption className="sr-only">Усилие по высоте, стороне и номеру прохода в ньютонах</caption>
      <thead><tr><th>Высота</th><th>Сторона</th>{[1, 2, 3].map(n => <th key={n}>{n}-й, Н</th>)}<th>Изменение</th><th>Разброс / допуск, Н</th></tr></thead>
      <tbody>{rows.map((r, i) => <tr key={r.height + r.side} data-chosen={i === ix} data-end={r.side === 'right'} onClick={() => setSelected(i)}>
        <th scope="row"><button type="button" aria-label={fmt(r.height) + ' мм, ' + railName[r.side] + ' сторона'} aria-pressed={i === ix} onClick={() => setSelected(i)}>{fmt(r.height)} мм</button></th>
        <td><i className="mp-side-dot" style={{ background: railColor[r.side] }} />{railName[r.side]}</td>
        {r.values.map((v, j) => <td key={j} className={v === null ? 'mp-missing' : ''} aria-label={v !== null ? undefined : r.attempted[j] ? 'Недостаточно отсчётов' : 'Проход не выполнен'}>
          {r.attempted[j] ? fmt(v) : '·'}</td>)}
        <td><svg viewBox="0 0 64 28" aria-hidden="true" className="mp-spark">
          {r.values.map((v, j) => v !== null && <g key={j}>{j > 0 && r.values[j - 1] !== null &&
            <line x1={6 + (j - 1) * 26} y1={sy(r.values[j - 1]!)} x2={6 + j * 26} y2={sy(v)} stroke={railColor[r.side]} strokeWidth="2" />}
            <circle cx={6 + j * 26} cy={sy(v)} r="3.3" fill={railColor[r.side]} /></g>)}</svg></td>
        <td>{r.spread === null ? <span className="mp-state" data-state="unknown">{status(r)}</span> : <div className="mp-spread" data-exceeded={r.ok === false}>
          <span>{fmt(r.spread)} / {fmt(r.limit)}{r.ok === false && ' ↑'}</span>
          {risk(r) >= 0 && <i><b style={{ width: (risk(r) / maxRatio * 100) + '%' }} /><em style={{ left: (100 / maxRatio) + '%' }} /></i>}</div>}</td>
      </tr>)}</tbody></table></div>
    <div className="mp-legend">{rows.some(r => r.attempted.includes(false)) && <span>· Проход не выполнен</span>}
      <span>— Недостаточно отсчётов</span><span>│ Отметка допуска</span><span>↑ Разброс выше допуска</span></div>
  </PlotFrame>
}
