import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motorApi, type ObservationSource, type SetObservation } from '@/features/motor/api/motor-api'
import { SessionChart } from './session-chart'

const sourceName = { modbus: 'Тренажёр · Modbus', canopen: 'Тренажёр · CANopen', twin: 'Цифровой двойник' }
const statusName = { recording: 'Идёт запись', completed: 'Завершён', interrupted: 'Прерван' }
const modes: Record<string, string> = { constant: 'Постоянный вес', assist_up: 'Помощь при подъёме', eccentric: 'Эксцентрическая нагрузка', curve: 'Кривая нагрузки', bodyweight: 'Собственный вес' }
const number = (n: number | null, digits = 1) => n == null ? '—' : n.toLocaleString('ru-RU', { maximumFractionDigits: digits })
const stamp = (iso: string) => new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const pairSpeed = (pair: [number, number] | null) => pair ? pair.map(v => number(v / 1000, 3)).join(' / ') + ' м/с' : '—'
const exercise = (r: SetObservation) => r.exerciseName || r.exerciseSlug || 'Упражнение без названия'

function exportSet(data: SetObservation) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `egym-${data.source}-set-${data.id}.json`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function SetDetail({ record }: { record: SetObservation }) {
  const query = useQuery({ queryKey: ['motor', 'set-observation', record.id, record.status], queryFn: () => motorApi.observation(record.id),
    refetchInterval: record.status === 'recording' ? 3500 : false })
  const r = query.data ?? record
  const skewWarning = r.maxSkewMm != null && r.maxSkewMm >= r.skewWarningMm
  return <section className="cal-surface cal-set-detail" aria-label="Запись подхода">
    <div className="cal-workspace-heading"><div><h2>{exercise(r)} · подход {r.setNumber}</h2>
      <p>{stamp(r.startedAt)} · {sourceName[r.source]} · профиль v{r.profileVersion}</p></div>
      <span data-tone={r.status === 'interrupted' ? 'warn' : 'good'}>{statusName[r.status]}</span></div>
    {r.reason && <p className="cal-stop-reason">{r.reason}</p>}
    <p>{r.fixedMm == null ? modes[r.mode] ?? r.mode : 'Фиксация грифа'} · {number(r.initialKg)} кг · нагрузка {r.loadDirection === 'down' ? 'вниз' : 'вверх'}.
      {' '}{r.fixedMm == null ? `Заданный ход ${number(r.lowerMm)}–${number(r.upperMm)} мм.` : `Точка удержания ${number(r.fixedMm)} мм.`}</p>
    <div className="cal-signal-readings"><dl>
      <div><dt>Рабочее время по кадрам</dt><dd>{number(r.workS)} с</dd></div>
      <div><dt>{r.fixedMm == null ? 'Полные / частичные повторы' : 'Учёт повторений'}</dt><dd>{r.fixedMm == null ? `${r.fullReps} / ${r.partialReps}` : 'Вручную в тренировке'}</dd></div>
      <div><dt>Измеренный ход</dt><dd>{r.minHeightMm == null ? '—' : `${number(r.minHeightMm)}–${number(r.maxHeightMm)} мм`}</dd></div>
      <div><dt>Пик подъёма · левая / правая</dt><dd>{pairSpeed(r.upMmS)}</dd></div>
      <div><dt>Пик спуска · левая / правая</dt><dd>{pairSpeed(r.downMmS)}</dd></div>
      <div><dt>Максимальный перекос</dt><dd>{r.maxSkewMm == null ? '—' : `${number(r.maxSkewMm)} мм при ${number(r.skewHeightMm)} мм`}</dd></div>
      {r.fixedPeakErrorMm && <div><dt>Уход от фиксации · левая / правая</dt><dd>{r.fixedPeakErrorMm.map(v => number(v)).join(' / ')} мм</dd></div>}
    </dl></div>
    {r.approach && <details className="cal-encoder-check"><summary>Подвод к старту · {number(r.approach.fromMm)} → {number(r.approach.targetMm)} мм</summary>
      <p>{({ moving: 'Идёт подвод', hold: 'Переход в удержание', interrupted: 'Подвод прерван' })[r.approach.status]}. По кадрам движения · {number(r.approach.seconds)} с, пик {number(r.approach.peakMmS / 1000, 3)} м/с.</p>
      <p>Отклонение от цели в последнем кадре подвода · левая {number(r.approach.errorsMm[0])} мм, правая {number(r.approach.errorsMm[1])} мм.</p>
    </details>}
    {r.encoderWindowS != null && <details className="cal-encoder-check"><summary>Сверка скорости по перемещению кареток</summary>
      <p>Пиковая средняя скорость на непрерывных отрезках от {number(1000 * r.encoderWindowS)} мс, левая / правая.
        {' '}Подъём · {pairSpeed(r.encoderUpMmS ?? null)}. Спуск · {pairSpeed(r.encoderDownMmS ?? null)}. Измерено отрезков · {r.encoderWindows ?? 0}.</p>
      <p>Одиночный всплеск сигнала скорости при неподвижном энкодере здесь виден при сравнении с пиками приводов.</p>
    </details>}
    {skewWarning && <p className="cal-stop-reason">Перекос достиг порога предупреждения профиля ({number(r.skewWarningMm)} мм). Сравните ход обеих сторон на этой высоте. <Link to={'?tab=friction&source=' + r.source + (r.skewHeightMm != null ? '&height=' + r.skewHeightMm : '')}>Карта трения по высоте</Link></p>}
    {query.isError ? <p role="alert">Не удалось загрузить график. <button type="button" className="cal-link" onClick={() => void query.refetch()}>Повторить</button></p>
      : !query.data ? <p role="status">Загрузка кадров…</p>
        : query.data.trace.t.length ? <SessionChart log={query.data.trace} code="EXERCISE" />
          : <p className="cal-empty">Рабочие кадры ещё не получены. Запись движения начинается, когда контроллер включает тренировку или фиксацию грифа.</p>}
    <p className="cal-quality">Принято {r.validFrames} кадров · отброшено {r.invalidFrames} · участков записи {r.segments}. Паузы и подвод к старту исключены из рабочих значений. Пики рассчитаны по всем принятым кадрам.</p>
    {query.data && <button type="button" className="cal-link" onClick={() => { if (query.data) exportSet(query.data) }}>Скачать запись JSON</button>}
  </section>
}

