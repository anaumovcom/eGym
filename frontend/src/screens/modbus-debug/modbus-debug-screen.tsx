import { ArrowLeft } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useModbusRead } from '@/features/modbus/lib/use-modbus-read'
import { useHardwareStore } from '@/stores/hardware-store'
import { ModbusShell, ModbusStatusBadge } from './modbus-shell'
import { DiagnosticsPanel } from './tabs/diagnostics-panel'
import { ParametersPanel } from './tabs/parameters-panel'
import { ControlModePanel } from './tabs/control-mode-panel'
import { DiDoPanel } from './tabs/di-do-panel'
import { MonitoringPanel } from './tabs/monitoring-panel'
import { ErrorsPanel } from './tabs/errors-panel'
import { LogPanel } from './tabs/log-panel'
import { SavePanel } from './tabs/save-panel'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'

type ModbusTab =
  | 'diagnostics'
  | 'parameters'
  | 'control'
  | 'dido'
  | 'monitoring'
  | 'errors'
  | 'log'
  | 'save'

const TABS: { id: ModbusTab; label: string }[] = [
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
  return (TABS.find((t) => t.id === v)?.id) ?? 'diagnostics'
}

export function ModbusDebugScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = asTab(searchParams.get('tab'))
  const snapshot = useHardwareStore((state) => state.snapshot)
  const selectedSide = useModbusStore((state) => state.selectedSide)
  const selectSide = useModbusStore((state) => state.selectSide)
  const driveAddresses = useModbusStore((state) => state.driveAddresses)
  const connectionStatus = useModbusStore((state) => state.connectionStatus)
  const loadStatus = useModbusStore((state) => state.loadStatus)
  const statusRead = useModbusRead(loadStatus, 2000)

  const setTab = (t: ModbusTab) => setSearchParams({ tab: t })

  return (
    <ModbusShell>
        <header className="modbus-hero">
          <div>
            <Link to="/settings?tab=service"><ArrowLeft size={15} aria-hidden="true" /> Сервис</Link>
            <h1>Modbus · Lichuan A6</h1>
            <p>Операторская диагностика · RS485 · 8E1</p>
          </div>
          <ModbusStatusBadge status={connectionStatus} loading={statusRead.loading} />
        </header>

        <div className="modbus-targets">
          <div><h2>Драйвер для чтения и записи</h2><p>Цель команд движения задаётся отдельно во вкладке «Управление».</p></div>
          <div className="modbus-target-list" role="group" aria-label="Драйвер сервопривода">
            {(['left', 'right'] as const).map((side) => {
              const drive = snapshot?.drives.find((item) => item.side === side)
              return (
                <button key={side} type="button" onClick={() => selectSide(side)} aria-pressed={selectedSide === side}>
                  <strong>{side === 'left' ? 'Левый' : 'Правый'} драйвер</strong>
                  <span>ID {driveAddresses[side]} · {drive == null ? 'нет телеметрии' : drive.connected ? 'на связи по данным тренажёра' : 'нет связи по данным тренажёра'}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="modbus-workspace">
          <nav className="modbus-nav" aria-label="Разделы Modbus">
            <Link to="/modbus/settings">Настройки Modbus</Link>
            {TABS.map((t) => (
              <button key={t.id} type="button" aria-current={tab === t.id ? 'page' : undefined} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
          </nav>

        <section className="modbus-content" aria-labelledby="modbus-section-title">
          <h2 id="modbus-section-title">{TABS.find((t) => t.id === tab)?.label}</h2>
          {tab === 'diagnostics' && <DiagnosticsPanel />}
          {tab === 'parameters' && <ParametersPanel />}
          {tab === 'control' && <ControlModePanel />}
          {tab === 'dido' && <DiDoPanel />}
          {tab === 'monitoring' && <MonitoringPanel />}
          {tab === 'errors' && <ErrorsPanel />}
          {tab === 'log' && <LogPanel />}
          {tab === 'save' && <SavePanel />}
        </section>
        </div>
    </ModbusShell>
  )
}
