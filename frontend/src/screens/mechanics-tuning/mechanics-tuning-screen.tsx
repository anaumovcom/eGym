import { Anchor, Feather, Hand, Home, OctagonX, ParkingSquare, RotateCcw, Wrench } from 'lucide-react'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { EmulatorPanel } from './tabs/emulator-panel'
import { LivePanel, useTelemetryDebugStream } from './tabs/live-panel'
import { ParametersPanel } from './tabs/parameters-panel'
import { PresetsPanel } from './tabs/presets-panel'
import { ProceduresPanel } from './tabs/procedures-panel'
import { RecordingsPanel } from './tabs/recordings-panel'

type Tab = 'params' | 'live' | 'procedures' | 'presets' | 'recordings' | 'emulator'

const TABS: { id: Tab; label: string }[] = [
  { id: 'params', label: 'Параметры' },
  { id: 'live', label: 'Live-телеметрия' },
  { id: 'procedures', label: 'Сценарии и мастера' },
  { id: 'presets', label: 'Пресеты' },
  { id: 'recordings', label: 'Записи и чёрный ящик' },
  { id: 'emulator', label: 'Эмулятор' },
]

function asTab(value: string | null): Tab {
  return TABS.find((tab) => tab.id === value)?.id ?? 'params'
}

const MODE_LABELS: Record<string, string> = {
  idle: 'Готов',
  post: 'Самотест',
  homing: 'Homing',
  moving: 'Перемещение',
  weightless: 'Невесомый гриф',
  start_hold: 'Ожидание захвата',
  training: 'Тренировка',
  fixed_hold: 'Фиксация',
  isometric: 'Изометрия',
  paused: 'Удержание',
  parked: 'Запаркован',
  estop: 'СТОП',
  fault: 'Ошибка',
}

