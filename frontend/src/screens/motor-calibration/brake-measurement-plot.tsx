import { useState } from 'react'
import { DirectionChoice, KeyMark, Metric, NoPoints, PlotFrame } from './measurement-frame'
import { axis, brakeRuns, finite, fmt, withUnit, type Direction, type Result } from './measurement-model'

const coastColor = '#eeb76f', brakeColor = '#6ad2e4'
export function BrakeMeasurementPlot({ result }: { result: Result }) {
  const [dir, setDir] = useState<Direction>('up')
  const [index, setIndex] = useState<number | null>(null)
  const all = brakeRuns(result), runs = all.filter(r => r.dir === dir)
  const longest = runs.reduce((best, r, i) => (r.total ?? -Infinity) > (runs[best]?.total ?? -Infinity) ? i : best, 0)
  const ix = index ?? longest, run = runs[ix], stop = finite(result.stopSpeedMmS)
  const distances = all.flatMap(r => [r.coast, r.total]).filter((v): v is number => v !== null)
  const scale = axis([0, ...(distances.some(v => v !== 0) ? distances : [1])])
  const left = 176, right = 718, row = 43, top = 42, bottom = top + runs.length * row
  const x = (v: number) => left + (v - scale.min) / (scale.max - scale.min) * (right - left)
  const trial = (r: typeof run) => fmt(r.target) + ' мм/с · ' + (r.direct ? 'сразу' : 'с поддержкой')
  return <PlotFrame title="Путь пустого грифа при торможении"
    description="У каждой заданной скорости два опыта. В одном торможение начинается сразу, в другом гриф сначала движется на поддержке. Шкала общая для подъёма и спуска."
    tools={<DirectionChoice dir={dir} onChange={v => { setDir(v); setIndex(null) }} />}
    inspector={<><h4>Подробности прогона</h4>{run ? <>
      <label className="mp-select">Задание и режим<select aria-label="Задание и режим" value={ix} onChange={e => setIndex(Number(e.target.value))}>
        {runs.map((r, i) => <option key={i} value={i}>{trial(r)}</option>)}</select></label>
      {run.total !== null ? <div className="mp-large"><span>Путь до порога остановки</span><strong>{fmt(run.total)} <small>мм</small></strong></div>
        : <NoPoints>{run.failed ? 'Быстрый ход перешёл в медленный режим. Для этого прогона путь не измерен.' : 'Полный путь неизвестен. Ниже приведены сохранившиеся измерения.'}</NoPoints>}
      {!run.failed &&
        <dl className="mp-metrics"><Metric label="Скорость в начале опыта">{withUnit(run.startSpeed, 'мм/с')}</Metric>
          <Metric label="Скорость в начале торможения">{withUnit(run.brakeSpeed, 'мм/с')}</Metric>
          <Metric label="Ход на поддержке">{withUnit(run.coast, 'мм')}</Metric><Metric label="Ход при торможении">{withUnit(run.brake, 'мм')}</Metric>
          <Metric label="Время активного торможения">{withUnit(run.time, 'с', 2)}</Metric></dl>}
      <p className="mp-note">{stop === null ? 'Численный порог остановки не указан в этой записи.' :
        'M5 заканчивает отсчёт при снижении скорости в направлении хода до ' + fmt(stop) + ' мм/с.'} Сравнивайте прогоны по фактической скорости в начале опыта.</p>
    </> : <NoPoints>В этом направлении прогонов нет.</NoPoints>}</>}>
    {!runs.length ? <NoPoints /> : <svg className="mp-svg" viewBox={`0 0 826 ${bottom + 59}`} role="img" aria-label="Измеренный путь на поддержке и при активном торможении в миллиметрах">
      <text className="mp-axis-title" x="12" y="21">Задание, мм/с</text><text className="mp-axis-title" x={right + 8} y="21">Путь, мм</text>
      <rect x="3" y={top + ix * row} width="811" height={row - 1} rx="7" fill="#203a47" />
      {scale.ticks.map(t => <g key={t}><line className={t === 0 ? 'mp-zero' : 'mp-grid v'} x1={x(t)} x2={x(t)} y1={top - 9} y2={bottom} />
        <text x={x(t)} y={bottom + 22} textAnchor="middle">{fmt(t)}</text></g>)}
      {runs.map((r, i) => {
        const py = top + row * (i + .5)
        return <g key={i} className="mp-hit" onClick={() => setIndex(i)}>
          <rect x="0" width="817" y={py - row / 2} height={row} fill="transparent" />
          <text x="12" y={py + 4} className="mp-axis-title">{fmt(r.target)}</text><text x="62" y={py + 4}>{r.direct ? 'сразу' : 'поддержка'}</text>
          {r.total !== null && r.coast !== null ? <>
            <rect x={Math.min(x(0), x(r.coast))} y={py - 8} height="16" width={Math.abs(x(r.coast) - x(0))} fill={coastColor} />
            <rect x={Math.min(x(r.coast), x(r.total))} y={py - 8} height="16" width={Math.abs(x(r.total) - x(r.coast))} fill={brakeColor} />
            <line x1={x(r.total)} x2={x(r.total)} y1={py - 10} y2={py + 10} stroke="#edf8fc" strokeWidth="2" />
            <text className="mp-axis-title" textAnchor="end" x="800" y={py + 4}>{fmt(r.total)}</text>
          </> : <text x={left + 15} y={py + 4} className="mp-missing">Нет замера{r.failed && ' · медленный ход'}</text>}
        </g>
      })}
      <text x={(left + right) / 2} y={bottom + 49} className="mp-axis-title" textAnchor="middle">Перемещение в направлении хода, мм</text>
    </svg>}
    <div className="mp-legend"><KeyMark color={coastColor}>Поддержка</KeyMark><KeyMark color={brakeColor}>Активное торможение</KeyMark></div>
  </PlotFrame>
}
