import {
  Activity,
  Anchor,
  BarChart3,
  CheckCircle2,
  Cpu,
  DatabaseBackup,
  Feather,
  FlaskConical,
  Gauge,
  Hand,
  HeartPulse,
  Home,
  Layers3,
  OctagonX,
  ParkingSquare,
  RotateCcw,
  SlidersHorizontal,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTuningStore } from '@/features/hardware/lib/use-tuning-store'
import { fetchModbusPositions, stopRaisePosition, zeroModbusPositions } from '@/features/modbus/api/modbus-api'
import type { ModbusPositions, ModbusReadiness } from '@/features/modbus/model/types'
import type { HardwareDriveTelemetry } from '@/features/hardware/model/types'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { LivePanel, useTelemetryDebugStream } from './tabs/live-panel'
import { ParametersPanel } from './tabs/parameters-panel'
import { PresetsPanel } from './tabs/presets-panel'
import { ProceduresPanel } from './tabs/procedures-panel'
import { RecordingsPanel } from './tabs/recordings-panel'

type Tab = 'params' | 'live' | 'procedures' | 'presets' | 'recordings'

type DriveFeedback = ModbusPositions

const EMPTY_READINESS: ModbusReadiness = {
  communicationReady: false, encoderReady: false, torqueControlReady: false, motionSafetyReady: false,
  degradedManualMode: true, allowEncoderRead: false, allowZeroOffset: false, allowStatusRead: false,
  allowManualTorqueTest: false, allowAutomaticMotion: false, allowPositionAutoMove: false,
  allowProgramWorkout: false, allowHoming: false, noBrake: true, noLimitSwitches: true,
  noHardwareStop: true, noHardwareSync: true, warning: '',
}

