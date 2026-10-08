import { useSearchParams } from 'react-router-dom'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { CalibrationsTab } from './calibrations-tab'
import { ParametersTab } from './parameters-tab'

type Tab = 'calibrations' | 'parameters'

const TABS: { id: Tab; label: string }[] = [
  { id: 'calibrations', label: 'Калибровки' },
  { id: 'parameters', label: 'Параметры' },
]

function Chip({ label, value, tone }: { label: string; value: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const color = { good: 'text-[#79de83]', warn: 'text-[#f2cf87]', bad: 'text-[#ff8f84]', neutral: 'text-white' }[tone]
  return (
    <div className="rounded-[16px] border border-white/8 bg-white/4 px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.12em] text-white/35">{label}</p>
      <p className={cn('text-sm font-medium', color)}>{value}</p>
    </div>
  )
}

export function MotorCalibrationScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab: Tab = searchParams.get('tab') === 'parameters' ? 'parameters' : 'calibrations'
  const snapshot = useHardwareStore((state) => state.snapshot)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'

  const serviceMode = Boolean(snapshot?.serviceMode)
  const control = snapshot?.control
  const servo = control?.servo
  const servoOn = Boolean(servo?.left && servo?.right)
  const estop = snapshot?.safety.state === 'emergency_stop'
  const calibrating = control?.mode === 'calibration'

  const toggleService = async () => {
    try { await runCommand({ action: 'toggle_service_mode', userId: selectedUserId, serviceMode: !serviceMode }) } catch { /* shown by the store */ }
  }
  const setServo = async (on: boolean) => {
    const warning = on
      ? 'Включить оба привода (SRV-ON)? Приводы сразу дадут момент поддержки вверх.'
      : 'Выключить оба привода? Поднятый гриф упадёт: тормоза нет. Убедитесь, что гриф лежит на упорах.'
    if (!window.confirm(warning)) return
    try { await runCommand({ action: on ? 'servo_on' : 'servo_off', userId: selectedUserId, serviceMode: true }) } catch { /* shown by the store */ }
  }

  return (
    <FormaShell
      userName={userName}
      machine={snapshot?.machine ?? { machineState: 'ready', machineLabel: 'Калибровка', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: '—' }}
      onStop={() => { void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId }) }}
    >
      <div className="flex flex-col gap-6">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-[#f4dfb4]">Калибровки привода</h1>
            <p className="mt-1 max-w-2xl text-sm text-white/45">
              Измерение параметров моторов и механики. Калибровка идёт, пока вы удерживаете кнопку; результат применяется только после сохранения.
            </p>
          </div>
          <div className="flex flex-wrap items-stretch gap-2">
            <Chip label="Сервисный режим" value={serviceMode ? 'включён' : 'выключен'} tone={serviceMode ? 'good' : 'warn'} />
            <Chip label="Приводы" value={servo ? `Л ${servo.left ? 'ON' : 'OFF'} · П ${servo.right ? 'ON' : 'OFF'}` : 'нет данных'} tone={servoOn ? 'good' : 'warn'} />
            <Chip label="Режим" value={estop ? 'СТОП' : calibrating ? 'калибровка' : control?.mode ?? '—'} tone={estop || control?.faultCode ? 'bad' : calibrating ? 'warn' : 'neutral'} />
            {control ? <Chip label="Положение" value={`${control.positionMm.toFixed(1)} мм`} tone="neutral" /> : null}
          </div>
        </header>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" className="py-2" onClick={() => void toggleService()} disabled={calibrating}>
            {serviceMode ? 'Выключить сервисный режим' : 'Включить сервисный режим'}
          </Button>
          {serviceMode ? (
            <Button variant="secondary" className="py-2" onClick={() => void setServo(!servoOn)} disabled={calibrating}>
              {servoOn ? 'Выключить приводы' : 'Включить приводы'}
            </Button>
          ) : null}
        </div>

        <div className="flex gap-1" role="tablist" aria-label="Разделы">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setSearchParams({ tab: item.id })}
              className={cn(
                'rounded-xl px-5 py-2 text-sm font-medium transition',
                tab === item.id ? 'border border-[#b5852f]/50 bg-[#b5852f]/30 text-[#f4dfb4]' : 'text-white/45 hover:bg-white/6 hover:text-white',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        {tab === 'calibrations' ? <CalibrationsTab serviceMode={serviceMode} /> : <ParametersTab serviceMode={serviceMode} calibrating={calibrating} />}
      </div>
    </FormaShell>
  )
}
