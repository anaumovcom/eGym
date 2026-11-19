import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { motorApi, type CalibrationRunRecord, type ParamItem } from '@/features/motor/api/motor-api'
import { ApiError } from '@/shared/api/client'
import { CalibrationGuide } from './calibration-guide'
import { PriorityMark } from './calibration-priority'
import { CalibrationFindings, ChangesTable, ReportTable } from './calibration-run-controls'
import { SessionChart } from './session-chart'

export function CalibrationRecordView({ runId, item, parameter }: {
  runId: string; item?: CalibrationRunRecord; parameter?: Pick<ParamItem, 'scope' | 'key'>
}) {
  const [stageCode, setStageCode] = useState('')
  const record = useQuery({ queryKey: ['motor', 'record', runId, item?.status ?? 'source'], queryFn: () => motorApi.record(runId), retry: false })
  if (record.isError) return <p role="status">{record.error instanceof ApiError && record.error.status === 404
    ? 'Запись этого замера отсутствует в архиве.' : 'Не удалось загрузить запись замера.'} <button type="button" className="cal-link" onClick={() => void record.refetch()}>Повторить</button></p>
  if (!record.data) return <p role="status">Загрузка записи…</p>
  const { stages, workingZone, baseVersion, adapter, savedVersion, startedAt } = record.data
  const code = record.data.code ?? item?.code ?? ''
  const stage = stages.find(s => s.code === stageCode)
  const whole = record.data.log?.t.length ? record.data.log : stages.length === 1 ? record.data.stageLogs?.[stages[0].code] : null
  const log = stage ? record.data.stageLogs?.[stage.code] : whole
  const changes = (record.data.changes ?? item?.changes ?? []).filter(c => !parameter || (c.key === parameter.key && c.scope === parameter.scope))
  return <div className="cal-archived">
    {parameter && <h4>Запись замера · {code} {record.data.title}</h4>}
    <PriorityMark code={stage?.code ?? code} explain />
    <CalibrationFindings stages={stage ? [stage] : stages} onStage={!stage && stages.length > 1 ? setStageCode : undefined} />
    <CalibrationGuide code={stage?.code ?? code} title={stage?.title ?? record.data.title ?? code} />
    <p>{adapter === 'twin' ? 'Цифровой двойник' : adapter === 'modbus' ? 'Тренажёр' : adapter === 'canopen' ? 'Тренажёр · CANopen' : 'Источник не указан'}
      {startedAt && ' · ' + new Date(startedAt).toLocaleString('ru-RU')}
      {baseVersion != null && ' · исходный профиль v' + baseVersion}{savedVersion != null && ' · сохранено в v' + savedVersion}</p>
    {stages.length > 1 && <label className="cal-stage-select">Посмотреть запись
      <select value={stageCode} onChange={e => setStageCode(e.target.value)}><option value="">Вся серия</option>
        {stages.map(s => <option key={s.code} value={s.code}>{s.code} · {s.title}</option>)}
      </select></label>}
    {log?.t.length ? <SessionChart key={stageCode} log={log} code={stage?.code ?? code} zone={stage ? stage.workingZone : workingZone} />
      : <p>{stage && whole?.t.length ? 'Отдельная телеметрия этапа отсутствует. Общий график можно открыть в пункте «Вся серия».'
        : 'У этого запуска нет записи телеметрии.'}</p>}
    <ReportTable stages={stage ? [stage] : stages} />
    {changes.length > 0 && <><h4>{parameter ? 'Значения параметра в этой записи' : 'Изменения профиля за запуск'}</h4><ChangesTable changes={changes} /></>}
  </div>
}
