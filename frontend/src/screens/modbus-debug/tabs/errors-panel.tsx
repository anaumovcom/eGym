import { AlertTriangle, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { useDriveTelemetry } from '@/features/modbus/lib/use-drive-telemetry'
import { ALARM_CODES } from '@/features/modbus/model/parameter-catalog'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function ErrorsPanel() {
  const { connectionStatus, runCommand } = useModbusStore()
  const [busy, setBusy] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [lastResult, setLastResult] = useState<string | null>(null)

  const isConnected = connectionStatus?.connected ?? false
  const frame = useDriveTelemetry(1000)
  const alarmCode = isConnected && !frame.isError && !frame.data?.error ? frame.data?.alarm ?? null : null
  const alarmInfo = alarmCode != null ? (ALARM_CODES[alarmCode] ?? null) : null
  const hasAlarm = alarmCode != null && alarmCode !== 0

  const handleReadAlarm = async () => {
    setBusy('read')
    try {
      await frame.refetch()
    } finally {
      setBusy(null)
    }
  }

  const handleReset = async () => {
    setBusy('reset')
    try {
      const r = await runCommand('alarm_reset', true)
      setLastResult(r.success ? 'Аварийный сигнал сброшен' : `Ошибка: ${r.error}`)
    } finally {
      setBusy(null)
    }
  }

  const handleClearHistory = async () => {
    setConfirmClear(false)
    setBusy('clear')
    try {
      const r = await runCommand('clear_alarm_history', true)
      setLastResult(r.success ? 'История ошибок очищена (PA_1A7 = 0x0802)' : `Ошибка: ${r.error}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* Current alarm */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Авария привода · PA_1C9</h3>
          <Button
            variant="secondary"
            className="text-xs"
            iconLeft={busy === 'read' ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            onClick={handleReadAlarm}
            disabled={!isConnected || busy !== null}
          >
            Читать
          </Button>
        </div>

        {alarmCode == null ? (
          <p className="text-sm text-white/40">{isConnected ? frame.data?.error || 'Состояние аварии неизвестно' : 'Ожидание подключения приводов'}</p>
        ) : !hasAlarm ? (
          <div className="flex items-center gap-3 rounded-xl bg-[#0d2d0f] border border-[#79de83]/20 p-4">
            <span className="text-[#79de83] text-2xl">✓</span>
            <div>
              <p className="font-semibold text-[#79de83]">Нет активных ошибок</p>
              <p className="text-xs text-white/40">Код: 0x0000</p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl bg-[#3d1010] border border-[#ff8f84]/30 p-4 space-y-3">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="text-[#ff8f84] mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-[#ff8f84] text-lg">
                    {alarmInfo?.label ?? `Неизвестная ошибка`}
                  </span>
                  <span className="font-mono text-xs text-white/40">
                    Err {alarmCode}
                  </span>
                </div>
                {alarmInfo && (
                  <div className="mt-2 space-y-1">
                    <p className="text-sm text-white/60"><span className="text-white/40">Причины: </span>{alarmInfo.causes}</p>
                    <p className="text-sm text-white/60"><span className="text-white/40">Действие: </span>{alarmInfo.action}</p>
                  </div>
                )}
              </div>
            </div>
            {connectionStatus?.simulationMode && alarmInfo && (
              <Button
                variant="secondary"
                iconLeft={<RotateCcw size={14} />}
                onClick={handleReset}
                disabled={!isConnected || busy !== null}
                className="text-sm"
              >
                {busy === 'reset' ? 'Сброс...' : 'Сбросить аварию'}
              </Button>
            )}
          </div>
        )}

        {lastResult && (
          <p className="text-xs text-white/40">{lastResult}</p>
        )}
      </div>

      {/* Alarm code reference */}
      <div className="glass-panel rounded-2xl p-5 space-y-3">
        <h4 className="font-semibold text-sm">Справочник кодов ошибок</h4>
        <div className="space-y-1">
          {Object.entries(ALARM_CODES).filter(([code]) => Number(code) !== 0).map(([code, info]) => (
            <div
              key={code}
              className={cn(
                'flex items-start gap-3 rounded-xl px-3 py-2',
                alarmCode === Number(code) ? 'bg-[#3d1010] border border-[#ff8f84]/30' : 'hover:bg-white/3',
              )}
            >
              <span className="font-mono text-xs text-white/40 shrink-0 mt-0.5 w-10">0x{Number(code).toString(16).toUpperCase().padStart(2, '0')}</span>
              <div>
                <p className="text-sm text-white/90 font-medium">{info.label}</p>
                <p className="text-xs text-white/40">{info.causes}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Clear history */}
      <div className="glass-panel rounded-2xl p-4 space-y-3 border border-[#ff8f84]/15">
        <h4 className="text-sm font-semibold text-[#ff8f84] flex items-center gap-2">
          <Trash2 size={14} /> Опасная операция
        </h4>
        <p className="text-xs text-white/50">
          Очистка истории ошибок выполняется через PA_1A7 = 0x0802. Требует подтверждения.
        </p>
        <Button
          variant="danger"
          className="text-xs"
          onClick={() => setConfirmClear(true)}
          disabled={!isConnected || busy !== null}
        >
          Очистить историю ошибок
        </Button>
      </div>

      {confirmClear && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-panel rounded-2xl p-6 max-w-md w-full mx-4 space-y-4">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="text-[#ff8f84] mt-0.5" />
              <div>
                <h3 className="font-bold text-white">Очистить историю ошибок?</h3>
                <p className="text-sm text-white/60 mt-1">Запись PA_1A7 = 0x0802 сотрёт журнал аварий в драйвере. Действие необратимо.</p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <Button variant="ghost" onClick={() => setConfirmClear(false)}>Отмена</Button>
              <Button variant="danger" onClick={handleClearHistory}>Очистить</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
