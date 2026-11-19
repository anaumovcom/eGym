import { Link } from 'react-router-dom'
import { useModbusRead } from '@/features/modbus/lib/use-modbus-read'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'
import { ModbusShell, ModbusStatusBadge } from '@/screens/modbus-debug/modbus-shell'
import { ConnectionForm } from './connection-form'

export function ModbusSettingsScreen() {
  const { connectionStatus, loadPorts, loadStatus } = useModbusStore()
  const portsRead = useModbusRead(loadPorts)
  const statusRead = useModbusRead(loadStatus, 2000)
  const status = statusRead.failed ? null : connectionStatus

  return (
    <ModbusShell>
      <header className="modbus-hero">
        <div><Link to="/settings/drives">Выбор Modbus или CANopen</Link><h1>Настройки Modbus</h1><Link to="/modbus">Диагностика Modbus</Link></div>
        <ModbusStatusBadge status={status} loading={statusRead.loading} />
      </header>
      {statusRead.failed && <button type="button" onClick={statusRead.refresh}>Повторить чтение статуса</button>}
      <ConnectionForm status={status} portsRead={portsRead} checking={statusRead.loading} refreshStatus={statusRead.refresh} />
    </ModbusShell>
  )
}
