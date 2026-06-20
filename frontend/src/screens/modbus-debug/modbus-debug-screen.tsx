import { useSearchParams } from 'react-router-dom'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { useHardwareStore } from '@/stores/hardware-store'
import { ConnectionPanel } from './tabs/connection-panel'
import { DiagnosticsPanel } from './tabs/diagnostics-panel'
import { ParametersPanel } from './tabs/parameters-panel'
import { ControlModePanel } from './tabs/control-mode-panel'
import { DiDoPanel } from './tabs/di-do-panel'
import { MonitoringPanel } from './tabs/monitoring-panel'
import { ErrorsPanel } from './tabs/errors-panel'
import { LogPanel } from './tabs/log-panel'
import { SavePanel } from './tabs/save-panel'
import { cn } from '@/shared/lib/cn'

type ModbusTab =
  | 'connection'
  | 'diagnostics'
  | 'parameters'
  | 'control'
  | 'dido'
  | 'monitoring'
  | 'errors'
  | 'log'
  | 'save'

const TABS: { id: ModbusTab; label: string }[] = [
  { id: 'connection', label: 'Подключение' },
  { id: 'diagnostics', label: 'Диагностика' },
  { id: 'parameters', label: 'Параметры' },
  { id: 'control', label: 'Управление' },
  { id: 'dido', label: 'DI/DO' },
  { id: 'monitoring', label: 'Мониторинг' },
  { id: 'errors', label: 'Ошибки' },
  { id: 'log', label: 'Журнал' },
  { id: 'save', label: 'Сохранение' },
]

function asTab(v: string | null): ModbusTab {
  return (TABS.find((t) => t.id === v)?.id) ?? 'connection'
}

export function ModbusDebugScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = asTab(searchParams.get('tab'))
  const snapshot = useHardwareStore((state) => state.snapshot)
  const runCommand = useHardwareStore((state) => state.runCommand)

  const setTab = (t: ModbusTab) => setSearchParams({ tab: t })

  return (
    <FormaShell
      userName="Debug"
      machine={snapshot?.machine ?? { machineState: 'ready', machineLabel: 'Debug', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: '—' }}
      onStop={() => { void runCommand({ action: 'trigger_emergency_stop', userId: null }) }}
    >
      <div className="flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#b5852f]/20 text-[#f2cf87]">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="4" width="20" height="16" rx="2" />
              <path d="M8 4v16M16 4v16M2 12h20" />
            </svg>
          </div>
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight text-[#f4dfb4]">
              Lichuan A6 · Modbus RTU Debug
            </h1>
            <p className="text-xs text-white/30">RS485 · 8E1 · Отладочная страница</p>
          </div>
        </div>

        {/* Tab bar */}
        <div className="overflow-x-auto">
          <div className="flex gap-1 min-w-max">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  'rounded-xl px-4 py-2 text-sm font-medium transition whitespace-nowrap',
                  tab === t.id
                    ? 'bg-[#b5852f]/30 text-[#f4dfb4] border border-[#b5852f]/50'
                    : 'text-white/40 hover:text-white hover:bg-white/6',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Tab content */}
        <div>
          {tab === 'connection' && <ConnectionPanel />}
          {tab === 'diagnostics' && <DiagnosticsPanel />}
          {tab === 'parameters' && <ParametersPanel />}
          {tab === 'control' && <ControlModePanel />}
          {tab === 'dido' && <DiDoPanel />}
          {tab === 'monitoring' && <MonitoringPanel />}
          {tab === 'errors' && <ErrorsPanel />}
          {tab === 'log' && <LogPanel />}
          {tab === 'save' && <SavePanel />}
        </div>
      </div>
    </FormaShell>
  )
}
