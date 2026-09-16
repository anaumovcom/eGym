import { Check, Loader2, Play, Square } from 'lucide-react'
import { useState } from 'react'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import type { HardwareProcedureStatus } from '@/features/hardware/model/types'
import { useAppStore } from '@/stores/app-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

const PROCEDURE_ARGS: Record<string, { key: string; label: string; default: number }[]> = {
  kg_factor: [{ key: 'reference_kg', label: 'Эталонный груз, кг', default: 10 }],
  hold_load: [{ key: 'load_kg', label: 'Нагрузка, кг', default: 20 }],
  failure: [{ key: 'load_kg', label: 'Нагрузка, кг', default: 40 }],
  jerk: [{ key: 'load_kg', label: 'Нагрузка, кг', default: 30 }],
  torque_step: [{ key: 'step_kg', label: 'Шаг усилия, кг', default: 5 }],
}

const DESCRIPTIONS: Record<string, string> = {
  bar_mass: 'Гриф удерживается на месте, сила удержания в покое даёт массу грифа и подвижных частей.',
  friction: 'Медленные подъём и опускание; отклонение силы от массы — трение вверх/вниз.',
  inertia: 'Резкие разгоны и реверсы без нагрузки; регрессия силы по ускорению даёт приведённую инерцию ШВП.',
  backlash: 'Реверс на постоянной скорости; потерянный ход — люфт.',
  kg_factor: 'Подвесьте эталонный груз (на эмуляторе — виртуальная рука тянет вниз) и сравните с приростом силы.',
  weightless_drift: 'Невесомый гриф 5 с без касания: дрейф позиции и скорости.',
  hold_load: 'Тренировка с заданной нагрузкой, виртуальный пользователь держит гриф неподвижно — контроль дрейфа.',
  accel_reverse: 'Разгон/реверс без нагрузки: пиковое ускорение, сила приводов, рассинхрон.',
  sync_sweep: 'Синхронный ход вверх-вниз: максимальный рассинхрон сторон.',
  failure: 'Виртуальный пользователь «отказывает» после 2 повторов — проверка страховки.',
  jerk: 'Виртуальный пользователь дёргает гриф — проверка ограничений скорости и синхронизации.',
  torque_step: 'Шаг усилия в невесомом режиме — время отклика регулятора.',
}

export function ProceduresPanel({ serviceMode, procedure }: { serviceMode: boolean; procedure: HardwareProcedureStatus | null }) {
  const schema = useTuningStore((state) => state.schema)
  const runProcedure = useTuningStore((state) => state.runProcedure)
  const abort = useTuningStore((state) => state.abortProcedure)
  const setPending = useTuningStore((state) => state.setPending)
  const apply = useTuningStore((state) => state.apply)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const [args, setArgs] = useState<Record<string, Record<string, number>>>({})
  const [accepted, setAccepted] = useState(false)
  const running = procedure?.status === 'running'

  if (!schema) return null

  const acceptSuggested = async (suggested: Record<string, unknown>) => {
    for (const [key, value] of Object.entries(suggested)) setPending(key, value)
    await apply('persist', selectedUserId)
    setAccepted(true)
  }

  const renderList = (title: string, items: { id: string; label: string }[]) => (
    <div className="glass-panel rounded-2xl p-4">
      <h3 className="mb-3 text-sm font-semibold text-[#f2cf87]">{title}</h3>
      <ul className="space-y-2">
        {items.map((item) => {
          const spec = PROCEDURE_ARGS[item.id] ?? []
          const isActive = procedure?.name === item.id && running
          return (
            <li key={item.id} className={cn('rounded-xl border border-white/8 p-3', isActive && 'border-[#f2cf87]/50')}>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex-1">
                  <div className="text-sm font-medium text-white">{item.label}</div>
                  <div className="text-xs text-white/45">{DESCRIPTIONS[item.id]}</div>
                </div>
                {spec.map((arg) => (
                  <label key={arg.key} className="flex items-center gap-1 text-[11px] text-white/50">
                    {arg.label}
                    <input
                      type="number"
                      aria-label={`${item.label}: ${arg.label}`}
                      className="w-20 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-right font-mono text-xs text-white"
                      value={args[item.id]?.[arg.key] ?? arg.default}
                      onChange={(event) => setArgs((prev) => ({ ...prev, [item.id]: { ...prev[item.id], [arg.key]: Number(event.target.value) } }))}
                    />
                  </label>
                ))}
                <Button
                  variant="secondary"
                  className="px-3 py-1.5 text-xs"
                  iconLeft={isActive ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                  disabled={!serviceMode || running}
                  onClick={() => {
                    setAccepted(false)
                    const provided = Object.fromEntries(spec.map((arg) => [arg.key, args[item.id]?.[arg.key] ?? arg.default]))
                    void runProcedure(item.id, provided, selectedUserId)
                  }}
                >
                  Запустить
                </Button>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )

  const suggested = (procedure?.result?.suggested as Record<string, unknown> | undefined) ?? undefined

  return (
    <div className="space-y-4">
      {!serviceMode && <div className="rounded-2xl border border-[#ffd166]/30 bg-[#3d2f10]/40 p-3 text-xs text-[#ffd166]">Процедуры запускаются только в сервисном режиме. Все — на низких скоростях, через safety-gate, СТОП всегда доступен.</div>}
      <div className="glass-panel rounded-2xl p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1">
            <div className="text-xs text-white/40">Текущая процедура</div>
            <div className="text-sm font-semibold text-white">{procedure?.label || '—'}</div>
            <div className="text-xs text-white/50">{procedure?.step || (procedure?.status === 'done' ? 'Завершено' : procedure?.status === 'failed' ? 'Ошибка' : 'ожидание')}</div>
          </div>
          <span className={cn('rounded-full px-3 py-1 text-xs', running ? 'bg-[#f2cf87]/20 text-[#f2cf87]' : procedure?.status === 'done' ? 'bg-[#9be29b]/20 text-[#9be29b]' : procedure?.status === 'failed' ? 'bg-[#ff6b6b]/20 text-[#ff8f84]' : 'bg-white/5 text-white/40')}>
            {procedure?.status ?? 'idle'} · {procedure?.progressTicks ?? 0} тактов
          </span>
          <Button variant="danger" className="px-3 py-1.5 text-xs" iconLeft={<Square size={14} />} disabled={!running} onClick={() => void abort()}>
            Прервать
          </Button>
        </div>
        {procedure?.result && (
          <div className="mt-3 rounded-xl bg-black/30 p-3">
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-white/75">{JSON.stringify(procedure.result, null, 2)}</pre>
            {suggested && Object.keys(suggested).length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-xs text-white/50">Предложенные значения: {Object.entries(suggested).map(([key, value]) => `${key} = ${String(value)}`).join(', ')}</span>
                <Button className="px-3 py-1.5 text-xs" iconLeft={<Check size={14} />} disabled={!serviceMode || accepted} onClick={() => void acceptSuggested(suggested)}>
                  {accepted ? 'Принято' : 'Принять и сохранить'}
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {renderList('Мастера измерения', schema.procedures.measurements)}
        {renderList('Тестовые сценарии', schema.procedures.scenarios)}
      </div>
    </div>
  )
}
