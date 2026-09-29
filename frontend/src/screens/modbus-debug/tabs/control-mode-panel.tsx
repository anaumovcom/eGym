import { AlertTriangle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { fetchModbusPositions, stopRaisePosition } from '@/features/modbus/api/modbus-api'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import type { ControlMode } from '@/features/modbus/model/types'

export function ControlModePanel() {
  const { connectionStatus, paramStates, writeControlRegister, motorEnabled, setMotorEnabled, runCommand, controlTarget, setControlTarget, driveAddresses } = useModbusStore()
  const [activeMode, setActiveMode] = useState<ControlMode>('position')
  const [confirmMotorEnable, setConfirmMotorEnable] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<string | null>(null)
  const [manualTorqueReady, setManualTorqueReady] = useState(false)

  useEffect(() => {
    let active = true
    const refresh = () => { void fetchModbusPositions().then((positions) => {
      if (active) setManualTorqueReady(positions.readiness.allowManualTorqueTest)
    }).catch(() => { if (active) setManualTorqueReady(false) }) }
    refresh()
    const timer = window.setInterval(refresh, 1000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const isConnected = connectionStatus?.connected ?? false

  const modeVal = paramStates.get(0x002)?.driverValue
  const extVal = paramStates.get(0x090)?.driverValue
  const hasAlarm = (paramStates.get(0x200)?.driverValue ?? 0) !== 0

  const handleSetMode = async (mode: ControlMode) => {
    const modeCode = { position: 0, speed: 1, torque: 2 }[mode]
    setBusy('mode')
    try {
      await writeControlRegister(0x002, modeCode)
      await writeControlRegister(0x090, 1)
      setActiveMode(mode)
      setLastResult(`Режим ${mode} записан для ${controlTarget === 'both' ? 'обоих приводов' : controlTarget}. Необходим перезапуск драйвера.`)
    } catch (error) {
      setLastResult(`Ошибка записи: ${error instanceof Error ? error.message : String(error)}. Проверьте оба привода перед движением.`)
    } finally {
      setBusy(null)
    }
  }

  const handleCommand = async (cmd: string) => {
    if (!motorEnabled && cmd === 'servo_on') {
      setConfirmMotorEnable(true)
      return
    }
    setBusy(cmd)
    try {
      const result = await runCommand(cmd as 'servo_on' | 'servo_off' | 'alarm_reset' | 'emergency_stop' | 'pos_load' | 'jog_start' | 'jog_stop' | 'homing', true)
      setLastResult(result.success ? `Команда ${cmd}: OK` : `Ошибка: ${result.error}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl p-4 space-y-2">
        <p className="text-sm font-semibold text-[#f4dfb4]">Адресат команд управления</p>
        <div className="flex flex-wrap gap-2">
          {(['both', 'left', 'right'] as const).map((target) => (
            <button key={target} type="button" aria-pressed={controlTarget === target}
              className={cn('rounded-xl border px-4 py-2 text-sm', controlTarget === target ? 'border-[#b5852f] bg-[#b5852f]/30 text-[#f4dfb4]' : 'border-white/10 text-white/50')}
              onClick={() => setControlTarget(target)}>
              {target === 'both' ? `Оба · ID ${driveAddresses.left} и ${driveAddresses.right}` : `${target === 'left' ? 'Левый' : 'Правый'} · ID ${driveAddresses[target]}`}
            </button>
          ))}
        </div>
        <p className="text-xs text-[#ffd166]">Команды «Оба» отправляются каждому приводу отдельно. E-CTRL-UNAVAILABLE запрещает автоматическое движение. Ручной момент недоступен без проверенного Servo-OFF: программный STOP не заменяет аппаратный E-STOP.</p>
      </div>
      {/* Controlled STOP — never the hardware E-STOP */}
      <div className="rounded-2xl border border-[#ff8f84]/40 bg-[#3d1010]/60 p-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
          <div className="flex-1">
            <div className="font-bold text-[#ff8f84] flex items-center gap-2">
              <AlertTriangle size={16} />
              STOP · управляемый подъём
            </div>
            <p className="text-xs text-white/40 mt-1">
              STOP выполняет управляемый подъём грифа вверх. Это не заменяет аппаратный E-STOP. Только симуляция.
            </p>
          </div>
          <Button
            variant="danger"
            className="min-w-[160px]"
            onClick={() => {
              setBusy('stop_raise')
              void stopRaisePosition().then((result) => setLastResult(`Подъём к ${result.targetMm} мм, лимит ${result.torqueLimit}`))
                .catch((error: unknown) => setLastResult(`STOP не выполнен: ${error instanceof Error ? error.message : String(error)}. Используйте аппаратный E-STOP.`))
                .finally(() => setBusy(null))
            }}
            disabled={!isConnected || busy !== null || !connectionStatus?.simulationMode}
          >
            STOP · подъём к 2000 мм
          </Button>
        </div>
      </div>

      {/* Motor enable gate */}
      <div className="glass-panel rounded-2xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-semibold text-white">Разрешить управление двигателем</p>
            <p className="text-xs text-white/40 mt-1">По умолчанию движение заблокировано для безопасности.</p>
          </div>
          <button
            className={cn(
              'rounded-xl px-4 py-2 text-sm font-semibold transition',
              motorEnabled
                ? 'bg-[#79de83]/20 text-[#79de83] border border-[#79de83]/30'
                : 'bg-white/8 text-white/50 border border-white/10',
            )}
            onClick={() => {
              if (!motorEnabled) setConfirmMotorEnable(true)
              else setMotorEnabled(false)
            }}
          >
            {motorEnabled ? '✓ Движение разрешено' : 'Разрешить'}
          </button>
        </div>
      </div>

      {/* Mode selector */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="font-semibold text-[#f4dfb4]">Режим управления · сервисная настройка, не разрешение движения</h3>

        <div className="flex gap-2">
          {(['position', 'speed', 'torque'] as ControlMode[]).map((m) => (
            <ModeTab key={m} mode={m} active={activeMode === m} onClick={() => setActiveMode(m)} />
          ))}
        </div>

        {/* Mode status */}
        <div className="flex flex-wrap gap-2">
          <StatusChip label="PA_002" value={modeVal != null ? `= ${modeVal}` : '?'} ok={modeVal === (['position','speed','torque'] as ControlMode[]).indexOf(activeMode)} />
          <StatusChip label="PA_090" value={extVal != null ? `= ${extVal}` : '?'} ok={extVal === 1} />
          {hasAlarm && <StatusChip label="ALARM" value="Есть ошибка" ok={false} />}
        </div>

        <Button
          variant="secondary"
          disabled={!isConnected || busy === 'mode'}
          onClick={() => handleSetMode(activeMode)}
          className="text-sm"
        >
          {busy === 'mode' ? 'Настраиваю...' : `Установить режим ${activeMode}`}
        </Button>
        {activeMode === 'torque' && (
          <p className="text-xs text-[#ff8f84] flex items-center gap-1">
            <AlertTriangle size={12} /> Режим момента опасен. Требуется подтверждение перед включением.
          </p>
        )}
      </div>

      {/* Mode-specific segment controls */}
      {activeMode === 'position' && (
        <PositionSegmentControls isConnected={isConnected} busy={busy} onCommand={handleCommand} setBusy={setBusy} setLastResult={setLastResult} />
      )}
      {activeMode === 'speed' && (
        <SpeedSegmentControls isConnected={isConnected} />
      )}
      {activeMode === 'torque' && (
        <TorqueSegmentControls isConnected={isConnected} motorEnabled={motorEnabled && manualTorqueReady} />
      )}

      {/* Command panel */}
      <div className="glass-panel rounded-2xl p-4 space-y-3">
        <h4 className="font-semibold text-[#f4dfb4] text-sm">Команды управления</h4>
        <div className="flex flex-wrap gap-2">
          <CmdButton label="Servo ON" cmd="servo_on" accent busy={busy} disabled={!isConnected || !motorEnabled || hasAlarm || !manualTorqueReady} onCmd={handleCommand} />
          <CmdButton label="Сброс аварии" cmd="alarm_reset" busy={busy} disabled={!isConnected} onCmd={handleCommand} />
          <CmdButton label="JOG ▶" cmd="jog_start" busy={busy} disabled={!isConnected || !motorEnabled || !manualTorqueReady} onCmd={handleCommand} />
          <CmdButton label="JOG ■" cmd="jog_stop" busy={busy} disabled={!isConnected} onCmd={handleCommand} />
          <CmdButton label="Homing" cmd="homing" busy={busy} disabled onCmd={handleCommand} />
        </div>
        {lastResult && (
          <p className="text-xs text-white/50">{lastResult}</p>
        )}
      </div>

      {/* Confirm dialog */}
      {confirmMotorEnable && (
        <ConfirmDialog
          title="Разрешить управление двигателем?"
          body="Это позволит отправлять команды движения. Убедитесь, что зона вокруг двигателя свободна."
          onConfirm={() => { setMotorEnabled(true); setConfirmMotorEnable(false) }}
          onCancel={() => setConfirmMotorEnable(false)}
        />
      )}
    </div>
  )
}

function ModeTab({ mode, active, onClick }: { mode: string; active: boolean; onClick: () => void }) {
  const labels: Record<string, string> = { position: 'Position', speed: 'Speed', torque: 'Torque' }
  return (
    <button
      onClick={onClick}
      className={cn(
        'rounded-xl px-4 py-2 text-sm font-semibold transition',
        active ? 'bg-[#b5852f]/40 text-[#f4dfb4] border border-[#b5852f]/60' : 'bg-white/6 text-white/50 hover:text-white',
      )}
    >
      {labels[mode]}
    </button>
  )
}

function StatusChip({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <span className={cn(
      'rounded-lg px-2.5 py-1 text-xs font-mono',
      ok ? 'bg-[#0d2d0f] text-[#79de83]' : 'bg-[#2d2500] text-[#f2cf87]',
    )}>
      {label} {value}
    </span>
  )
}

function CmdButton({ label, cmd, busy, disabled, onCmd, accent }: {
  label: string; cmd: string; busy: string | null; disabled: boolean; onCmd: (c: string) => void; accent?: boolean
}) {
  return (
    <Button
      variant={accent ? 'primary' : 'secondary'}
      className="text-xs"
      onClick={() => onCmd(cmd)}
      disabled={disabled || busy === cmd}
    >
      {busy === cmd ? '...' : label}
    </Button>
  )
}

function PositionSegmentControls({
  isConnected, busy, onCommand, setBusy, setLastResult,
}: {
  isConnected: boolean
  busy: string | null
  onCommand: (cmd: string) => void
  setBusy: (v: string | null) => void
  setLastResult: (v: string) => void
}) {
  const { paramStates, writeControlRegister, readRegister } = useModbusStore()
  const [segIndex, setSegIndex] = useState(0)
  const [posLow, setPosLow] = useState('')
  const [posHigh, setPosHigh] = useState('')
  const [speed, setSpeed] = useState('')

  const posLowAddr = 0x168 + segIndex * 2
  const posHighAddr = 0x168 + segIndex * 2 + 1
  const speedAddr = 0x190 + segIndex

  const drvLow = paramStates.get(posLowAddr)?.driverValue
  const drvHigh = paramStates.get(posHighAddr)?.driverValue
  const position32 = drvLow != null && drvHigh != null ? ((drvHigh << 16) | (drvLow & 0xFFFF)) >>> 0 : null

  const handleWrite = async () => {
    setBusy('seg_write')
    try {
      if (posLow !== '') await writeControlRegister(posLowAddr, parseInt(posLow))
      if (posHigh !== '') await writeControlRegister(posHighAddr, parseInt(posHigh))
      if (speed !== '') await writeControlRegister(speedAddr, parseInt(speed))
      await writeControlRegister(0x091, segIndex)
      setLastResult(`Сегмент ${segIndex} записан. Нажмите POS_LOAD для загрузки.`)
    } catch (error) {
      setLastResult(`Ошибка записи сегмента: ${error instanceof Error ? error.message : String(error)}. Не запускайте движение.`)
    } finally {
      setBusy(null)
    }
  }

  const handleRead = async () => {
    await readRegister(posLowAddr)
    await readRegister(posHighAddr)
    await readRegister(speedAddr)
  }

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3">
      <h4 className="text-sm font-semibold text-[#f4dfb4]">Сегменты позиции (PA_168–PA_19F)</h4>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          Сегмент:
          <select
            className="input-field"
            value={segIndex}
            onChange={(e) => setSegIndex(Number(e.target.value))}
          >
            {Array.from({ length: 16 }, (_, i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </label>
        <Button variant="ghost" className="text-xs" onClick={handleRead} disabled={!isConnected}>Читать</Button>
      </div>

      {position32 != null && (
        <p className="font-mono text-sm text-[#f2cf87]">
          Позиция: {position32} имп
          <span className="text-white/30 ml-2 text-xs">(H=0x{drvHigh?.toString(16).toUpperCase()} L=0x{drvLow?.toString(16).toUpperCase()})</span>
        </p>
      )}

      <div className="grid grid-cols-3 gap-2">
        <SegField label="Позиция (low)" placeholder={String(drvLow ?? 0)} value={posLow} onChange={setPosLow} />
        <SegField label="Позиция (high)" placeholder={String(drvHigh ?? 0)} value={posHigh} onChange={setPosHigh} />
        <SegField label="Скорость (об/мин)" placeholder={String(paramStates.get(speedAddr)?.driverValue ?? 500)} value={speed} onChange={setSpeed} />
      </div>

      <div className="flex gap-2">
        <Button variant="secondary" className="text-xs" onClick={handleWrite} disabled={!isConnected || busy === 'seg_write'}>
          {busy === 'seg_write' ? '...' : 'Записать сегмент'}
        </Button>
        <Button variant="primary" className="text-xs" onClick={() => onCommand('pos_load')} disabled={!isConnected}>
          POS_LOAD
        </Button>
      </div>
    </div>
  )
}

function SpeedSegmentControls({ isConnected }: { isConnected: boolean }) {
  const { paramStates, writeControlRegister, readRegister } = useModbusStore()
  const [segIndex, setSegIndex] = useState(0)
  const [speed, setSpeed] = useState('')
  const addr = 0x150 + segIndex

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3">
      <h4 className="text-sm font-semibold text-[#f4dfb4]">Сегменты скорости (PA_150–PA_16F)</h4>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          Сегмент:
          <select className="input-field" value={segIndex} onChange={(e) => setSegIndex(Number(e.target.value))}>
            {Array.from({ length: 32 }, (_, i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </label>
        <Button variant="ghost" className="text-xs" onClick={() => readRegister(addr)} disabled={!isConnected}>Читать</Button>
      </div>
      <p className="font-mono text-sm text-white/60">Текущее: {paramStates.get(addr)?.driverValue ?? '—'} об/мин</p>
      <div className="flex gap-2">
        <input
          type="number"
          className="input-field w-32"
          placeholder="Скорость об/мин"
          value={speed}
          onChange={(e) => setSpeed(e.target.value)}
          min={-3000}
          max={3000}
        />
        <Button
          variant="secondary"
          className="text-xs"
          onClick={async () => { if (speed) { await writeControlRegister(addr, parseInt(speed)); await writeControlRegister(0x092, segIndex) } }}
          disabled={!isConnected || !speed}
        >
          Записать
        </Button>
      </div>
    </div>
  )
}

function TorqueSegmentControls({ isConnected, motorEnabled }: { isConnected: boolean; motorEnabled: boolean }) {
  const { paramStates, writeControlRegister, readRegister } = useModbusStore()
  const [segIndex, setSegIndex] = useState(0)
  const [torque, setTorque] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [writing, setWriting] = useState(false)
  const addr = 0x12C + segIndex

  return (
    <div className="glass-panel rounded-2xl border border-[#ff8f84]/20 p-4 space-y-3">
      <h4 className="text-sm font-semibold text-[#ff8f84] flex items-center gap-2">
        <AlertTriangle size={14} /> Сегменты момента (PA_12C–PA_14B) — ОПАСНО
      </h4>
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-sm">
          Сегмент:
          <select className="input-field" value={segIndex} onChange={(e) => setSegIndex(Number(e.target.value))}>
            {Array.from({ length: 32 }, (_, i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </label>
        <Button variant="ghost" className="text-xs" onClick={() => readRegister(addr)} disabled={!isConnected}>Читать</Button>
      </div>
      <p className="font-mono text-sm text-white/60">Текущее: {paramStates.get(addr)?.driverValue ?? '—'} (0.1%)</p>
      <div className="flex gap-2">
        <input
          type="number"
          className="input-field w-32"
          placeholder="Момент 0.1%"
          value={torque}
          onChange={(e) => setTorque(e.target.value)}
          min={-3000}
          max={3000}
        />
        <Button
          variant="danger"
          className="text-xs"
          onClick={() => setConfirm(true)}
          disabled={!isConnected || !motorEnabled || !torque || writing}
        >
          Записать
        </Button>
      </div>
      {result && <p role="status" className="text-xs text-[#ffd166]">{result}</p>}
      {confirm && (
        <ConfirmDialog
          title="Записать момент?"
          body={`Сегмент ${segIndex} получит значение ${torque} (0.1% от номинала). Двигатель начнёт вращение.`}
          onConfirm={async () => {
            setConfirm(false)
            if (torque) {
              setWriting(true)
              setResult(null)
              try {
                await writeControlRegister(addr, parseInt(torque, 10), true)
                await writeControlRegister(0x093, segIndex, true)
                setResult('Значение и выбор сегмента подтверждены чтением на выбранных приводах.')
              } catch (error) {
                setResult(`Ошибка: ${error instanceof Error ? error.message : String(error)}. Движение не запускайте: состояние приводов может различаться.`)
              } finally {
                setWriting(false)
              }
            }
          }}
          onCancel={() => setConfirm(false)}
          danger
        />
      )}
    </div>
  )
}

function SegField({ label, placeholder, value, onChange }: { label: string; placeholder: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="space-y-1">
      <span className="text-xs text-white/40">{label}</span>
      <input type="number" className="input-field w-full text-sm" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

function ConfirmDialog({ title, body, onConfirm, onCancel, danger }: {
  title: string; body: string; onConfirm: () => void; onCancel: () => void; danger?: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="glass-panel rounded-2xl p-6 max-w-md w-full mx-4 space-y-4">
        <div className="flex items-start gap-3">
          <AlertTriangle size={20} className={danger ? 'text-[#ff8f84] mt-0.5' : 'text-[#f2cf87] mt-0.5'} />
          <div>
            <h3 className="font-bold text-white">{title}</h3>
            <p className="text-sm text-white/60 mt-1">{body}</p>
          </div>
        </div>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onCancel}>Отмена</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm}>Подтвердить</Button>
        </div>
      </div>
    </div>
  )
}
