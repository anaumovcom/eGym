import { useState } from 'react'
import type { FrictionSource, Side } from '@/features/motor/api/motor-api'
import { railColor, railName, rails } from './friction-track-model'
import { DirectionChoice, HeightMapLink, KeyMark, Metric, NoPoints, PlotFrame } from './measurement-frame'
import { axis, fmt, forcePoints, withUnit, type Direction, type ForcePoint, type Result } from './measurement-model'

type ForceStage = 'S7' | 'D2' | 'F3'
const left = 68, right = 782, top = 38, bottom = 298
const copy = {
  S7: 'Точки показывают усилие поддержки на измеренной высоте грифа. Вертикальные отрезки соединяют пороги трогания каретки вниз и вверх.',
  D2: 'Скорость измерена по ходу каждой каретки. Сопротивление рассчитано по заданному усилию привода с поправкой на вес и ускорение.',
  F3: 'Каждая точка получена на установившемся ходе. Скорость общая для грифа, сопротивление оценено по управляющему усилию каждой стороны.',
}

export function ForceMeasurementPlot({ code, result, mapSource }: { code: ForceStage; result: Result; mapSource?: FrictionSource }) {
  const [dir, setDir] = useState<Direction>('up')
  const [pick, setPick] = useState<{ side: Side; index: number } | null>(null)
  const height = code === 'S7'
  const series = { left: forcePoints(code, result, 'left', dir), right: forcePoints(code, result, 'right', dir) }
  const side = pick && series[pick.side].length ? pick.side : series.left.length ? 'left' : 'right'
  const points = series[side]
  const index = pick ? Math.min(pick.index, points.length - 1) : height ? Math.floor(points.length / 2) : points.length - 1
  const current = points[index]
  const all = [...series.left, ...series.right]
  const xAxis = axis(all.map(p => p.x))
  const yAxis = axis(all.flatMap(p => [p.y, ...(p.low === null ? [] : [p.low]), ...(p.high === null ? [] : [p.high])]))
  const x = (v: number) => left + (v - xAxis.min) / (xAxis.max - xAxis.min) * (right - left)
  const y = (v: number) => bottom - (v - yAxis.min) / (yAxis.max - yAxis.min) * (bottom - top)
  const at = height ? 'Высота' : 'Скорость', unit = height ? 'мм' : 'мм/с'
  const title = height ? 'Усилие поддержки и трогания' : 'Сопротивление на измеренных скоростях'
  const forceName = height ? 'Поддержка' : 'Сопротивление'
  const changeSide = (next: Side) => {
    const items = series[next]
    const nextIndex = current ? items.reduce((best, p, i) => Math.abs(p.x - current.x) < Math.abs(items[best].x - current.x) ? i : best, 0) : 0
    setPick({ side: next, index: nextIndex })
  }
  function dot(p: ForcePoint, s: Side) {
    return s === 'left' ? <circle cx={x(p.x)} cy={y(p.y)} r="5.8" fill="#0d2330" stroke={railColor[s]} strokeWidth="2.8" />
      : <path d={`M${x(p.x)} ${y(p.y) - 4.4}l4.4 4.4 -4.4 4.4 -4.4 -4.4Z`} fill={railColor[s]} />
  }
  return <PlotFrame title={title} description={copy[code]}
    tools={!height && <DirectionChoice dir={dir} onChange={d => { setDir(d); setPick(null) }} />}
    inspector={<>
      <h4>Точка замера</h4>
      <div className="mp-switch" role="group" aria-label="Сторона тренажёра">{rails.map(s =>
        <button type="button" key={s} aria-pressed={side === s} disabled={!series[s].length} onClick={() => changeSide(s)}>
          <i className="mp-side-dot" style={{ background: railColor[s] }} />{railName[s]}</button>)}</div>
      {current ? <>
        <label className="mp-select">{at} замера<select aria-label={at + ' замера'} value={index} onChange={e => setPick({ side, index: Number(e.target.value) })}>
          {points.map((p, i) => <option key={i} value={i}>{fmt(p.x)} {unit}</option>)}</select></label>
        <div className="mp-large"><span>{forceName} · {railName[side].toLowerCase()} сторона</span><strong>{fmt(current.y)} <small>Н</small></strong></div>
        {height ? <><dl className="mp-metrics"><Metric label="Порог трогания вверх">{withUnit(current.high, 'Н')}</Metric>
          <Metric label="Порог трогания вниз">{withUnit(current.low, 'Н')}</Metric>
          <Metric label="Ширина окна">{withUnit(current.low !== null && current.high !== null ? current.high - current.low : null, 'Н')}</Metric></dl>
          <p className="mp-note">{current.low === null || current.high === null ? 'Для этой точки сохранилось только усилие поддержки. Новый замер S7 запишет оба порога.' :
            'Чем шире окно, тем сильнее нужно изменить усилие, чтобы сдвинуть каретку.'}</p>
          {mapSource && <HeightMapLink source={mapSource} height={current.x} />}</>
          : <><dl className="mp-metrics"><Metric label="Измеренный диапазон">{fmt(points[0].x)}–{fmt(points[points.length - 1].x)} мм/с</Metric>
            <Metric label="Точек в этом направлении">{points.length}</Metric></dl>
            <p className="mp-note">Сравните сопротивление левой и правой сторон при близких скоростях. Переключите направление, чтобы проверить разницу на спуске.</p></>}
      </> : <NoPoints>Для выбранного направления точки отсутствуют.</NoPoints>}
    </>}>
    {!all.length ? <NoPoints /> : <svg className="mp-svg mp-force-svg" viewBox="0 0 820 354" role="img" aria-label={title + ' · ' + at + ', ' + unit}>
      <text x={left} y="19" className="mp-axis-title">{height ? 'Усилие' : 'Сопротивление'}, Н</text>
      {yAxis.ticks.map(v => <g key={v}><line className="mp-grid" x1={left} x2={right} y1={y(v)} y2={y(v)} />
        <text x={left - 11} y={y(v) + 4} textAnchor="end">{fmt(v, 2)}</text></g>)}
      {xAxis.ticks.map(v => <g key={v}><line className="mp-grid v" x1={x(v)} x2={x(v)} y1={top} y2={bottom} />
        <text x={x(v)} y={bottom + 22} textAnchor="middle">{fmt(v, 2)}</text></g>)}
      <text className="mp-axis-title" x={(left + right) / 2} y="346" textAnchor="middle">{height ? 'Средняя высота грифа' : 'Скорость'}, {unit}</text>
      {current && <line className="mp-cursor" x1={x(current.x)} x2={x(current.x)} y1={top} y2={bottom} />}
      {rails.map(s => <g key={s}>
        <polyline fill="none" stroke={railColor[s]} opacity=".8" strokeWidth="2.5" strokeDasharray={s === 'right' ? '6 5' : undefined}
          points={series[s].map(p => x(p.x) + ',' + y(p.y)).join(' ')} />
        {series[s].map((p, i) => <g key={i} className="mp-hit" onClick={() => setPick({ side: s, index: i })}>
          {height && p.low !== null && p.high !== null && <g transform={'translate(' + (s === 'left' ? -4 : 4) + ',0)'}>
            <path fill="none" stroke={railColor[s]} strokeWidth="2" opacity=".85"
              d={`M${x(p.x) - 3} ${y(p.low)}h6 M${x(p.x)} ${y(p.low)}V${y(p.high)} M${x(p.x) - 3} ${y(p.high)}h6`} />
          </g>}
          {dot(p, s)}<circle cx={x(p.x)} cy={y(p.y)} r="12" fill="transparent" />
        </g>)}
      </g>)}
      {current && <circle cx={x(current.x)} cy={y(current.y)} r="10" fill="none" stroke="#f4f9ff" strokeWidth="1.7" pointerEvents="none" />}
    </svg>}
    <div className="mp-legend"><KeyMark color={railColor.left} shape="circle">Левая сторона</KeyMark>
      <KeyMark color={railColor.right} shape="diamond">Правая сторона</KeyMark>{height && <span>↕ Пороги трогания</span>}</div>
  </PlotFrame>
}
