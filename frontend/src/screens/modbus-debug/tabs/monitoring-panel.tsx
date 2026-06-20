import { Activity, Pause, Play, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { Button } from '@/shared/ui/button'

const MONITOR_ADDRESSES = [0x203, 0x204, 0x205, 0x206, 0x207, 0x208, 0x20B, 0x20C, 0x209, 0x20A]

const MONITOR_LABELS: Record<number, string> = {
  0x203: 'Фактическая скорость',
  0x204: 'Фактический момент',
  0x205: 'Позиция OB (low)',
  0x206: 'Позиция OB (high)',
  0x207: 'Командная позиция (low)',
  0x208: 'Командная позиция (high)',
  0x20B: 'Ошибка позиции (low)',
  0x20C: 'Ошибка позиции (high)',
  0x209: 'Заданная скорость',
  0x20A: 'Заданный момент',
}

type AutoInterval = 500 | 1000 | 2000 | 5000

export function MonitoringPanel() {
  const { paramStates, connectionStatus, readBatch } = useModbusStore()
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [interval, setInterval_] = useState<AutoInterval>(1000)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isConnected = connectionStatus?.connected ?? false

  const refresh = async () => {
    if (!isConnected) return
    setLoading(true)
    try {
      await readBatch(MONITOR_ADDRESSES)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (autoRefresh && isConnected) {
      timerRef.current = setInterval(refresh, interval)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
      timerRef.current = null
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, interval, isConnected])

  // 32-bit helpers
  const pos32 = combine32(paramStates.get(0x205)?.driverValue, paramStates.get(0x206)?.driverValue)
  const cmd32 = combine32(paramStates.get(0x207)?.driverValue, paramStates.get(0x208)?.driverValue)
  const err32 = combine32(paramStates.get(0x20B)?.driverValue, paramStates.get(0x20C)?.driverValue)

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="glass-panel rounded-2xl p-4 flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          iconLeft={loading ? <Activity size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          onClick={refresh}
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
          {autoRefresh ? 'Стоп' : 'Авто'}
        </Button>
        {autoRefresh && (
          <select
            className="input-field text-xs"
            value={interval}
            onChange={(e) => setInterval_(Number(e.target.value) as AutoInterval)}
          >
            <option value={500}>0.5 с</option>
            <option value={1000}>1 с</option>
            <option value={2000}>2 с</option>
            <option value={5000}>5 с</option>
          </select>
        )}
        {autoRefresh && <span className="text-xs text-[#79de83] animate-pulse">● Обновляется</span>}
        {!isConnected && <span className="text-xs text-[#ff8f84]">⚠ Нет подключения</span>}
      </div>

      {/* 32-bit computed values */}
      <div className="grid gap-3 sm:grid-cols-3">
        <BigMetric label="Позиция (ОС)" value={pos32 != null ? String(pos32) : '—'} unit="имп" addr="0x206:0x205" />
        <BigMetric label="Командная позиция" value={cmd32 != null ? String(cmd32) : '—'} unit="имп" addr="0x208:0x207" />
        <BigMetric label="Ошибка позиции" value={err32 != null ? String(err32) : '—'} unit="имп" addr="0x20C:0x20B" danger={err32 != null && Math.abs(err32) > 1000} />
      </div>

      {/* Speed / torque row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MonitorCard addr={0x203} label="Фактическая скорость" unit="об/мин" />
        <MonitorCard addr={0x209} label="Заданная скорость" unit="об/мин" />
        <MonitorCard addr={0x204} label="Фактический момент" unit="0.1%" />
        <MonitorCard addr={0x20A} label="Заданный момент" unit="0.1%" />
      </div>

      {/* Full register table */}
      <div className="glass-panel rounded-2xl overflow-hidden">
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
            {MONITOR_ADDRESSES.map((addr) => {
              const st = paramStates.get(addr)
              const v = st?.driverValue
              return (
                <tr key={addr} className="border-b border-white/4 hover:bg-white/3">
                  <td className="px-4 py-2 font-mono text-xs text-white/40">0x{addr.toString(16).toUpperCase().padStart(3, '0')}</td>
                  <td className="px-4 py-2 text-white/70">{MONITOR_LABELS[addr] ?? `0x${addr.toString(16)}`}</td>
                  <td className="px-4 py-2 text-right font-mono">{v != null ? v : '—'}</td>
                  <td className="px-4 py-2 text-right font-mono text-white/40">{v != null ? `0x${v.toString(16).toUpperCase().padStart(4, '0')}` : '—'}</td>
                  <td className="px-4 py-2 text-right text-xs text-white/30">{st?.readAt ? new Date(st.readAt).toLocaleTimeString() : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function combine32(low?: number | null, high?: number | null): number | null {
  if (low == null || high == null) return null
  return ((high << 16) | (low & 0xFFFF)) | 0
}

function BigMetric({ label, value, unit, addr, danger }: {
  label: string; value: string; unit: string; addr: string; danger?: boolean
}) {
  return (
    <div className={`glass-panel rounded-2xl p-4 ${danger ? 'border border-[#ff8f84]/30' : ''}`}>
      <div className="text-xs text-white/40 mb-1">{label}</div>
      <div className={`text-2xl font-mono font-bold ${danger ? 'text-[#ff8f84]' : 'text-white'}`}>{value}</div>
      <div className="flex items-center justify-between mt-1">
        <span className="text-xs text-white/30">{unit}</span>
        <span className="text-[10px] font-mono text-white/20">{addr}</span>
      </div>
    </div>
  )
}

function MonitorCard({ addr, label, unit }: { addr: number; label: string; unit: string }) {
  const paramStates = useModbusStore((s) => s.paramStates)
  const st = paramStates.get(addr)
  const v = st?.driverValue
  return (
    <div className="glass-panel rounded-2xl p-4">
      <div className="text-xs text-white/40 mb-1">{label}</div>
      <div className="text-xl font-mono font-bold text-white">{v != null ? v : '—'}</div>
      <div className="flex items-center justify-between mt-1">
        <span className="text-xs text-white/30">{unit}</span>
        <span className="text-[10px] font-mono text-white/20">0x{addr.toString(16).toUpperCase().padStart(3, '0')}</span>
      </div>
    </div>
  )
}
