import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motorApi, type SpeedDirection, type SpeedStudy as Study } from '@/features/motor/api/motor-api'

const speed = (mmS: number) => (mmS / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 3 })
const number = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 1 })

function Direction({ name, data, target }: { name: string; data: SpeedDirection; target: number }) {
  const { profileLimitMmS, insideLimits, brakingMm, availableMm, measuredMinMmS, measuredMaxMmS } = data
  return <div className="cal-speed-direction">
    <h4>{name} <span data-tone={insideLimits ? 'neutral' : 'warn'}>{insideLimits ? 'В пределах настроек' : 'Выше предела профиля'}</span></h4>
    <div className="cal-limit-track" aria-hidden="true">
      <i style={{ width: `${Math.min(100, profileLimitMmS / 15)}%` }} /><b style={{ left: `${target / 15}%` }} />
    </div>
    <dl>
      <div><dt>Предел профиля</dt><dd>{speed(profileLimitMmS)} м/с</dd></div>
      <div><dt>Измерено в M5</dt><dd>{measuredMinMmS !== null && measuredMaxMmS !== null ? `${speed(measuredMinMmS)}–${speed(measuredMaxMmS)} м/с` : 'Нет записи'}</dd></div>
      <div><dt>Путь торможения</dt><dd>{brakingMm !== null ? `${number(brakingMm)} мм` : 'Нужен замер M5'}</dd></div>
      <div><dt>От середины до границы</dt><dd>{availableMm !== null ? `${number(availableMm)} мм` : 'Проверьте B7, B8 и пределы'}</dd></div>
    </dl>
    {brakingMm !== null && !data.insideMeasuredRange ? <p data-tone="warn">Расчёт вне подтверждённого диапазона скоростей M5.</p> : null}
    {brakingMm !== null && availableMm !== null && brakingMm > availableMm ? <p data-tone="bad">До границы не хватает {number(brakingMm - availableMm)} мм.</p> : null}
  </div>
}

function ReversalReplay({ replay }: { replay: Study['replay'] }) {
  if (!replay) return <p>Частота опроса профиля не позволяет воспроизвести этот повтор. Проверьте B1.</p>
  const { points, strokeMm, turnDelayMs } = replay
  const end = points[points.length - 1][0]
  const peak = Math.max(1, ...points.flatMap(([, reference, observed]) => [Math.abs(reference), Math.abs(observed)]))
  const path = (index: 1 | 2) => points.map(p => `${(p[0] / end * 600).toFixed(2)},${(60 - 54 * p[index] / peak).toFixed(2)}`).join(' ')
  const timing = { measured: 'измерен в B1', manual: 'задан вручную', derived: 'расчётное значение профиля', default: 'из настроек по умолчанию' }[replay.cycleSource]
  return <div className="cal-replay">
    <p>Модель подаёт на рабочий алгоритм известную траекторию вверх и вниз на {number(strokeMm)} мм. Период опроса {number(replay.cycleMs)} мс ({timing}).</p>
    <figure>
      <figcaption><b>Скорость, м/с</b><span>Заданная</span><span>Оценка алгоритма</span></figcaption>
      <div className="cal-plot-body">
        <div className="cal-plot-scale"><span>+{speed(peak)}</span><span>0</span><span>−{speed(peak)}</span></div>
        <svg viewBox="0 0 600 120" preserveAspectRatio="none" role="img" aria-label="Заданная и оценённая скорости на модельном повторе">
          <line x1="0" x2="600" y1="60" y2="60" stroke="#536c78" />
          <polyline points={path(1)} fill="none" stroke="#6fc9ff" strokeWidth="3" vectorEffect="non-scaling-stroke" />
          <polyline points={path(2)} fill="none" stroke="#ffc478" strokeWidth="2" strokeDasharray="6 3" vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <div className="cal-time-axis"><span>0 с</span><span>Время повтора</span><span>{number(end)} с</span></div>
    </figure>
    <p>Среднеквадратичная ошибка скорости <b>{speed(replay.rmsMmS)} м/с</b>. {turnDelayMs === null ? 'Смена направления не распознана.' : `Алгоритм распознал разворот на ${number(Math.abs(turnDelayMs))} мс ${turnDelayMs < 0 ? 'раньше' : 'позже'} заданного момента.`}</p>
  </div>
}

export function SpeedStudy({ version }: { version?: number | null }) {
  const [target, setTarget] = useState(1500)
  const query = useQuery({ queryKey: ['motor', 'speed-study', version, target], queryFn: () => motorApi.speedStudy(target) })
  const data = query.data
  return <section className="cal-surface cal-speed-study" aria-label="Расчёт скорости">
    <div className="cal-workspace-heading"><h3>Расчёт скорости</h3><span>Без движения грифа</span></div>
    <label className="cal-speed-input">
      <span>Целевая скорость</span><strong>{speed(target)} <small>м/с</small></strong>
      <input type="range" aria-label="Целевая скорость, мм/с" aria-valuetext={`${speed(target)} м/с`} min={50} max={1500} step={50} value={target} onChange={e => setTarget(Number(e.target.value))} />
    </label>
    {data ? <>
      <p>Для цели нужно <b>{number(data.targetRpm)} об/мин</b>. В профиле предел привода {number(data.driveLimitRpm)} об/мин, аварийный порог {number(data.alarmRpm)} об/мин.</p>
      <p>{data.travelPerCycleMm != null && data.cycleMs != null ? `При этой скорости гриф проходит ${number(data.travelPerCycleMm)} мм за один измеренный цикл управления (${number(data.cycleMs)} мс по B1).` : 'После B1 здесь появится расстояние, которое гриф проходит за один цикл управления.'}</p>
      {data.m5RunId && data.m5Source !== data.adapter && <p data-tone="warn">{data.m5Source ? 'Запись M5 получена на другом источнике данных.' : 'В архивной записи M5 не указан источник данных.'} Для расчёта торможения выполните M5 на текущем тренажёре.</p>}
      <div className="cal-speed-grid"><Direction name="Подъём" data={data.directions.up} target={target} /><Direction name="Опускание" data={data.directions.down} target={target} /></div>
      <p>Модель M5 описывает активное торможение пустого грифа. Допуск ШВП и опор на {number(data.targetRpm)} об/мин требует паспортных данных установленного узла.</p>
      <details><summary>Модель быстрого разворота</summary><ReversalReplay replay={data.replay} /></details>
      <Link className="cal-link" to="?tab=observations">Сравнить с измеренной скоростью в подходах</Link>
    </> : <p role="status">{query.isError ? 'Не удалось прочитать скоростной профиль.' : 'Чтение скоростного профиля…'}</p>}
  </section>
}