const EMPTY_FEEDBACK: DriveFeedback = {
  connected: false, simulationMode: false, zeroed: false, zeroGeneration: 0,
  readiness: EMPTY_READINESS,
  left: { slaveId: 1, currentPulses: null, zeroPulses: null, positionMm: null },
  right: { slaveId: 2, currentPulses: null, zeroPulses: null, positionMm: null },
  skewMm: null, error: null,
}

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'params', label: 'Параметры', icon: SlidersHorizontal },
  { id: 'live', label: 'Live-телеметрия', icon: Activity },
  { id: 'procedures', label: 'Сценарии и мастера', icon: FlaskConical },
  { id: 'presets', label: 'Пресеты', icon: Layers3 },
  { id: 'recordings', label: 'Записи и чёрный ящик', icon: DatabaseBackup },
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
  const emulatorMode = snapshot?.emulatorMode ?? false
  const [feedback, setFeedback] = useState<DriveFeedback>(EMPTY_FEEDBACK)
  const [zeroing, setZeroing] = useState(false)
  const [zeroError, setZeroError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)
  const [stopResult, setStopResult] = useState<string | null>(null)
  const pollEpoch = useRef(0)
  const showModbus = feedback.connected && (!feedback.simulationMode || !emulatorMode)

  const zeroPosition = async () => {
    ++pollEpoch.current
    setZeroing(true)
    setZeroError(null)
    try {
      const result = await zeroModbusPositions()
      setFeedback(result)
    } catch (error) {
      setZeroError(error instanceof Error ? error.message : 'Не удалось обнулить оба энкодера')
    } finally {
      setZeroing(false)
    }
  }

  const softwareStop = async () => {
    setStopping(true)
    setStopResult(null)
    try {
      const result = await stopRaisePosition()
      setStopResult(`Управляемый подъём до ${result.targetMm} мм, лимит ${result.torqueLimit}, скорость ${result.speedRpm} об/мин. Только симуляция; не аппаратный E-STOP.`)
    } catch (error) {
      setStopResult(`Остановка НЕ подтверждена: ${error instanceof Error ? error.message : String(error)}. Используйте аппаратный E-STOP.`)
    } finally {
      setStopping(false)
    }
  }

  useEffect(() => {
    let disposed = false
    let reading = false
    const refresh = async () => {
      if (reading || zeroing) return
      reading = true
      const epoch = pollEpoch.current
      try {
        const result = await fetchModbusPositions()
        if (!disposed && epoch === pollEpoch.current) setFeedback(result)
      } catch {
        if (!disposed && epoch === pollEpoch.current) setFeedback(EMPTY_FEEDBACK)
      } finally {
        reading = false
      }
    }
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 1000)
    return () => { disposed = true; window.clearInterval(timer) }
  }, [zeroing])

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
      <div className="mechanics-tuning-screen flex flex-col gap-4" data-testid="mechanics-tuning-screen">
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

        {control?.adapter === 'modbus-rtu' && (
          <div role="status" className="rounded-xl border border-[#ffd166]/30 bg-[#3d2f10]/40 px-4 py-3 text-sm text-[#ffd166]">
            {feedback.readiness.warning || 'Автоматическое движение отключено: контур безопасности Modbus не проверен (E-CTRL-UNAVAILABLE). Программный STOP не заменяет аппаратный E-STOP.'}
            <div>Связь: {feedback.readiness.communicationReady ? 'есть' : 'нет'} · Энкодеры: {feedback.readiness.encoderReady ? 'доступны' : 'недоступны'} · Тест момента: {feedback.readiness.allowManualTorqueTest ? 'доступен' : 'не подтверждён'} · Автоматическое движение: запрещено</div>
          </div>
        )}

        <div className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl p-3">
          <Button variant="secondary" iconLeft={<RotateCcw size={14} />} disabled={!feedback.readiness.allowZeroOffset || zeroing}
            onClick={() => { void zeroPosition() }}>
            {zeroing ? 'Обнуляю...' : 'Обнулить позицию'}
          </Button>
          <span className="text-xs text-white/50">Программный ноль двух приводов · без записи в энкодеры · при каждом запуске снимается заново</span>
          {zeroError && <span role="alert" className="text-xs text-[#ff8f84]">{zeroError}</span>}
          {!feedback.zeroed && showModbus && <span role="status" className="text-xs text-[#ffd166]">{feedback.error ?? 'Нулевая позиция ещё не задана'}</span>}
          <Button variant="danger" disabled={!feedback.simulationMode || stopping} onClick={() => {
            if (window.confirm('STOP выполняет управляемый подъём грифа вверх до 2000 мм. Это не заменяет аппаратный E-STOP. Продолжить в симуляции?')) void softwareStop()
          }}>
            {stopping ? 'Отправляю...' : 'STOP · управляемый подъём (не E-STOP)'}
          </Button>
          {stopResult && <span role="alert" className="text-xs text-[#ff8f84]">{stopResult}</span>}
        </div>

        <ControlOverview control={control} estop={estop} drives={snapshot?.drives ?? []} feedback={feedback} emulatorMode={emulatorMode} showModbus={showModbus} />

        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Feather size={14} />} disabled={estop || feedback.connected} onClick={() => command('enter_weightless', { mode: 'service' })}>Невесомый гриф</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Hand size={14} />} disabled={estop || feedback.connected} onClick={() => command('hold')}>Удержать</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<ParkingSquare size={14} />} disabled={estop || feedback.connected} onClick={() => command('park')}>Парковка</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Home size={14} />} disabled={estop || feedback.connected || (control?.adapter === 'modbus-rtu' && !feedback.readiness.allowHoming)} onClick={() => command('home', { mode: 'homing' })}>Homing</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<Anchor size={14} />} disabled={estop} onClick={() => command('run_self_test')}>Самотест</Button>
          <Button variant="secondary" className="px-3 py-1.5 text-xs" iconLeft={<RotateCcw size={14} />} onClick={() => command(control?.mode === 'fault' ? 'reset_fault' : 'complete_set')}>{control?.mode === 'fault' ? 'Сбросить ошибку' : 'Завершить подход'}</Button>
          {estop ? (
            <Button variant="danger" className="px-3 py-1.5 text-xs" iconLeft={<OctagonX size={14} />} onClick={() => command('clear_emergency_stop')}>Снять СТОП</Button>
          ) : (
            <Button variant="danger" className="px-3 py-1.5 text-xs" iconLeft={<OctagonX size={14} />} onClick={() => { if (feedback.connected) void softwareStop(); else command('trigger_emergency_stop') }}>СТОП</Button>
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
                  'flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium transition',
                  tab === item.id ? 'border border-[#b5852f]/50 bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/40 hover:bg-white/6 hover:text-white',
                )}
              >
                <item.icon size={15} aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          {tab === 'params' && <ParametersPanel serviceMode={serviceMode} />}
          {tab === 'live' && <LivePanel control={control} emulatorMode={emulatorMode} positionMm={showModbus && feedback.left.positionMm != null && feedback.right.positionMm != null ? (feedback.left.positionMm + feedback.right.positionMm) / 2 : showModbus ? null : undefined} />}
          {tab === 'procedures' && <ProceduresPanel serviceMode={serviceMode} procedure={procedure} />}
          {tab === 'presets' && <PresetsPanel serviceMode={serviceMode} />}
          {tab === 'recordings' && <RecordingsPanel />}
        </div>
      </div>
    </FormaShell>
  )
}

