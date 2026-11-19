import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motorApi, type FaultCase, type FaultResponse } from '@/features/motor/api/motor-api'

const reaction: Record<FaultResponse, string> = {
  ok: 'Ровный ход', warning: 'Предупреждение', skew: 'Остановка по перекосу',
  telemetry: 'Остановка по давности кадра', drive: 'Остановка по отказу привода',
}
const format = (x: number | null) => x == null ? '—' : x.toLocaleString('ru-RU', { maximumFractionDigits: 2 })

function FaultTrace({ row, warn, stop }: { row: FaultCase; warn: number; stop: number }) {
  const frames = row.frames
  const [index, setIndex] = useState(frames.length - 1)
  const focus = frames[index]
  const extent = Math.max(stop, ...frames.flatMap(f => [Math.abs(f.rawMm ?? 0), Math.abs(f.deltaMm ?? 0)])) * 1.16
  const end = frames.at(-1)!.ms
  const x = (ms: number) => 5 + 690 * ms / Math.max(end, 1)
  const y = (mm: number) => 64 - 59 * mm / extent
  const path = (key: 'deltaMm' | 'rawMm') => frames.map((f, i) => {
    const value = f[key]
    return value === null ? '' : `${i && frames[i - 1][key] !== null ? 'L' : 'M'}${x(f.ms)},${y(value)}`
  }).join(' ')
  const event = frames.find(f => f.state === 'stop')
  return <figure className="cal-fault-trace">
    <figcaption><strong>Перекос Л−П, мм</strong>
      <span><i className="cal-fault-aligned" /> На один момент <b>{format(focus.deltaMm)}</b></span>
      <span><i className="cal-fault-raw" /> При опросе <b>{format(focus.rawMm)}</b></span>
    </figcaption>
    <div className="cal-plot-body"><div className="cal-plot-scale"><span>+{format(extent)}</span><span>0</span><span>−{format(extent)}</span></div>
      <svg viewBox="0 0 700 128" preserveAspectRatio="none" role="img" aria-label={`Модель перекоса. Предупреждение ±${warn} мм, остановка ±${stop} мм`}>
        {[-stop, -warn, 0, warn, stop].map(v => <line key={v} x1="0" x2="700" y1={y(v)} y2={y(v)}
          stroke={Math.abs(v) === stop ? '#f28783' : v ? '#daaa62' : '#496780'} strokeDasharray={v ? '4 5' : undefined} />)}
        <path d={path('rawMm')} fill="none" stroke="#f5bf7e" strokeWidth="4" strokeDasharray="8 5" vectorEffect="non-scaling-stroke" />
        <path d={path('deltaMm')} fill="none" stroke="#73d2fb" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        {event && <line x1={x(event.ms)} x2={x(event.ms)} y1="0" y2="128" stroke="#ff8984" strokeWidth="2" />}
        <line x1={x(focus.ms)} x2={x(focus.ms)} y1="0" y2="128" stroke="#ddedf5" strokeDasharray="2 4" />
        {focus.deltaMm !== null && <circle cx={x(focus.ms)} cy={y(focus.deltaMm)} r="3" fill="#73d2fb" />}
      </svg>
    </div>
    <div className="cal-time-axis"><span>0 мс</span><span>Время модели</span><span>{format(end)} мс</span></div>
    <label className="cal-fault-cursor">Кадр {index + 1} · {format(focus.ms)} мс
      <input type="range" min={0} max={frames.length - 1} value={index} aria-label="Кадр модели" onChange={e => setIndex(Number(e.target.value))} />
      <strong data-tone={focus.state === 'stop' ? 'bad' : focus.state === 'warning' ? 'warn' : 'neutral'}>
        {focus.state === 'stop' ? 'Остановка' : focus.state === 'warning' ? 'Предупреждение' : focus.deltaMm === null ? 'Ожидание пары' : 'В допуске'}
      </strong>
    </label>
  </figure>
}

export function FaultRehearsal({ version }: { version?: number | null }) {
  const query = useQuery({ queryKey: ['motor', 'fault-rehearsal', version], queryFn: motorApi.faultRehearsal })
  const [selected, setSelected] = useState('left')
  const data = query.data
  const row = data?.cases.find(c => c.id === selected) ?? data?.cases[0]
  return <section className="cal-surface cal-fault" aria-label="Моделирование отказов">
    <div className="cal-workspace-heading"><div><h2>Моделирование отказов</h2>
      <p>Проверьте реакцию контроллера на модельных кадрах. Приводы остаются в текущем состоянии.</p></div>
      {data && <label>Ситуация <select value={row?.id} onChange={e => setSelected(e.target.value)}>
        {data.cases.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select></label>}
    </div>
    {query.isError ? <p role="alert">Не удалось загрузить проверку. <button className="cal-link" onClick={() => void query.refetch()}>Повторить</button></p>
      : data && row ? <>
        <p>{row.description}</p>
        <div className="cal-fault-limits"><span>Профиль v{data.version}</span><span data-tone="warn">Предупреждение ±{format(data.warningMm)} мм</span>
          <span data-tone="bad">Остановка ±{format(data.criticalMm)} мм</span></div>
        <FaultTrace key={row.id} row={row} warn={data.warningMm} stop={data.criticalMm} />
        <p className="cal-fault-outcome" role="status" data-tone={row.matches ? 'neutral' : 'bad'}>
          <strong>{reaction[row.actual]}</strong> · {row.matches ? 'Реакция совпала с ожидаемой.' : `Ожидалось «${reaction[row.expected]}».`}
          {row.detail && ` ${row.detail}`}
        </p>
      </> : <p role="status">Вычисление модельных кадров…</p>}
  </section>
}
