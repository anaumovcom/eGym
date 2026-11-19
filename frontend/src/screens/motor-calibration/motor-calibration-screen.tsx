import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { CalibrationsTab } from './calibrations-tab'
import { ParametersTab } from './parameters-tab'
import { ExerciseObservations } from './exercise-observations'
import { FrictionArchiveTab } from './friction-archive'
import { MeasurementArchiveTab } from './measurement-archive'
import './motor-calibration-screen.css'

type Tab = 'calibrations' | 'friction' | 'plots' | 'parameters' | 'observations'

const TABS: { id: Tab; label: string }[] = [
  { id: 'calibrations', label: 'Калибровки' },
  { id: 'friction', label: 'Карта ШВП' },
  { id: 'plots', label: 'Графики замеров' },
  { id: 'parameters', label: 'Параметры' },
  { id: 'observations', label: 'Записи упражнений' },
]

const MOTION_LABELS: Record<string, string> = {
  idle: 'Покой', support: 'Поддержка', parked: 'На упорах', moving: 'Перемещение',
  weightless: 'Невесомость', training: 'Тренировка', start_hold: 'Удержание на старте',
  fixed_hold: 'Удержание высоты', calibration: 'Калибровка', fault: 'Авария',
  estop: 'Аварийная остановка', stopped: 'Остановлен',
}

function Chip({ label, value, tone }: { label: string; value: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }) {
  return (
    <div className="cal-readout" data-tone={tone}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

export function MotorCalibrationScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [runLocked, setRunLocked] = useState(false)
  const tab = TABS.find(item => item.id === searchParams.get('tab'))?.id ?? 'calibrations'
  const reviewing = tab === 'friction' || tab === 'plots'
  const snapshot = useHardwareStore((state) => state.snapshot)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'

  const serviceMode = Boolean(snapshot?.serviceMode)
  const control = snapshot?.control
  const servo = control?.servo
  const servoOn = Boolean(servo?.left && servo?.right)
  const connectionStatus = useHardwareStore((state) => state.connectionStatus)
  const connectionLost = connectionStatus === 'disconnected' || connectionStatus === 'error'
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
      machine={snapshot?.machine ?? { machineState: 'warning', machineLabel: 'Ожидание данных тренажёра', safety: 'enabled', leftDrive: 'warning', rightDrive: 'warning', calibration: '—' }}
      onStop={() => { void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId }) }}
    >
      <div className="cal-console">
        <header className={reviewing ? 'cal-hero bs-service-header' : 'cal-hero'}>
          <div>
            <Link to="/settings?tab=service"><ArrowLeft size={15} aria-hidden="true" /> Сервис</Link>
            <h1>Калибровки тренажёра</h1>
            {!reviewing && <p>Настройте вес, плавность хода и разворот грифа под ощущение обычного Смита.</p>}
          </div>
          <div className="cal-tabs" role="tablist" aria-label="Разделы">
            {TABS.map(item => <button
              key={item.id} type="button" role="tab" id={`motor-tab-${item.id}`}
              aria-controls="motor-tab-content" aria-selected={tab === item.id}
              disabled={runLocked && tab !== item.id}
              onClick={() => setSearchParams(prev => { const next = new URLSearchParams(prev); next.set('tab', item.id); return next })}
            >{item.label}</button>)}
          </div>
        </header>

        {!reviewing && <section className="cal-surface" aria-label="Состояние тренажёра">
          <div className="cal-workspace-heading">
            <h2>Состояние тренажёра</h2>
            <div className="cal-actions" role="group" aria-label="Управление сервисным режимом и приводами">
              <Button variant="secondary" className="py-2" onClick={() => void toggleService()} disabled={calibrating || runLocked}>
                {serviceMode ? 'Выключить сервисный режим' : 'Включить сервисный режим'}
              </Button>
              {serviceMode && <Button variant="secondary" className="py-2" onClick={() => void setServo(!servoOn)} disabled={calibrating || runLocked}>
                {servoOn ? 'Выключить приводы' : 'Включить приводы'}
              </Button>}
            </div>
          </div>
          {connectionLost ? <p data-tone="warn">Нет связи. Показан последний полученный снимок.</p> : !snapshot ? <p>Телеметрия ещё не получена.</p> : null}
          <dl className="cal-readouts">
            <Chip label="Источник данных" value={control?.adapter === 'twin' ? 'Цифровой двойник' : control?.adapter === 'modbus-torque' ? 'Приводы Modbus' : control?.adapter === 'canopen-torque' ? 'Приводы CANopen' : 'Нет данных'} tone="neutral" />
            <Chip label="Сервисный режим" value={snapshot ? serviceMode ? 'Включён' : 'Выключен' : 'Нет данных'} tone={serviceMode ? 'good' : 'neutral'} />
            <Chip label="Левый привод" value={servo?.left == null ? 'Нет данных' : servo.left ? 'Серво ON' : 'Серво OFF'} tone={servo?.left ? 'good' : 'neutral'} />
            <Chip label="Правый привод" value={servo?.right == null ? 'Нет данных' : servo.right ? 'Серво ON' : 'Серво OFF'} tone={servo?.right ? 'good' : 'neutral'} />
            <Chip label="Режим движения" value={estop ? 'СТОП' : control?.mode ? MOTION_LABELS[control.mode] ?? control.mode : '—'} tone={estop || control?.faultCode ? 'bad' : 'neutral'} />
            <Chip label="Положение" value={control ? `${control.positionMm.toFixed(1)} мм` : '—'} tone="neutral" />
          </dl>
        </section>}

        <div className="min-w-0" id="motor-tab-content" role="tabpanel" aria-labelledby={`motor-tab-${tab}`}>
          {tab === 'calibrations' ? <CalibrationsTab serviceMode={serviceMode} onLock={setRunLocked} /> : tab === 'observations'
            ? <ExerciseObservations adapter={control?.adapter} /> : tab === 'friction' ? <FrictionArchiveTab activeAdapter={control?.adapter} />
              : tab === 'plots' ? <MeasurementArchiveTab activeAdapter={control?.adapter} />
              : <ParametersTab serviceMode={serviceMode} calibrating={calibrating} />}
        </div>
      </div>
    </FormaShell>
  )
}