type ControlState = NonNullable<ReturnType<typeof useHardwareStore.getState>['snapshot']>['control']

function ControlOverview({ control, estop, drives, feedback, emulatorMode, showModbus }: { control: ControlState | null | undefined; estop: boolean; drives: HardwareDriveTelemetry[]; feedback: DriveFeedback; emulatorMode: boolean; showModbus: boolean }) {
  const lower = control?.config.lowerMm ?? 0
  const upper = control?.config.upperMm ?? 1
  const positionProgress = !showModbus && emulatorMode && control ? toPercent(control.positionMm, lower, upper) : undefined
  const barMm = feedback.left.positionMm != null && feedback.right.positionMm != null ? (feedback.left.positionMm + feedback.right.positionMm) / 2 : null
  const actualSyncMm = feedback.skewMm != null ? Math.abs(feedback.skewMm) : null
  const loadScale = control ? Math.max(control.loadTargetKg, control.loadEffectiveKg, 1) : 1
  const loadProgress = control ? toPercent(control.loadEffectiveKg, 0, loadScale) : 0
  const syncProgress = showModbus ? (actualSyncMm != null ? toPercent(actualSyncMm, 0, 8) : undefined) : (control ? toPercent(control.syncDeltaMm, 0, 8) : undefined)
  const syncTone = control?.syncStatus === 'critical' ? 'bad' : control?.syncStatus === 'warning' ? 'warn' : 'good'
  const ready = Boolean(control?.heartbeatOk && control.commOk && control.powerOk && !estop && !control.faultCode)

  return (
    <section aria-label="Состояние механики" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      <IndicatorCard
        icon={Activity}
        label="Режим"
        value={control ? MODE_LABELS[control.mode] ?? control.mode : '—'}
        detail={control?.label ?? 'Нет данных'}
        tone={control?.mode === 'fault' || estop ? 'bad' : 'good'}
      />
      <IndicatorCard
        icon={Gauge}
        label="Позиция грифа"
        value={showModbus ? (barMm != null ? `${barMm.toFixed(4)} мм` : 'Нет данных') : (emulatorMode && control ? `${control.positionMm.toFixed(1)} мм` : 'Нет данных')}
        detail={showModbus ? 'От программного нуля · среднее PA_1BD:PA_1BC · 0,0032 мм/имп' : (emulatorMode ? `${lower.toFixed(0)} — ${upper.toFixed(0)} мм · модель` : 'Нет связи с приводами')}
        progress={positionProgress}
      />
      {(['left', 'right'] as const).map((side) => {
        const drive = drives.find((item) => item.side === side)
        const positionMm = feedback[side].positionMm
        return (
          <IndicatorCard key={side} icon={Cpu} label={`${side === 'left' ? 'Левый' : 'Правый'} драйвер`}
            value={showModbus ? (positionMm != null ? `${positionMm.toFixed(4)} мм` : 'Нет данных') : (emulatorMode && drive ? `${drive.positionMm.toFixed(1)} мм` : 'Нет данных')}
            detail={showModbus ? `Ноль ${feedback[side].zeroPulses ?? '—'} имп · Slave ID ${feedback[side].slaveId} · PA_1BD:PA_1BC` : (emulatorMode ? (drive ? `Модель · ${drive.status} · ${drive.currentA.toFixed(1)} А` : 'Модель · нет данных') : 'Нет связи с приводом')}
            tone={showModbus ? (positionMm == null ? 'bad' : 'good') : (emulatorMode && drive?.connected ? 'good' : 'bad')} />
        )
      })}
      <IndicatorCard
        icon={BarChart3}
        label="Нагрузка"
        value={control ? `${control.loadEffectiveKg.toFixed(1)} кг` : '—'}
        detail={control ? `цель ${control.loadTargetKg.toFixed(1)} кг · усилие ${control.userForceKg.toFixed(1)} кг` : 'Нет данных'}
        progress={loadProgress}
      />
      <IndicatorCard
        icon={SlidersHorizontal}
        label="Рассинхрон"
        value={showModbus ? (feedback.skewMm != null ? `${feedback.skewMm.toFixed(1)} мм` : 'Нет данных') : (control ? `${control.syncDeltaMm.toFixed(2)} мм` : '—')}
        detail={showModbus ? 'Факт Modbus · разница двух приводов' : (control ? (control.syncStatus === 'critical' ? 'Критический' : control.syncStatus === 'warning' ? 'Предупреждение' : 'В пределах нормы') : 'Нет данных')}
        progress={syncProgress}
        tone={showModbus ? undefined : syncTone}
      />
      <IndicatorCard
        icon={RotateCcw}
        label="Движение"
        value={control ? `${control.velocityMmPerSec.toFixed(0)} мм/с` : '—'}
        detail={control ? `${control.repetitionCount} повт. · ${control.tempoLabel}` : 'Скорость и повторы'}
      />
      <IndicatorCard
        icon={ready ? CheckCircle2 : HeartPulse}
        label="Системы"
        value={ready ? 'Готовы' : 'Проверить'}
        detail={control ? `${control.heartbeatOk ? 'Связь есть' : 'Нет heartbeat'} · тормоза ${control.brakeEngaged ? 'зажаты' : 'сняты'}` : 'Нет данных'}
        tone={ready ? 'good' : 'bad'}
      />
      {control?.faultCode ? (
        <div className="rounded-2xl border border-[#ff8f84]/40 bg-[#3d1010]/45 px-4 py-3 text-xs text-[#ff8f84] sm:col-span-2 xl:col-span-6">
          Ошибка: <span className="font-mono font-semibold">{control.faultCode}</span>
        </div>
      ) : null}
    </section>
  )
}