function ObservationList({ source }: { source: ObservationSource }) {
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const query = useQuery({ queryKey: ['motor', 'set-observations', source, offset], queryFn: () => motorApi.observations(source, offset), refetchInterval: offset === 0 ? 5000 : false })
  const rows = query.data?.items ?? []
  const record = rows.find(r => r.id === selected) ?? rows[0]
  if (query.isError) return <p role="alert">Не удалось прочитать журнал. <button type="button" className="cal-link" onClick={() => void query.refetch()}>Повторить</button></p>
  if (!query.data) return <p role="status">Загрузка журнала…</p>
  if (!record) return <p className="cal-surface">Записей для источника «{sourceName[source]}» пока нет. Проведите подход на тренажёре с этим источником, и его измерения появятся здесь автоматически.</p>
  return <div className="cal-workspace">
    <aside className="cal-surface cal-sidebar"><h2>Подходы</h2>
      <ol className="cal-set-list">{rows.map(row => <li key={row.id}><button type="button" aria-pressed={row.id === record.id} onClick={() => setSelected(row.id)}>
        <strong>{exercise(row)}</strong><span>{stamp(row.startedAt)} · подход {row.setNumber}</span>
        <small>{statusName[row.status]} · {number(row.initialKg)} кг · v{row.profileVersion}</small></button></li>)}</ol>
      <div className="cal-pages">{offset > 0 && <button className="cal-link" onClick={() => setOffset(offset - 20)}>Новее</button>}
        {query.data.hasMore && <button className="cal-link" onClick={() => setOffset(offset + 20)}>Старее</button>}</div>
    </aside>
    <SetDetail key={record.id} record={record} />
  </div>
}

export function ExerciseObservations({ adapter }: { adapter?: string }) {
  const [chosen, setChosen] = useState<ObservationSource | null>(null)
  const source = chosen ?? (adapter === 'twin' ? 'twin' : adapter?.startsWith('canopen') ? 'canopen' : 'modbus')
  return <div className="cal-lab"><section className="cal-surface"><div className="cal-workspace-heading">
    <div><h2>Механика упражнений</h2><p>Сравнивайте скорость, усилие и перекос в обычных подходах с измерениями калибровки.</p></div>
    <div className="cal-plot-tools" role="group" aria-label="Источник записей">
      {(['modbus', 'canopen', 'twin'] as const).map(s => <button type="button" key={s} aria-pressed={s === source} onClick={() => setChosen(s)}>{sourceName[s]}</button>)}
    </div></div></section>
    <ObservationList key={source} source={source} />
  </div>
}
