import { Activity, AlertTriangle, Cable, CheckCircle2, Link, Unlink, Wifi, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export function ConnectionPanel() {
  const {
    connectionParams,
    connectionStatus,
    ports,
    setConnectionParams,
    loadPorts,
    loadStatus,
    connect,
    disconnect,
    ping,
  } = useModbusStore()

  const [pingResult, setPingResult] = useState<boolean | null>(null)
  const [pingLoading, setPingLoading] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void loadPorts()
    void loadStatus()
  }, [loadPorts, loadStatus])

  const handleConnect = async () => {
    setBusy(true)
    try {
      await connect()
    } finally {
      setBusy(false)
    }
  }

  const handleDisconnect = async () => {
    setBusy(true)
    try {
      await disconnect()
    } finally {
      setBusy(false)
    }
  }

  const handlePing = async () => {
    setPingLoading(true)
    try {
      const ok = await ping()
      setPingResult(ok)
    } finally {
      setPingLoading(false)
    }
  }

  const isConnected = connectionStatus?.connected ?? false

  return (
    <div className="space-y-4">
      {/* Main connection block */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[#f4dfb4] font-semibold">
            <Cable size={18} />
            Подключение к Modbus RTU
          </div>
          <StatusBadge connected={isConnected} simMode={connectionStatus?.simulationMode ?? false} />
        </div>

        {/* Port & params row */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <label className="space-y-1">
            <span className="text-xs text-white/50">Serial-порт</span>
            <select
              className="input-field w-full"
              value={connectionParams.port}
              onChange={(e) => setConnectionParams({ port: e.target.value })}
              disabled={isConnected}
            >
              {ports.map((p) => (
                <option key={p.device} value={p.device}>{p.device} — {p.description}</option>
              ))}
              {!ports.find((p) => p.device === connectionParams.port) && (
                <option value={connectionParams.port}>{connectionParams.port}</option>
              )}
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-xs text-white/50">Скорость (бод)</span>
            <select
              className="input-field w-full"
              value={connectionParams.baudRate}
              onChange={(e) => setConnectionParams({ baudRate: Number(e.target.value) })}
              disabled={isConnected}
            >
              {[9600, 19200, 38400, 57600, 115200].map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </label>

          <label className="space-y-1">
            <span className="text-xs text-white/50">Slave ID (адрес)</span>
            <input
              type="number"
              className="input-field w-full"
              min={1}
              max={247}
              value={connectionParams.slaveId}
              onChange={(e) => setConnectionParams({ slaveId: Number(e.target.value) })}
              disabled={isConnected}
            />
          </label>

          <label className="space-y-1">
            <span className="text-xs text-white/50">Таймаут (мс)</span>
            <input
              type="number"
              className="input-field w-full"
              min={100}
              max={5000}
              step={100}
              value={connectionParams.timeoutMs}
              onChange={(e) => setConnectionParams({ timeoutMs: Number(e.target.value) })}
              disabled={isConnected}
            />
          </label>
        </div>

        {/* Format info (fixed for Lichuan A6) */}
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white/4 p-3 text-sm">
          <span className="text-white/50 text-xs">Формат связи:</span>
          <FormatTag label="8 data bits" />
          <FormatTag label="Even parity" highlighted />
          <FormatTag label="1 stop bit" />
        </div>

        {/* Stats row */}
        {connectionStatus && (
          <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <StatCell label="Последний ответ" value={connectionStatus.lastSuccessAt ? new Date(connectionStatus.lastSuccessAt).toLocaleTimeString() : '—'} />
            <StatCell label="Успешных запросов" value={String(connectionStatus.okCount)} tone="good" />
            <StatCell label="Ошибок" value={String(connectionStatus.errorCount)} tone={connectionStatus.errorCount > 0 ? 'danger' : undefined} />
            <StatCell label="Режим" value={connectionStatus.simulationMode ? 'Симуляция' : 'Реальный порт'} tone={connectionStatus.simulationMode ? 'warning' : 'good'} />
          </div>
        )}

        {connectionStatus?.errorMessage && (
          <div className="flex items-center gap-2 rounded-xl bg-[#3d1010] px-4 py-2 text-sm text-[#ff8f84]">
            <XCircle size={15} />
            {connectionStatus.errorMessage}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-3">
          {!isConnected ? (
            <Button
              variant="primary"
              iconLeft={<Link size={15} />}
              onClick={handleConnect}
              disabled={busy}
            >
              Подключиться
            </Button>
          ) : (
            <Button
              variant="danger"
              iconLeft={<Unlink size={15} />}
              onClick={handleDisconnect}
              disabled={busy}
            >
              Отключиться
            </Button>
          )}
          <Button
            variant="secondary"
            iconLeft={pingLoading ? <Activity size={15} className="animate-spin" /> : <Wifi size={15} />}
            onClick={handlePing}
            disabled={pingLoading || !isConnected}
          >
            Проверить связь
          </Button>
          {pingResult !== null && (
            <span className={cn('flex items-center gap-1 text-sm', pingResult ? 'text-[#79de83]' : 'text-[#ff8f84]')}>
              {pingResult ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
              {pingResult ? 'Драйвер отвечает' : 'Нет ответа'}
            </span>
          )}
        </div>
      </div>

      {/* Wiring guide */}
      <div className="glass-panel rounded-2xl p-5">
        <div className="flex items-center gap-2 text-[#f4dfb4] font-semibold mb-3">
          <AlertTriangle size={16} className="text-[#f2cf87]" />
          Схема подключения
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs text-white/50 mb-2 uppercase tracking-wide">Адаптер → Драйвер</p>
            <WireRow from="T/R+" to="485+" />
            <WireRow from="T/R−" to="485−" />
            <WireRow from="GND" to="GND (если подключён)" />
          </div>
          <div>
            <p className="text-xs text-white/50 mb-2 uppercase tracking-wide">Lichuan A6 — распиновка RJ45</p>
            <PinRow pin="3" label="GND" />
            <PinRow pin="4" label="485+" highlighted />
            <PinRow pin="5" label="485−" highlighted />
          </div>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ connected, simMode }: { connected: boolean; simMode: boolean }) {
  if (!connected) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-white/8 px-3 py-1 text-xs text-white/50">
        <span className="h-2 w-2 rounded-full bg-white/30" />
        Не подключено
      </span>
    )
  }
  if (simMode) {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-[#2d2500] px-3 py-1 text-xs text-[#f2cf87]">
        <span className="h-2 w-2 animate-pulse rounded-full bg-[#f2cf87]" />
        Симуляция
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 rounded-full bg-[#0d2d0f] px-3 py-1 text-xs text-[#79de83]">
      <span className="h-2 w-2 animate-pulse rounded-full bg-[#79de83]" />
      Подключено
    </span>
  )
}

function FormatTag({ label, highlighted }: { label: string; highlighted?: boolean }) {
  return (
    <span className={cn('rounded px-2 py-0.5 text-xs font-mono', highlighted ? 'bg-[#b5852f]/30 text-[#f2cf87]' : 'bg-white/8 text-white/70')}>
      {label}
    </span>
  )
}

function StatCell({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'warning' | 'danger' }) {
  const colorMap = { good: 'text-[#79de83]', warning: 'text-[#f2cf87]', danger: 'text-[#ff8f84]' }
  return (
    <div className="rounded-xl bg-white/4 px-3 py-2">
      <div className="text-white/40 mb-0.5">{label}</div>
      <div className={cn('font-mono font-semibold', tone ? colorMap[tone] : 'text-white')}>{value}</div>
    </div>
  )
}

function WireRow({ from, to }: { from: string; to: string }) {
  return (
    <div className="flex items-center gap-2 py-1 text-sm">
      <span className="font-mono text-[#f2cf87] min-w-[48px]">{from}</span>
      <span className="text-white/30">→</span>
      <span className="font-mono text-white/80">{to}</span>
    </div>
  )
}

function PinRow({ pin, label, highlighted }: { pin: string; label: string; highlighted?: boolean }) {
  return (
    <div className="flex items-center gap-2 py-1 text-sm">
      <span className={cn('rounded px-1.5 py-0.5 font-mono text-xs font-bold', highlighted ? 'bg-[#b5852f]/30 text-[#f2cf87]' : 'bg-white/8 text-white/50')}>
        pin {pin}
      </span>
      <span className="font-mono text-white/80">{label}</span>
    </div>
  )
}