export function MechanicsTuningScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = asTab(searchParams.get('tab'))
  const snapshot = useHardwareStore((state) => state.snapshot)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'
  const loadSchema = useTuningStore((state) => state.loadSchema)
  const loadTuning = useTuningStore((state) => state.loadTuning)
  const loadEvents = useTuningStore((state) => state.loadEvents)
  const errorMessage = useTuningStore((state) => state.errorMessage)
  const setError = useTuningStore((state) => state.setError)
  const setProcedure = useTuningStore((state) => state.setProcedure)
  const procedure = useTuningStore((state) => state.procedure)

  const serviceMode = snapshot?.serviceMode ?? false
  const control = snapshot?.control ?? null
  const estop = snapshot?.safety.state === 'emergency_stop'

  useTelemetryDebugStream(true)

  useEffect(() => {
    void loadSchema()
    void loadTuning()
    void loadEvents()
  }, [loadSchema, loadTuning, loadEvents])

  useEffect(() => {
    if (snapshot?.procedure) setProcedure(snapshot.procedure)
  }, [snapshot?.procedure, setProcedure])

  useEffect(() => {
    void loadTuning()
  }, [serviceMode, loadTuning])

  const command = (action: string, extra: Record<string, unknown> = {}) => {
    void runCommand({ action, userId: selectedUserId, ...extra }).catch(() => undefined)
  }

  return (
    <FormaShell
      userName={userName}
      machine={snapshot?.machine ?? { machineState: 'ready', machineLabel: 'Механика', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: '—' }}
      onStop={() => command('trigger_emergency_stop')}
    >
      <div className="flex flex-col gap-4" data-testid="mechanics-tuning-screen">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#b5852f]/20 text-[#f2cf87]">
            <Wrench size={20} />
          </div>
          <div className="flex-1">
            <h1 className="font-display text-xl font-bold tracking-tight text-[#f4dfb4]">Механика · отладка и настройка</h1>
            <p className="text-xs text-white/30">Реестр параметров · live-телеметрия · мастера измерения · чёрный ящик · адаптер {control?.adapter ?? '—'}</p>
          </div>
          <Button
            variant={serviceMode ? 'primary' : 'secondary'}
            className="text-xs"
            iconLeft={<Wrench size={14} />}
            onClick={() => command('toggle_service_mode', { serviceMode: !serviceMode })}
          >
            {serviceMode ? 'Сервисный режим: ВКЛ' : 'Включить сервисный режим'}
          </Button>
        </div>

        {!serviceMode && (
          <div className="rounded-2xl border border-[#ffd166]/30 bg-[#3d2f10]/40 px-4 py-2 text-xs text-[#ffd166]">
            Просмотр доступен всегда. Изменение параметров, запуск процедур и импорт пресетов — только в сервисном режиме. Временные значения автоматически откатываются при выходе из него, СТОП или потере связи.
          </div>
        )}
        {(errorMessage || hardwareError) && (
          <div className="flex items-center justify-between rounded-2xl border border-[#ff8f84]/40 bg-[#3d1010]/60 px-4 py-2 text-xs text-[#ff8f84]" role="alert">
            <span>{errorMessage ?? hardwareError}</span>
            <button type="button" className="text-white/50 hover:text-white" onClick={() => setError(null)}>скрыть</button>
          </div>
        )}

        <div className="glass-panel flex flex-wrap items-center gap-x-5 gap-y-2 rounded-2xl px-4 py-3 text-xs">
          <Stat label="Режим" value={control ? `${MODE_LABELS[control.mode] ?? control.mode} · ${control.label}` : '—'} tone={control?.mode === 'fault' || estop ? 'bad' : undefined} />
          <Stat label="Позиция" value={control ? `${control.positionMm.toFixed(1)} мм` : '—'} />
          <Stat label="Скорость" value={control ? `${control.velocityMmPerSec.toFixed(0)} мм/с` : '—'} />
          <Stat label="Усилие" value={control ? `${control.userForceKg.toFixed(1)} кг` : '—'} />
          <Stat label="Нагрузка" value={control ? `${control.loadEffectiveKg.toFixed(1)} кг` : '—'} />
          <Stat label="Рассинхрон" value={control ? `${control.syncDeltaMm.toFixed(2)} мм` : '—'} tone={control?.syncStatus === 'critical' ? 'bad' : control?.syncStatus === 'warning' ? 'warn' : undefined} />
          <Stat label="Повторы" value={control ? `${control.repetitionCount}` : '—'} />
          <Stat label="Тормоза" value={control ? (control.brakeEngaged ? 'зажаты' : 'сняты') : '—'} />
          <Stat label="Heartbeat" value={control ? (control.heartbeatOk ? 'ок' : 'потерян') : '—'} tone={control && !control.heartbeatOk ? 'bad' : undefined} />
          {control?.faultCode && <Stat label="Ошибка" value={control.faultCode} tone="bad" />}
          {snapshot?.alerts?.length ? <Stat label="Предупреждения" value={snapshot.alerts.join(' · ')} tone="warn" /> : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Feather size={14} />} disabled={estop} onClick={() => command('enter_weightless', { mode: 'service' })}>Невесомый гриф</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Hand size={14} />} disabled={estop} onClick={() => command('hold')}>Удержать</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<ParkingSquare size={14} />} disabled={estop} onClick={() => command('park')}>Парковка</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Home size={14} />} disabled={estop} onClick={() => command('home', { mode: 'homing' })}>Homing</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Anchor size={14} />} disabled={estop} onClick={() => command('run_self_test')}>Самотест</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<RotateCcw size={14} />} onClick={() => command(control?.mode === 'fault' ? 'reset_fault' : 'complete_set')}>{control?.mode === 'fault' ? 'Сбросить ошибку' : 'Завершить подход'}</Button>
          {estop ? (
            <Button variant="danger" className="px-3 py-1.5 text-xs" iconLeft={<OctagonX size={14} />} onClick={() => command('clear_emergency_stop')}>Снять СТОП</Button>
          ) : (
            <Button variant="danger" className="px-3 py-1.5 text-xs" iconLeft={<OctagonX size={14} />} onClick={() => command('trigger_emergency_stop')}>СТОП</Button>
          )}
        </div>

        <div className="overflow-x-auto">
          <div className="flex min-w-max gap-1">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSearchParams({ tab: item.id })}
                className={cn(
                  'whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium transition',
                  tab === item.id ? 'border border-[#b5852f]/50 bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:bg-white/6 hover:text-white',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          {tab === 'params' && <ParametersPanel serviceMode={serviceMode} />}
          {tab === 'live' && <LivePanel control={control} />}
          {tab === 'procedures' && <ProceduresPanel serviceMode={serviceMode} procedure={procedure} />}
          {tab === 'presets' && <PresetsPanel serviceMode={serviceMode} />}
          {tab === 'recordings' && <RecordingsPanel />}
          {tab === 'emulator' && <EmulatorPanel />}
        </div>
      </div>
    </FormaShell>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'bad' | 'warn' }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-white/40">{label}:</span>
      <span className={cn('font-mono text-white/85', tone === 'bad' && 'text-[#ff8f84]', tone === 'warn' && 'text-[#ffd166]')}>{value}</span>
    </div>
  )
}
