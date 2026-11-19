import { Activity, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { useCallback } from 'react'
import { useModbusRead } from '@/features/modbus/lib/use-modbus-read'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import {
  BAUD_RATE_LABELS,
  CONTROL_MODE_LABELS,
} from '@/features/modbus/model/parameter-catalog'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function DiagnosticsPanel() {
  const { diagnostics: lastCheck, loadDiagnostics, connectionStatus, readRegister, selectedSide, driveAddresses } = useModbusStore()
  const isConnected = connectionStatus?.connected ?? false
  const slave = driveAddresses[selectedSide]
  const check = useCallback(async () => {
    if (isConnected && slave) await loadDiagnostics()
  }, [isConnected, slave, loadDiagnostics])
  const { loading, failed, refresh: handleRefresh } = useModbusRead(check, isConnected ? 1000 : undefined)
  const diagnostics = isConnected && !failed ? lastCheck : null

  const handleQuickRead = async (address: number) => {
    await readRegister(address)
    await loadDiagnostics()
  }

  return (
    <div className="space-y-4">
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="font-semibold">Проверка выбранного драйвера</h3>
          <Button
            variant="secondary"
            iconLeft={loading ? <Activity size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            onClick={handleRefresh}
            disabled={loading || !isConnected}
            className="text-xs"
          >
            Обновить
          </Button>
        </div>

        {!diagnostics && (
          <p className="text-sm text-[#a9bece]">{failed ? 'Состояние привода неизвестно' : isConnected ? 'Ожидание данных привода' : 'Ожидание подключения приводов'}</p>
        )}

        {diagnostics && (
          <div className="space-y-4">
            {/* Summary */}
            <DiagSummary responding={diagnostics.responding} summary={diagnostics.statusSummary} hasAlarm={diagnostics.hasAlarm} motionSafe={diagnostics.motionSafe} />

            {/* Parameter overview */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <DiagRow
                label="Slave ID"
                value={diagnostics.slaveId != null ? String(diagnostics.slaveId) : '—'}
                paramName="PA_000"
                address={0x000}
                onRead={handleQuickRead}
              />
              <DiagRow
                label="Скорость RS485"
                value={diagnostics.baudRateCode != null ? (BAUD_RATE_LABELS[diagnostics.baudRateCode] ?? String(diagnostics.baudRateCode)) : '—'}
                paramName="PA_00D"
                address={0x00D}
                onRead={handleQuickRead}
              />
              <DiagRow
                label="Режим управления"
                value={diagnostics.controlMode != null ? (CONTROL_MODE_LABELS[diagnostics.controlMode] ?? String(diagnostics.controlMode)) : '—'}
                paramName="PA_002"
                address={0x002}
                onRead={handleQuickRead}
              />
              <DiagRow
                label="Расширенный режим"
                value={diagnostics.extendedMode === 1 ? 'Включён' : diagnostics.extendedMode === 0 ? 'Выключен' : '—'}
                paramName="PA_090"
                address={0x090}
                onRead={handleQuickRead}
                valueColor={diagnostics.extendedMode === 1 ? 'good' : 'warning'}
              />
              <DiagRow
                label="Код ошибки"
                value={diagnostics.alarmCode != null ? (diagnostics.alarmCode === 0 ? 'Нет ошибки' : `0x${diagnostics.alarmCode.toString(16).toUpperCase().padStart(4, '0')}`) : '—'}
                paramName="PA_1C9"
                address={0x1C9}
                onRead={handleQuickRead}
                valueColor={diagnostics.hasAlarm == null ? 'warning' : diagnostics.hasAlarm ? 'danger' : 'good'}
              />
            </div>

            {diagnostics.checkedAt && (
              <p className="text-xs text-white/30">
                Последняя проверка: {new Date(diagnostics.checkedAt).toLocaleTimeString()}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Quick action buttons */}
      <div className="glass-panel rounded-2xl p-5">
        <h3 className="text-sm font-semibold mb-1">Чтение отдельных регистров</h3>
        <p className="mb-3 text-xs text-[#a9bece]">Чтение обновляет сводку и не записывает значения.</p>
        <div className="flex flex-wrap gap-2">
          {QUICK_READS.map((qr) => (
            <Button
              key={qr.address}
              variant="secondary"
              className="text-xs"
              onClick={() => handleQuickRead(qr.address)}
              disabled={!isConnected}
            >
              Читать {qr.name}
            </Button>
          ))}
        </div>
      </div>
    </div>
  )
}

const QUICK_READS = [
  { name: 'PA_000', address: 0x000 },
  { name: 'PA_002', address: 0x002 },
  { name: 'PA_00D', address: 0x00D },
  { name: 'PA_090', address: 0x090 },
  { name: 'PA_1C9 (ошибка)', address: 0x1C9 },
  { name: 'PA_1C1 (скорость)', address: 0x1C1 },
  { name: 'PA_1C4 (момент)', address: 0x1C4 },
]

function DiagSummary({
  responding, summary, hasAlarm, motionSafe,
}: { responding: boolean; summary: string; hasAlarm: boolean | null; motionSafe: boolean }) {
  const tone = !responding ? 'danger' : !motionSafe ? 'warning' : 'good'
  const toneClasses = {
    danger: 'border-[#ff8f84]/30 bg-[#3d1010]',
    warning: 'border-[#f2cf87]/30 bg-[#2d2500]',
    good: 'border-[#79de83]/20 bg-[#0d2d0f]',
  }
  const icon = responding
    ? hasAlarm !== false || !motionSafe
      ? <XCircle size={18} className="text-[#f2cf87]" />
      : <CheckCircle2 size={18} className="text-[#79de83]" />
    : <XCircle size={18} className="text-[#ff8f84]" />

  return (
    <div className={cn('flex items-center gap-3 rounded-xl border p-4', toneClasses[tone])}>
      {icon}
      <div className="flex-1">
        <p className="font-semibold text-sm text-white">{summary}</p>
        {motionSafe && <p className="text-xs text-[#79de83] mt-0.5">Управление движением возможно</p>}
        {!motionSafe && responding && <p className="text-xs text-[#f2cf87] mt-0.5">Управление движением заблокировано</p>}
      </div>
    </div>
  )
}

function DiagRow({
  label, value, paramName, address, onRead, valueColor,
}: {
  label: string
  value: string
  paramName: string
  address: number
  onRead: (addr: number) => void
  valueColor?: 'good' | 'warning' | 'danger'
}) {
  const colorMap = { good: 'text-[#79de83]', warning: 'text-[#f2cf87]', danger: 'text-[#ff8f84]' }
  return (
    <div className="rounded-xl bg-white/4 p-3 flex items-center justify-between gap-2">
      <div>
        <div className="text-xs text-white/40 mb-0.5">{label}</div>
        <div className={cn('font-mono text-sm font-semibold', valueColor ? colorMap[valueColor] : 'text-white')}>
          {value}
        </div>
      </div>
      <button
        className="text-xs text-white/30 hover:text-white/70 font-mono"
        onClick={() => onRead(address)}
      >
        {paramName} ↺
      </button>
    </div>
  )
}