function IndicatorCard({ icon: Icon, label, value, detail, progress, tone }: { icon: LucideIcon; label: string; value: string; detail: string; progress?: number; tone?: 'good' | 'warn' | 'bad' }) {
  const indicatorColor = tone === 'bad' ? 'bg-[#ff8f84]' : tone === 'warn' ? 'bg-[#ffd166]' : tone === 'good' ? 'bg-[#79de83]' : 'bg-[#d6b05f]'

  return (
    <div className="glass-panel min-w-0 rounded-2xl p-3">
      <div className="flex items-center gap-2 text-[11px] text-white/40">
        <Icon size={14} className={cn(tone === 'bad' && 'text-[#ff8f84]', tone === 'warn' && 'text-[#ffd166]', tone === 'good' && 'text-[#79de83]')} aria-hidden="true" />
        <span>{label}</span>
        {tone ? <span className={cn('ml-auto h-2 w-2 rounded-full shadow-[0_0_8px_currentColor]', tone === 'bad' && 'text-[#ff8f84] bg-[#ff8f84]', tone === 'warn' && 'text-[#ffd166] bg-[#ffd166]', tone === 'good' && 'text-[#79de83] bg-[#79de83]')} aria-hidden="true" /> : null}
      </div>
      <div className="mt-1 truncate font-mono text-sm font-semibold text-white/90" title={value}>{value}</div>
      {progress !== undefined ? (
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/8" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress)}>
          <div className={cn('h-full rounded-full transition-[width] duration-300', indicatorColor)} style={{ width: `${progress}%` }} />
        </div>
      ) : null}
      <div className="mt-1.5 truncate text-[10px] text-white/35" title={detail}>{detail}</div>
    </div>
  )
}

function toPercent(value: number, min: number, max: number) {
  if (!Number.isFinite(value) || max <= min) return 0
  return Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100))
}
