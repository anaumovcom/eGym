import { Download, Filter, RefreshCw, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import type { ExchangeDirection } from '@/features/modbus/model/types'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

const DIR_COLORS: Record<ExchangeDirection, string> = {
  TX: 'text-[#79de83]',
  RX: 'text-[#89b4e8]',
  INFO: 'text-white/40',
  ERROR: 'text-[#ff8f84]',
}

const DIR_BG: Record<ExchangeDirection, string> = {
  TX: 'bg-[#79de83]/10',
  RX: 'bg-[#89b4e8]/10',
  INFO: 'bg-white/4',
  ERROR: 'bg-[#ff8f84]/10',
}

export function LogPanel() {
  const { logEntries, logTotal, logFilter, setLogFilter, loadLog, clearLog } = useModbusStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void handleRefresh()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logFilter])

  const handleRefresh = async () => {
    setLoading(true)
    try {
      await loadLog()
    } finally {
      setLoading(false)
    }
  }

  const handleClear = async () => {
    await clearLog()
  }

  const handleExport = () => {
    const lines = logEntries.map((e) =>
      [
        new Date(e.ts).toISOString(),
        e.direction,
        e.action,
        e.address != null ? `0x${e.address.toString(16).toUpperCase().padStart(3, '0')}` : '',
        e.value != null ? String(e.value) : '',
        e.rawRequest ?? '',
        e.rawResponse ?? '',
        e.error ?? '',
        e.elapsedMs != null ? `${e.elapsedMs.toFixed(1)}ms` : '',
      ].join('\t'),
    )
    const blob = new Blob([['Timestamp', 'Dir', 'Action', 'Addr', 'Value', 'Request', 'Response', 'Error', 'Elapsed'].join('\t') + '\n' + lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `modbus-log-${Date.now()}.tsv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="glass-panel rounded-2xl p-4 flex flex-wrap items-center gap-2">
        <Button
          variant="secondary"
          className="text-xs"
          iconLeft={loading ? <RefreshCw size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          onClick={handleRefresh}
          disabled={loading}
        >
          Обновить
        </Button>

        <span className="flex items-center gap-1 text-xs text-white/40">
          <Filter size={12} /> Фильтр:
        </span>

        <DirectionFilter label="TX" value="TX" current={logFilter.direction} onChange={(v) => setLogFilter({ direction: v })} />
        <DirectionFilter label="RX" value="RX" current={logFilter.direction} onChange={(v) => setLogFilter({ direction: v })} />
        <DirectionFilter label="Ошибки" value="ERROR" current={logFilter.direction} onChange={(v) => setLogFilter({ direction: v })} />
        <DirectionFilter label="INFO" value="INFO" current={logFilter.direction} onChange={(v) => setLogFilter({ direction: v })} />
        <DirectionFilter label="Все" value={undefined} current={logFilter.direction} onChange={(v) => setLogFilter({ direction: v })} />

        <div className="ml-auto flex gap-2">
          <Button variant="ghost" className="text-xs" iconLeft={<Download size={13} />} onClick={handleExport} disabled={logEntries.length === 0}>
            Экспорт
          </Button>
          <Button variant="ghost" className="text-xs" iconLeft={<Trash2 size={13} />} onClick={handleClear} disabled={logEntries.length === 0}>
            Очистить
          </Button>
        </div>
      </div>

      <p className="text-xs text-white/30 px-1">
        Показано: {logEntries.length} из {logTotal}
      </p>

      {/* Log table */}
      <div className="glass-panel rounded-2xl overflow-hidden">
        {logEntries.length === 0 ? (
          <div className="p-8 text-center text-white/30 text-sm">Журнал пуст</div>
        ) : (
          <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#1a1207] z-10">
                <tr className="border-b border-white/8 text-white/30 uppercase tracking-wide">
                  <th className="px-3 py-2 text-left">Время</th>
                  <th className="px-3 py-2 text-left">Dir</th>
                  <th className="px-3 py-2 text-left">Действие</th>
                  <th className="px-3 py-2 text-left">Адрес</th>
                  <th className="px-3 py-2 text-right">Значение</th>
                  <th className="px-3 py-2 text-left">Запрос</th>
                  <th className="px-3 py-2 text-left">Ответ</th>
                  <th className="px-3 py-2 text-right">мс</th>
                  <th className="px-3 py-2 text-left">Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {logEntries.map((entry) => (
                  <tr
                    key={entry.id}
                    className={cn(
                      'border-b border-white/4 hover:bg-white/3 transition',
                      entry.error ? 'bg-[#3d1010]/40' : '',
                    )}
                  >
                    <td className="px-3 py-2 text-white/30 whitespace-nowrap">
                      {new Date(entry.ts).toLocaleTimeString('ru', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 })}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold', DIR_BG[entry.direction], DIR_COLORS[entry.direction])}>
                        {entry.direction}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-mono text-white/70 whitespace-nowrap">{entry.action}</td>
                    <td className="px-3 py-2 font-mono text-white/40">
                      {entry.address != null ? `0x${entry.address.toString(16).toUpperCase().padStart(3, '0')}` : ''}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-white/60">
                      {entry.value != null ? `${entry.value} (0x${entry.value.toString(16).toUpperCase().padStart(4, '0')})` : ''}
                    </td>
                    <td className="px-3 py-2 font-mono text-white/40 max-w-[200px] truncate" title={entry.rawRequest ?? ''}>
                      {entry.rawRequest}
                    </td>
                    <td className="px-3 py-2 font-mono text-white/40 max-w-[200px] truncate" title={entry.rawResponse ?? ''}>
                      {entry.rawResponse}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-white/30">
                      {entry.elapsedMs != null ? entry.elapsedMs.toFixed(1) : ''}
                    </td>
                    <td className="px-3 py-2 text-[#ff8f84] max-w-[200px] truncate" title={entry.error ?? ''}>
                      {entry.error}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function DirectionFilter({
  label, value, current, onChange,
}: {
  label: string
  value: string | undefined
  current: string | undefined
  onChange: (v: string | undefined) => void
}) {
  const active = current === value
  return (
    <button
      className={cn(
        'rounded-xl px-3 py-1.5 text-xs font-medium transition',
        active ? 'bg-[#b5852f]/30 text-[#f2cf87]' : 'bg-white/6 text-white/40 hover:text-white',
      )}
      onClick={() => onChange(active ? undefined : value)}
    >
      {label}
    </button>
  )
}
