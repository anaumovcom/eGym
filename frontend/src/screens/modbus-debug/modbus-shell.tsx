import { Activity } from 'lucide-react'
import type { PropsWithChildren } from 'react'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import type { ModbusConnectionStatus } from '@/features/modbus/model/types'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import './modbus-debug-screen.css'

export function ModbusStatusBadge({ status, loading }: { status: ModbusConnectionStatus | null; loading: boolean }) {
  const pending = useModbusStore((s) => s.connectionPending)
  const state = !loading && status?.connected ? status.simulationMode ? 'simulated' : 'online' : 'offline'
  const text = pending === 'connect' ? 'Подключение…' : pending === 'disconnect' ? 'Отключение…' : loading ? 'Проверяем статус…' : !status ? 'Статус неизвестен' :
    !status.connected ? 'Не подключено' : status.simulationMode ? 'Симуляция' : 'Подключено'
  return <div className="modbus-link-status" data-state={state} role="status" aria-label="Состояние канала Modbus">
    <Activity size={18} aria-hidden="true" /><div><small>Канал Modbus RTU</small><strong>{text}</strong></div>
  </div>
}

export function ModbusShell({ children }: PropsWithChildren) {
  const userId = useAppStore((state) => state.selectedUserId)
  const runCommand = useHardwareStore((state) => state.runCommand)
  return (
    <FormaShell
      userName={userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'}
      machine={{ machineState: 'warning', machineLabel: 'Статус тренажёра неизвестен', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: '—' }}
      onStop={() => { void runCommand({ action: 'trigger_emergency_stop', userId }) }}
    >
      <div className="modbus-console">
        {children}
        <p className="modbus-safety-note">Программная остановка не заменяет физическую аварийную остановку.</p>
      </div>
    </FormaShell>
  )
}