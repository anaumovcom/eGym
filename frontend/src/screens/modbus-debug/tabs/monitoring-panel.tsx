import { Activity, Pause, Play, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { useDriveTelemetry } from '@/features/modbus/lib/use-drive-telemetry'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { positionFeedback } from '@/features/modbus/model/position-feedback'
import { Button } from '@/shared/ui/button'

type AutoInterval = 500 | 1000 | 2000 | 5000

export function MonitoringPanel() {
  const { connectionStatus, paramStates, readRegister } = useModbusStore()
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [interval, setInterval_] = useState<AutoInterval>(1000)
  const isConnected = connectionStatus?.connected ?? false
  const frame = useDriveTelemetry(autoRefresh ? interval : false)
  const loading = frame.isFetching
  const data = isConnected && !frame.isError && !frame.data?.error ? frame.data : undefined
  const message = frame.data?.error || (frame.isError ? 'Не удалось получить кадр привода' : null)
  const when = frame.data?.readAt ? new Date(frame.data.readAt).toLocaleTimeString() : '—'
  const low = paramStates.get(0x1B8)
  const high = paramStates.get(0x1B9)
  const commandPosition = isConnected && low?.readStatus === 'ok' && high?.readStatus === 'ok'
    && low.driverValue != null && high.driverValue != null ? positionFeedback(low.driverValue, high.driverValue) : null
  const rows = [
    ['PA_1BC/1BD', 'Положение энкодера', data?.feedbackPosition],
    ['PA_1BE/1BF', 'Ошибка позиции', data?.positionError],
    ['PA_1C0', 'Заданная скорость', data?.commandSpeedRpm],
    ['PA_1C1', 'Фактическая скорость', data?.feedbackSpeedRpm],
    ['PA_1C3', 'Задание момента в приводе', data?.commandTorqueRaw],
    ['PA_1C4', 'Фактический момент', data?.feedbackTorqueRaw],
    ['PA_1C9', 'Авария', data?.alarm],
  ] as const

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="glass-panel rounded-2xl p-4 space-y-3">
        <div><h3 className="font-semibold">Телеметрия выбранного драйвера</h3><p className="text-sm text-[#a9bece]">{isConnected ? 'Последний кадр обмена с приводом.' : 'Нет входящих данных: подключение не установлено.'}</p></div>
        <div className="modbus-actions">
        <Button
          variant="secondary"
          iconLeft={loading ? <Activity size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          onClick={() => void frame.refetch()}
          disabled={loading || !isConnected}
          className="text-xs"
        >
          Обновить
        </Button>
        <Button
          variant={autoRefresh ? 'danger' : 'secondary'}
          iconLeft={autoRefresh ? <Pause size={14} /> : <Play size={14} />}
          onClick={() => setAutoRefresh((v) => !v)}
          disabled={!isConnected}
          className="text-xs"
        >
          {autoRefresh ? 'Остановить опрос' : 'Автообновление'}
        </Button>
        {autoRefresh && (
          <select
            className="input-field text-xs"
            aria-label="Интервал автообновления"
            value={interval}
            onChange={(e) => setInterval_(Number(e.target.value) as AutoInterval)}
          >
            <option value={500}>0.5 с</option>
            <option value={1000}>1 с</option>
            <option value={2000}>2 с</option>
            <option value={5000}>5 с</option>
          </select>
        )}
        {isConnected && <span className="text-xs text-white/60">Кадр · {when}</span>}
        {isConnected && message && <span role="status" className="text-xs text-[#ffd166]">{message}</span>}
        {autoRefresh && <span className="text-xs text-[#79de83] animate-pulse">● Обновляется</span>}
        {!isConnected && <span className="text-xs text-[#ff8f84]">⚠ Нет подключения</span>}
        </div>
      </div>

      {/* 32-bit computed values */}
      <h3 className="font-semibold">Положение</h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,13rem),1fr))] gap-3">
        <BigMetric label="Позиция от нуля" value={data?.positionMm?.toFixed(4) ?? '—'} unit="мм" addr="PA_1BC/1BD" />
        <div>
          <BigMetric label="Командная позиция" value={String(commandPosition ?? '—')} unit="имп" addr="PA_1B8/1B9" />
          <Button className="text-xs" variant="secondary" disabled={!isConnected} onClick={() => void readRegister(0x1B8, 2)}>Считать командную позицию</Button>
        </div>
        <BigMetric label="Ошибка позиции" value={String(data?.positionError ?? '—')} unit="имп" addr="PA_1BE/1BF" />
      </div>

      <h3 className="font-semibold">Скорость и момент</h3>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,11rem),1fr))] gap-3">
        <BigMetric label="Фактическая скорость" value={String(data?.feedbackSpeedRpm ?? '—')} unit="об/мин" addr="PA_1C1" />
        <BigMetric label="Отправленный момент" value={String(data?.torqueWrittenRaw ?? '—')} unit="0,1 %" addr="PA_12C" />
        <BigMetric label="Задание в приводе" value={String(data?.commandTorqueRaw ?? '—')} unit="0,1 %" addr="PA_1C3" />
        <BigMetric label="Фактический момент" value={String(data?.feedbackTorqueRaw ?? '—')} unit="0,1 %" addr="PA_1C4" />
        <BigMetric label="Отправлено минус задание привода" value={data?.torqueWrittenRaw != null && data.commandTorqueRaw != null ? String(data.torqueWrittenRaw - data.commandTorqueRaw) : '—'} unit="0,1 %" addr="PA_12C − PA_1C3" />
        <BigMetric label="Задание минус фактический" value={data?.commandTorqueRaw != null && data.feedbackTorqueRaw != null ? String(data.commandTorqueRaw - data.feedbackTorqueRaw) : '—'} unit="0,1 %" addr="PA_1C3 − PA_1C4" />
      </div>

      {/* Full register table */}
      <div className="glass-panel modbus-table-scroll rounded-2xl" role="region" aria-label="Сырые значения телеметрии" tabIndex={0}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/8 text-xs text-white/40 uppercase">
              <th className="px-4 py-2 text-left">Адрес</th>
              <th className="px-4 py-2 text-left">Параметр</th>
              <th className="px-4 py-2 text-right">Значение</th>
              <th className="px-4 py-2 text-right">Hex</th>
              <th className="px-4 py-2 text-right">Обновлено</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([address, label, value]) => (
              <tr key={address} className="border-b border-white/4 hover:bg-white/3">
                <td className="px-4 py-2 font-mono text-xs text-white/40">{address}</td>
                <td className="px-4 py-2 text-white/70">{label}</td>
                <td className="px-4 py-2 text-right font-mono">{value ?? '—'}</td>
                <td className="px-4 py-2 text-right font-mono">{value == null ? '—' : (address.includes('/') ? value >>> 0 : value & 0xffff).toString(16).toUpperCase().padStart(address.includes('/') ? 8 : 4, '0')}</td>
                <td className="px-4 py-2 text-right text-xs text-white/30">{when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BigMetric({ label, value, unit, addr, danger }: {
  label: string; value: string; unit: string; addr: string; danger?: boolean
}) {
  return (
    <div className={`glass-panel rounded-2xl p-4 ${danger ? 'border border-[#ff8f84]/30' : ''}`}>
      <div className="text-xs text-white/40 mb-1">{label}</div>
      <div className={`text-2xl font-mono font-bold ${danger ? 'text-[#ff8f84]' : 'text-white'}`}>{value}</div>
      <div className="flex flex-wrap items-center justify-between gap-1 mt-1">
        <span className="text-xs text-white/30">{unit}</span>
        <span className="text-[10px] font-mono text-white/20">{addr}</span>
      </div>
    </div>
  )
}
